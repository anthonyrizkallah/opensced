"""The pricing run: Real-Time Reliability Deployment Price Adders (Protocols 6.5.7.3.1).

When ERCOT has taken reliability actions (units committed by RUC, Load Resources deployed, emergency imports), the
dispatch run's prices are lower than they would have been without them. ERCOT solves SCED a second time with those
actions undone and adds the difference to settlement prices:

    adder for energy     = max(pricing-run system lambda - dispatch-run system lambda, 0)        6.5.7.3.1(2)(o)
    adder for a reserve  = max(pricing-run clearing price - dispatch-run clearing price, 0)      6.5.7.3.1(2)(p)

The pricing run changes these inputs:

    (a)  a RUC-committed unit (status ONRUC, not opted out of RUC settlement), or one named in `rmr`: LSL and LDL to
         zero, its reserve offers removed, and all its capacity offered at the power balance penalty price. The text
         gives that offer for "the first step"; ERCOT's adders are only reproduced when it holds in the final step too
         (March 23, 2026 at 21:50: $294.78 against ERCOT's $286.92; on the unit's own $250 curve, $4.01)
    (c)-(e)  every other on-line resource SCED can move: LDL and HDL widened to what it can reach in 60 minutes from
         its telemetered output (not past LSL and HSL)
    (f)  the MW of non-controllable Load Resources that were deployed are added to demand, with a virtual offer for
         the same MW priced from $300 for the first MW to $700 for the last
    (g)-(k)  other deployed MW (ERS, DC tie and block load transfer adjustments) added to or taken off demand
    (l)-(n)  the two-step clearing again, from the offer curves before mitigation: step 1 on competitive constraints,
         with RUC and RMR units offered at the power balance penalty price; then mitigation against step 1's prices;
         then step 2 on every constraint. Give `unmitigated` (the same run built from ERCOT's step 1 curves, see
         unmitigated_inputs) for this. Without it the pricing run is one solve on the curves as given, which is
         only right when no offer cap would bind differently

With no reliability action in the interval there is no pricing run and the adders are zero.

What ERCOT publishes for each run (Real-Time Price Adders, NP6-323-CD): the adders, the RUC and RMR capacity relaxed
(RTRRUC, RTRRMR) and the MW added to demand (RTDNCLR, RTDERS, the DC tie and BLT columns).

    from opensced.markets.ercot import pricing
    run = pricing.pricing_run(inputs, deployed_load_mw=122.1)
    run.energy_adder, run.reserve_adders, run.dispatch, run.pricing
"""
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from opensced.core.model import clear
from opensced.markets.ercot.rulebooks import ALL

RUC_STATUSES = ('ONRUC',)
NOT_WIDENED = ('ONRUC', 'ONTEST', 'STARTUP', 'SHUTDOWN', 'ONHOLD', 'OUTL')
RAMP_MINUTES = 60.0
RUC_OFFER_FLOOR = 250.0                                                  # a RUC-committed unit must offer at or above this
DEPLOYED_LOAD_BID = (300.0, 700.0)                                       # $/MWh for the first and the last deployed MW
DEPLOYED = 'deployed load resources'


@dataclass
class PricingRun:
    dispatch: object                                                     # Result of the dispatch run
    pricing: object                                                      # Result of the pricing run
    energy_adder: float
    reserve_adders: pd.Series
    relaxed_mw: float                                                    # RUC / RMR low limits set to zero, MW
    added_demand_mw: float

    def __repr__(self):
        ra = ', '.join(f'{k} {v:.2f}' for k, v in self.reserve_adders.items())
        return (f'pricing run: lambda {self.pricing.system_lambda:.2f} against {self.dispatch.system_lambda:.2f} in the dispatch run\n'
                f'  energy adder ${self.energy_adder:.2f}; reserve adders {ra}\n'
                f'  {self.relaxed_mw:,.1f} MW of RUC/RMR low limits relaxed, {self.added_demand_mw:,.1f} MW added to demand')


