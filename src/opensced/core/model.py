"""clear(): one interval's inputs and a rulebook in, prices and dispatch out.

The clearing is one linear program, solved with HiGHS. core/features holds its parts:

  minimize    energy offer cost + reserve offer cost - value of reserves bought on the demand curves
              + shortage_price x shortfall - surplus_price x surplus + max_shadow_price x constraint violations
  subject to  the power balance, each resource's limits, reserve headroom, battery state of charge and the network

Prices are the program's duals: the system lambda from the power balance, each constraint's shadow price from its
row, each reserve product's clearing price from its demand row.
"""
import numpy as np
import pandas as pd

from opensced.core import tables
from opensced.core.features import balance, mitigation, network, reserves, storage
from opensced.core.program import Program
from opensced.core.result import Result
from opensced.core.rules import Rules


def _col(r, name, default):
    if name in r.columns:
        return pd.to_numeric(r[name], errors='coerce').to_numpy(float)
    return np.asarray(default, float) if not np.isscalar(default) else np.full(len(r), float(default))


def _prepare(inputs, rules, focus=None):
    """the resources table as arrays: where each resource starts, how far it may move, what it may carry."""
    r = inputs.resources.reset_index(drop=True)
    names = r['name'].to_numpy()
    low, high = _col(r, 'low', 0), _col(r, 'high', 0)
    ramp_low, ramp_high = _col(r, 'ramp_low', low), _col(r, 'ramp_high', high)
    ramp_low, ramp_high = np.where(np.isnan(ramp_low), low, ramp_low), np.where(np.isnan(ramp_high), high, ramp_high)
    output = np.nan_to_num(_col(r, 'output', 0.0))
    can = r['dispatchable'].fillna(False).to_numpy(bool) if 'dispatchable' in r else np.ones(len(r), bool)
    lo, hi = (ramp_low, ramp_high) if rules.dispatch_limits == 'ramp' else (np.fmax(ramp_low, low), np.fmin(ramp_high, high))
    disp = can & np.isfinite(lo) & np.isfinite(hi) & (hi >= lo)
    lo, hi = np.where(disp, lo, output), np.where(disp, hi, output)
    S = dict(n=len(r), table=r, names=names, at={n: i for i, n in enumerate(names)}, disp=disp, lo=lo, hi=hi, low=low, high=high,
             ramp_low=ramp_low, ramp_high=ramp_high, output=output)
    S['B'] = balance.blocks(S, inputs.energy_offers, rules, {S['at'][k]: v for k, v in focus.items() if k in S['at']} if focus else None)
    S['blocks_of'] = pd.Series(np.arange(len(S['B']))).groupby(S['B'].res.to_numpy()).apply(np.array).to_dict()
    return S


def _storage_state(S, inputs, efficiency=1.0):
    n = S['n']
    S['esr'], S['head'], S['room'], S['eff'] = np.zeros(n, bool), np.full(n, np.inf), np.full(n, np.inf), np.full(n, float(efficiency))
    st = inputs.storage
    if st is None or not len(st):
        return
    i = st['resource'].map(S['at'])
    ok = i.notna().to_numpy()
    i = i[ok].astype(int).to_numpy()
    soc, mn, mx = (pd.to_numeric(st[c], errors='coerce').to_numpy(float)[ok] for c in ('soc', 'soc_min', 'soc_max'))
    good = np.isfinite(soc) & S['disp'][i]
    S['esr'][i[good]] = True
    S['head'][i[good]], S['room'][i[good]] = (soc - mn)[good], (mx - soc)[good]
    if 'efficiency' in st:
        eff = pd.to_numeric(st['efficiency'], errors='coerce').to_numpy(float)[ok]
        S['eff'][i[good]] = np.where(np.isfinite(eff) & (eff > 0), eff, float(efficiency))[good]


def clear(inputs, rules=None, check=True):
    """Clear one interval.

        result = clear(inputs)                      # default rulebook: energy and network
        result = clear(inputs, rules=my_rules)

    inputs  an opensced.Inputs (see opensced.schema())
    rules   an opensced.Rules. Markets supply dated ones: opensced.market('ercot').rules.on('2026-08-12')
    check   validate the tables first. Turn off inside a loop once the inputs are known to be clean.

    Reserves are cleared when the rulebook has products and inputs.reserve_demand is given. Constraints are enforced
    when inputs.constraints is given. -> opensced.Result"""
    rules = rules or Rules()
    if check:
        tables.validate(inputs, rules.product_names or None, rules.demand_names or None)
    if not rules.two_step or inputs.mitigated:
        return _clear_once(inputs, rules)
    first = _clear_once(mitigation.competitive_only(inputs), rules)      # step 1: reference prices
    if not first.solved:
        return first
    first._inputs = inputs                                               # price resources with the full shift-factor table
    reference = first.resource_prices().rename('reference_price')
    second = _clear_once(inputs.copy(energy_offers=mitigation.mitigate(inputs, reference, rules), mitigated=True), rules)
    second.reference_prices, second.step1 = reference, first
    return second


