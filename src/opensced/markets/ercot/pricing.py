"""The pricing run: Real-Time Reliability Deployment Price Adders (Protocols 6.5.7.3.1).

When ERCOT has taken reliability actions (units committed by RUC, Load Resources deployed, emergency imports), the
dispatch run's prices are lower than they would have been without them. ERCOT solves SCED a second time with those
actions undone and adds the difference to settlement prices:

    adder for energy     = max(pricing-run system lambda - dispatch-run system lambda, 0)        6.5.7.3.1(2)(o)
    adder for a reserve  = max(pricing-run clearing price - dispatch-run clearing price, 0)      6.5.7.3.1(2)(p)

The pricing run changes these inputs:

    (a)  a RUC-committed unit (status ONRUC, not opted out of RUC settlement), or one named in `rmr`: LSL and LDL to
         zero, its reserve offers removed, and for the first step all its capacity offered at the power balance
         penalty price
    (c)-(e)  every other on-line resource SCED can move: LDL and HDL widened to what it can reach in 60 minutes from
         its telemetered output (not past LSL and HSL)
    (f)  the MW of non-controllable Load Resources that were deployed are added to demand, with a virtual offer for
         the same MW priced from $300 for the first MW to $700 for the last
    (g)-(k)  other deployed MW (ERS, DC tie and block load transfer adjustments) added to or taken off demand
    (l)-(n)  the two-step clearing again. Step 1 on competitive constraints only, RUC and RMR units at the penalty
         price; each resource's price in it is its reference price. Step 2 on every constraint. In step 2 a RUC or
         RMR unit that is subject to mitigation (Protocols 3.19.4, 6.5.7.3(14)(b)(i)) has its penalty-price curve
         capped at its reference price, so it comes back wherever step 2 would otherwise price above step 1. One that
         is not subject to mitigation stays at the penalty price. Checked on ERCOT's adders both ways:
           August 23, 2026 at 20:00, RUC units mitigated: ERCOT $39.86; capped $39.7; left at the penalty price $209.76
           March 23, 2026 at 21:50, RUC units not mitigated: ERCOT $286.92; at the penalty price $294.78; capped $105.26
         Who is subject to mitigation is an input (`mitigated`): the competitiveness test is not run here.
         mitigated_in_hour() reads it off ERCOT's own curves.
         Every other resource keeps the curve it was given. Give `unmitigated` (the same run built from ERCOT's step 1
         curves, see unmitigated_inputs) to redo their mitigation against the pricing run's own reference prices too

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
NOT_WIDENED = ('ONRUC', 'ONTEST', 'STARTUP', 'STARTUP-NS', 'SHUTDOWN', 'ONHOLD', 'OUTL')
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


def relaxed_units(inputs, rmr=(), opted_out=()):
    """Names of the units the pricing run prices out: ONRUC and not opted out, or named in rmr."""
    r = inputs.resources
    status = r['status'].astype(str).to_numpy() if 'status' in r else np.full(len(r), '')
    m = (np.isin(status, RUC_STATUSES) & ~r['name'].isin(set(opted_out)).to_numpy()) | r['name'].isin(set(rmr)).to_numpy()
    return list(r['name'][m])


def pricing_inputs(inputs, deployed_load_mw=0.0, other_demand_mw=0.0, rmr=(), opted_out=(), ramp_minutes=RAMP_MINUTES,
                   keep_binding_limits=False, deployed_load_bid=DEPLOYED_LOAD_BID, deployed_load_node=None, penalty_price=None):
    """The dispatch run's Inputs changed as 6.5.7.3.1(2)(a)-(k) says. -> (Inputs, MW of low limits relaxed)

    deployed_load_mw   MW of deployed non-controllable Load Resources to add back (ERCOT's RTDNCLR)
    other_demand_mw    net MW of the other reliability deployments to add to demand (ERS, DC tie, BLT)
    rmr                names of Reliability Must-Run units that are on line
    opted_out          names of ONRUC units whose QSE opted out of RUC settlement (6.5.7.3.1(1)(a)): they are left as
                       they are. ERCOT does not publish who opted out; opted_out_from_relaxed() works it out from the
                       relaxed MW ERCOT does publish (RTRRUC)
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


def capped_by_ercot(day, time):
    """The resources ERCOT capped in one run, read off its curves: step 2 curve below step 1 curve.
    -> (names, table resource, mw, price of their step 2 curves)

    This only sees a cap that bit. A mitigated resource whose reference price is above its whole offer curve looks
    the same as one that is not mitigated."""
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
    return capped, (pd.concat(caps, ignore_index=True) if caps else None)


def mitigated_in_hour(day, time):
    """Names of the resources ERCOT's curves show as capped in any run of the Operating Hour `time` is in.

    Mitigation, once applied to a resource, stays for the rest of the Operating Hour (3.19.4), and a cap can only be
    seen in a run where it bit, so the hour is read as a whole. A resource whose reference price stayed above its
    offer curve all hour cannot be told apart from one that was never mitigated: it is left out."""
    t = pd.Timestamp(time)
    names = set()
    for u in day.times:
        if pd.Timestamp(u).floor('h') == t.floor('h'):
            names |= set(capped_by_ercot(day, u)[0])
    return sorted(names)


def opted_out_from_relaxed(inputs, relaxed_mw, tolerance=1.0, rmr=()):
    """Names of the ONRUC units left out of ERCOT's pricing run, worked out from the RUC capacity it says it relaxed
    (RTRRUC in the Real-Time Price Adders report). -> list of names, or None when no set of units adds up

    ERCOT does not publish who opted out of RUC settlement, but it does publish the total low limit it set to zero.
    The units whose low dispatch limits add up to that total are the ones it relaxed; the rest were left alone.
    With several sets within the tolerance, the one leaving out the fewest units is taken."""
    from itertools import combinations
    r = inputs.resources
    names = relaxed_units(inputs, rmr)
    if not names:
        return []
    x = r.set_index('name')
    low = np.maximum(x['low'], x['ramp_low'].fillna(x['low']) if 'ramp_low' in x else x['low']).clip(lower=0.0).reindex(names).to_numpy(float)
    if len(names) > 16:
        return None
    for k in range(len(names) + 1):                                      # leave out as few as possible
        best = None
        for out in combinations(range(len(names)), k):
            miss = abs(low.sum() - low[list(out)].sum() - float(relaxed_mw))
            if miss <= tolerance and (best is None or miss < best[0]):
                best = (miss, out)
        if best is not None:
            return [names[i] for i in best[1]]
    return None


def unmitigated_inputs(day, time, **options):
    """A run's Inputs from ERCOT's step 1 (unmitigated) curves, with the resources ERCOT capped marked `mitigated` and
    their caps taken from ERCOT's own step 2 curves. day: an ERCOT Day. options: as for day.inputs().

    A resource was capped where its step 2 curve is below its step 1 curve. Its step 2 curve is then the cap ERCOT
    applied in the dispatch run: the higher of its mitigated offer cap and that run's reference price. In the pricing
    run the cap is the higher of that curve and the pricing run's own reference price."""
    capped, table = capped_by_ercot(day, time)
    return day.inputs(time, curve='SCED1', mitigated=capped, mitigated_offer_caps=table, **options)


def pricing_run(inputs, rules=None, dispatch=None, unmitigated=None, always=False, mitigated=None, **changes):
    """Clear the dispatch run and the pricing run and take the adders. -> PricingRun

    inputs       the dispatch run's Inputs (from ercot.inputs() or Day.inputs())
    rules        the rulebook. Default: the one in force at inputs.time
    dispatch     the dispatch run's Result, if already cleared
    unmitigated  the same run from ERCOT's step 1 curves (unmitigated_inputs). Every resource's curve is then mitigated
                 again against the pricing run's reference prices, not only the RUC and RMR units'
    mitigated    names of the resources subject to mitigation in the interval (mitigated_in_hour). Only matters for
                 RUC and RMR units: one named here is capped at its step 1 price in step 2, any other stays at the
                 penalty price. Default: the ones marked `mitigated` in inputs.resources
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
    source = inputs if unmitigated is None else unmitigated
    units = relaxed_units(source, changes.get('rmr', ()), changes.get('opted_out', ()))
    if unmitigated is None and not units:                                # only demand was added: one solve
        priced = clear(changed, rules, check=False)
    else:
        step1 = _clear_once(mitigation.competitive_only(changed), rules)
        if not step1.solved:
            priced = step1
        else:
            step1._inputs = changed
            reference = step1.resource_prices().rename('reference_price')
            offers = changed.energy_offers if unmitigated is None else mitigation.mitigate(changed, reference, rules)
            flagged = set(mitigated) if mitigated is not None else (set(source.resources['name'][source.resources['mitigated'].fillna(False).astype(bool)]) if 'mitigated' in source.resources else set())
            capped = [n for n in units if n in flagged and n in reference.index and np.isfinite(reference[n])]
            if capped:                                                   # (m): a mitigated priced-out unit is capped at its reference price
                high = changed.resources.set_index('name')['high']
                cap = pd.DataFrame([{'resource': n, 'mw': mw, 'price': float(reference[n])} for n in capped for mw in (0.0, float(high[n]))])
                offers = pd.concat([offers[~offers['resource'].isin(set(capped))], cap], ignore_index=True)
            priced = _clear_once(changed.copy(energy_offers=offers, mitigated=True), rules)
            priced.reference_prices, priced.step1 = reference, step1
    energy = max(priced.system_lambda - dispatch.system_lambda, 0.0) if priced.solved and dispatch.solved else float('nan')
    if priced.reserve_prices is not None and dispatch.reserve_prices is not None:
        reserves = (priced.reserve_prices - dispatch.reserve_prices).clip(lower=0.0).rename('adder')
    else:
        reserves = pd.Series(dtype=float, name='adder')
    return PricingRun(dispatch, priced, energy, reserves, relaxed, float(changed.demand) - float(inputs.demand))