def pricing_inputs(inputs, deployed_load_mw=0.0, other_demand_mw=0.0, rmr=(), opted_out=(), ramp_minutes=RAMP_MINUTES,
                   keep_binding_limits=False, deployed_load_bid=DEPLOYED_LOAD_BID, deployed_load_node=None, penalty_price=None):
    """The dispatch run's Inputs changed as 6.5.7.3.1(2)(a)-(k) says. -> (Inputs, MW of low limits relaxed)

    deployed_load_mw   MW of deployed non-controllable Load Resources to add back (ERCOT's RTDNCLR)
    other_demand_mw    net MW of the other reliability deployments to add to demand (ERS, DC tie, BLT)
    rmr                names of Reliability Must-Run units that are on line
    opted_out          names of ONRUC units whose QSE opted out of RUC settlement (6.5.7.3.1(1)(a)): they are left as
                       they are. ERCOT does not publish who opted out. below_ruc_floor() is one guess (units offering
                       under the $250 RUC floor); check the relaxed MW against ERCOT's RTRRUC before trusting it
    penalty_price      $/MWh for a RUC or RMR unit's capacity. Default: the rulebook's shortage price
    keep_binding_limits   leave a limit where the base point sat on it (NPRR904's wording, not yet in force: with no
                          reliability action ERCOT's adders are matched only when every limit is widened)
    deployed_load_node    settlement point for the virtual offer, if the network is modelled and you know where"""
    r = inputs.resources.copy()
    status = r['status'].astype(str).to_numpy() if 'status' in r else np.full(len(r), '')
    ruc = (np.isin(status, RUC_STATUSES) & ~r['name'].isin(set(opted_out)).to_numpy()) | r['name'].isin(set(rmr)).to_numpy()
    low, high = r['low'].to_numpy(float), r['high'].to_numpy(float)
    rl = r['ramp_low'].fillna(r['low']).to_numpy(float) if 'ramp_low' in r else low.copy()
    rh = r['ramp_high'].fillna(r['high']).to_numpy(float) if 'ramp_high' in r else high.copy()
    relaxed = float(np.clip(np.maximum(low, rl)[ruc], 0, None).sum())
    low, rl = np.where(ruc, np.minimum(low, 0.0), low), np.where(ruc, np.minimum(rl, 0.0), rl)
    disp = r['dispatchable'].fillna(False).to_numpy(bool) if 'dispatchable' in r else np.ones(len(r), bool)
    if 'telemetered' in r and 'ramp_up' in r:
        tel = r['telemetered'].to_numpy(float)
        up, down = r['ramp_up'].to_numpy(float), r['ramp_down'].to_numpy(float)
        out = r['output'].to_numpy(float)
        load = (r['kind'] == 'load').to_numpy() if 'kind' in r else np.zeros(len(r), bool)
        tel = np.where(load, out, tel)                                   # a controllable load: its consumption going in
        wide = disp & ~ruc & ~np.isin(status, NOT_WIDENED) & np.isfinite(tel) & np.isfinite(up) & np.isfinite(down)
        gen = wide & ~load & (r['kind'] != 'storage').to_numpy() if 'kind' in r else wide
        wide &= ~(gen & (tel < 0.95 * low))                              # (c): not a generator running below 95% of LSL
        at_low, at_high = np.abs(out - rl) < 1e-3, np.abs(out - rh) < 1e-3
        new_low = np.maximum(tel - ramp_minutes * down, low)
        new_high = np.minimum(tel + ramp_minutes * up, high)
        rl = np.where(wide & ~(keep_binding_limits & at_low), np.minimum(rl, new_low), rl)
        rh = np.where(wide & ~(keep_binding_limits & at_high), np.maximum(rh, new_high), rh)
    r['low'], r['ramp_low'], r['ramp_high'] = low, rl, rh
    names_ruc = set(r['name'][ruc])
    drop = lambda t: None if t is None else t[~t['resource'].isin(names_ruc)].reset_index(drop=True)
    offers, eo = drop(inputs.reserve_offers), inputs.energy_offers
    if names_ruc:
        pen = float(ALL.on(inputs.time).shortage if penalty_price is None and inputs.time is not None else (penalty_price or ALL.latest.shortage))
        eo = pd.concat([eo[~eo['resource'].isin(names_ruc)], pd.DataFrame([{'resource': n, 'mw': mw, 'price': pen} for n, h in zip(r['name'][ruc], high[ruc]) for mw in (0.0, float(h))])], ignore_index=True)
    limits = drop(inputs.reserve_limits)
    demand = float(inputs.demand) + float(deployed_load_mw) + float(other_demand_mw)
    nodes = inputs.resource_nodes
    if deployed_load_mw > 0:                                             # (f): the deployed MW come back as demand, with a
        row = {c: np.nan for c in r.columns}                             # virtual offer that serves them at $300 to $700
        row.update(name=DEPLOYED, low=0.0, high=float(deployed_load_mw), ramp_low=0.0, ramp_high=float(deployed_load_mw), output=0.0, dispatchable=True)
        for c, v in (('kind', 'generator'), ('type', 'VIRTUAL'), ('status', 'ON'), ('category', 'other'), ('mitigated', False)):
            if c in r:
                row[c] = v
        r = pd.concat([r, pd.DataFrame([row])], ignore_index=True)
        eo = pd.concat([eo, pd.DataFrame({'resource': DEPLOYED, 'mw': [0.0, float(deployed_load_mw)], 'price': list(deployed_load_bid)})], ignore_index=True)
        if deployed_load_node is not None and nodes is not None:
            nodes = pd.concat([pd.Series(nodes), pd.Series({DEPLOYED: deployed_load_node})])
    for c in ('dispatchable', 'mitigated'):
        if c in r:
            r[c] = r[c].astype(bool)
    return inputs.copy(resources=r, demand=demand, energy_offers=eo, reserve_offers=offers, reserve_limits=limits, resource_nodes=nodes), relaxed