def _clear_once(inputs, rules):
    """the program for the offers as given: solved, then solved again with each resource's curve cut finer around
    where it landed (rules.block_refine passes), so sloped offer curves are priced where they are actually met."""
    result, focus, step = _solve(inputs, rules, None), {}, rules.block_mw
    for _ in range(0 if rules.offer_curves == 'exact' else rules.block_refine):
        if not result.solved:
            break
        fine = step / rules.block_refine_factor
        lo, hi = result._range                                           # a resource at a limit is cut finer too: where its
        for name, mw in result.dispatch[hi - lo > rules.tolerance_mw].items():   # curve slopes away from the limit, the first
            focus.setdefault(name, []).append((float(mw), step, fine))   # coarse step may be all that kept it there
        result, step = _solve(inputs, rules, focus), fine
    return result


def _solve(inputs, rules, focus):
    """one solve of the program."""
    S = _prepare(inputs, rules, focus)
    with_reserves = rules.has('reserves') and bool(rules.products) and inputs.reserve_demand is not None
    S['cons'], S['sf'] = network.matrix(S, inputs, rules.shift_factor_cutoff) if rules.has('network') else (None, None)
    P = Program()
    balance.variables(P, S, rules)
    if with_reserves:
        S['cap'], S['OB'] = reserves.limits(S, inputs, rules)
        _storage_state(S, inputs, rules.storage_charge_efficiency)
        if not rules.has('storage'):
            S['esr'][:] = False
        reserves.award_variables(P, S, rules)
        storage.variables(P, S, rules)
        reserves.offer_variables(P, S, rules)
        reserves.demand_variables(P, S, inputs, rules)
    if S['cons'] is not None:
        network.variables(P, S)
    if with_reserves:
        reserves.resource_rows(P, S, rules)
        storage.rows(P, S, rules)
        reserves.offer_rows(P, S)
        reserves.demand_rows(P, S, inputs, rules)
    if S['cons'] is not None:
        network.rows(P, S)
    eq, rhs = balance.equation(P, S, float(inputs.demand))
    sol = P.solve(eq, rhs, rules.solver, rules.solver_options)
    passes = 0
    while with_reserves and rules.storage_charge_offset and sol.status == 0 and passes < rules.storage_passes and S['esr'].any():
        lower, upper = storage.settle_direction(P, S, sol.x, rules)     # one battery, one direction
        if not lower and not upper:
            break
        P.pin(lower, upper)
        again = P.solve(eq, rhs, rules.solver, rules.solver_options)
        if again.status != 0:
            break
        sol, passes = again, passes + 1
    cnames = pd.Index(S['cons']['name'].to_numpy() if S['cons'] is not None else [], name='constraint')
    if sol.status != 0:
        return Result(solved=False, status=str(sol.message), system_lambda=float('nan'), rules=rules, time=inputs.time,
                      shadow_prices=pd.Series(np.nan, index=cnames, name='shadow_price'), _inputs=inputs)
    nb = len(S['B'])
    p = S['lo'].copy()
    np.add.at(p, S['B'].res.to_numpy(), sol.x[:nb])
    duals = sol.ineqlin.marginals if P.rows else np.zeros(0)
    slack = P.start('slack')
    awards, prices, bought = None, None, None
    if with_reserves:
        cols = {}
        for name in rules.product_names:
            st, ln = P.var[f'r_{name}']
            a = np.zeros(S['n'])
            a[S['rv'][name]] = sol.x[st:st + ln]
            cols[name] = a
        awards = pd.DataFrame(cols, index=pd.Index(S['names'], name='resource'))
        awards = awards[(awards.abs() > 1e-9).any(axis=1)]
        prices = pd.Series({name: float(-duals[S['reserve_rows'][name]]) for name in rules.demand_names}, name='price')
        bought = pd.Series({name: float(sol.x[P.var[f'q_{name}'][0]:sum(P.var[f'q_{name}'])].sum()) for name in rules.demand_names}, name='mw')
    violation = None
    if S['cons'] is not None:
        v = P.start('violation')
        violation = pd.Series(sol.x[v:v + len(cnames)], index=cnames, name='violation_mw')
    lam = float(sol.eqlin.marginals[0])
    cap = rules.cap
    uncapped = {'system_lambda': lam, 'reserve_prices': prices}
    if cap is not None:                                                  # prices are capped after the solve
        prices = None if prices is None else prices.clip(upper=cap)
    out = Result(
        solved=True, status='ok', system_lambda=lam if cap is None else min(lam, cap), uncapped=uncapped, rules=rules, time=inputs.time,
        shadow_prices=pd.Series([float(-duals[k]) for k in S.get('net_rows', [])], index=cnames, name='shadow_price', dtype=float),
        dispatch=pd.Series(p, index=pd.Index(S['names'], name='resource'), name='mw'),
        reserve_awards=awards, reserve_prices=prices, reserve_bought=bought, violations=violation,
        shortfall=float(sol.x[slack]), surplus=float(sol.x[slack + 1]), cost=float(sol.fun), _inputs=inputs)
    out._range = (S['lo'], S['hi'])
    return out