def below_ruc_floor(inputs):
    """Names of ONRUC units offering below the RUC offer floor: a guess at who opted out of RUC settlement. Against
    ERCOT's published relaxed MW it is right on every run of March 23, 2026 and wrong on a third of August 12."""
    e, r = inputs.energy_offers, inputs.resources
    lowest = e[e['mw'] > 0].groupby('resource')['price'].min()
    under = set(lowest.index[lowest < RUC_OFFER_FLOOR - 0.01])
    return sorted(under & set(r['name'][np.isin(r['status'].astype(str), RUC_STATUSES)]))


def unmitigated_inputs(day, time, **options):
    """A run's Inputs from ERCOT's step 1 (unmitigated) curves, with the resources ERCOT capped marked `mitigated` and
    their caps taken from ERCOT's own step 2 curves. day: an ERCOT Day. options: as for day.inputs().

    A resource was capped where its step 2 curve is below its step 1 curve. Its step 2 curve is then the cap ERCOT
    applied in the dispatch run: the higher of its mitigated offer cap and that run's reference price. In the pricing
    run the cap is the higher of that curve and the pricing run's own reference price."""
    from opensced.markets.ercot.adapter import NPT, RES
    x = day._by_run[pd.Timestamp(time)].reset_index(drop=True)
    num = lambda c: pd.to_numeric(x[c], errors='coerce').to_numpy(float) if c in x else np.full(len(x), np.nan)
    m1 = np.column_stack([num(f'SCED1CurveMW{j}') for j in range(1, NPT + 1)])
    p1 = np.column_stack([num(f'SCED1CurvePrice{j}') for j in range(1, NPT + 1)])
    m2 = np.column_stack([num(f'SCED2CurveMW{j}') for j in range(1, NPT + 1)])
    p2 = np.column_stack([num(f'SCED2CurvePrice{j}') for j in range(1, NPT + 1)])
    names, capped, caps = x[RES].to_numpy(), [], []
    for i in range(len(x)):
        a, b = np.isfinite(m1[i]) & np.isfinite(p1[i]), np.isfinite(m2[i]) & np.isfinite(p2[i])
        if a.sum() < 2 or b.sum() < 2:
            continue
        u = np.unique(m2[i][b])
        if len(u) < 2:
            continue
        q = (u[:-1] + u[1:]) / 2
        o1, o2 = np.argsort(m1[i][a], kind='stable'), np.argsort(m2[i][b], kind='stable')
        if (np.interp(q, m2[i][b][o2], p2[i][b][o2]) < np.interp(q, m1[i][a][o1], p1[i][a][o1]) - 0.011).any():
            capped.append(names[i])
            caps.append(pd.DataFrame({'resource': names[i], 'mw': m2[i][b][o2], 'price': p2[i][b][o2]}))
    table = pd.concat(caps, ignore_index=True) if caps else None
    return day.inputs(time, curve='SCED1', mitigated=capped, mitigated_offer_caps=table, **options)


def pricing_run(inputs, rules=None, dispatch=None, unmitigated=None, always=False, **changes):
    """Clear the dispatch run and the pricing run and take the adders. -> PricingRun

    inputs       the dispatch run's Inputs (from ercot.inputs() or Day.inputs())
    rules        the rulebook. Default: the one in force at inputs.time
    dispatch     the dispatch run's Result, if already cleared
    unmitigated  the same run from ERCOT's step 1 curves (unmitigated_inputs). The pricing run then repeats the two-step
                 clearing as 6.5.7.3.1(2)(l)-(n) says
    always       run the pricing solve even when no reliability action is active. By default the adders are zero then:
                 6.5.7.3.1(2) determines them only "for intervals where there are reliability deployments". Some
                 deployments are not in ERCOT's published report (off-line Non-Spin brought on line, for one); pass
                 always=True for an interval you know had one
    changes      deployed_load_mw, other_demand_mw, rmr, ... (see pricing_inputs)"""
    from opensced.core.features import mitigation
    from opensced.core.model import _clear_once
    rules = rules or (ALL.on(inputs.time) if inputs.time is not None else ALL.latest)
    dispatch = dispatch or clear(inputs, rules, check=False)
    changed, relaxed = pricing_inputs(inputs if unmitigated is None else unmitigated, **changes)
    acted = relaxed > 0 or abs(float(changed.demand) - float((inputs if unmitigated is None else unmitigated).demand)) > 0 or bool(changes.get('rmr'))
    if not acted and not always:                                         # nothing was deployed: there is no pricing run
        zero = pd.Series(0.0, index=dispatch.reserve_prices.index, name='adder') if dispatch.reserve_prices is not None else pd.Series(dtype=float, name='adder')
        return PricingRun(dispatch, dispatch, 0.0, zero, 0.0, 0.0)
    if unmitigated is None:
        priced = clear(changed, rules, check=False)
    else:
        step1 = _clear_once(mitigation.competitive_only(changed), rules)
        if not step1.solved:
            priced = step1
        else:
            step1._inputs = changed
            reference = step1.resource_prices().rename('reference_price')
            priced = _clear_once(changed.copy(energy_offers=mitigation.mitigate(changed, reference, rules), mitigated=True), rules)
            priced.reference_prices, priced.step1 = reference, step1
    energy = max(priced.system_lambda - dispatch.system_lambda, 0.0) if priced.solved and dispatch.solved else float('nan')
    if priced.reserve_prices is not None and dispatch.reserve_prices is not None:
        reserves = (priced.reserve_prices - dispatch.reserve_prices).clip(lower=0.0).rename('adder')
    else:
        reserves = pd.Series(dtype=float, name='adder')
    return PricingRun(dispatch, priced, energy, reserves, relaxed, float(changed.demand) - float(inputs.demand))
