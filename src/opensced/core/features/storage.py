"""Battery state of charge under energy and reserve awards.

What a battery is told to do over one interval, plus every reserve it is awarded, must fit in the energy it holds:

    discharge side   p x interval + sum over up products of r x duration                       <= soc - soc_min
    charge side      eff x (charging MW x interval + sum over down products of r x duration)
                     - discharging MW x interval                                               <= soc_max - soc

p is the battery's output and is signed: discharging uses stored energy, charging adds to it. So a battery that is
charging can carry a little more upward reserve, by exactly the energy it takes in during the interval, and no more.
This is rules.storage_signed_energy, the default.

eff is the storage table's `efficiency`: of each MWh taken from the grid, the share that ends up stored. It applies to
what would be taken in (charging, and a downward reserve if deployed), not to discharge. Checked against ERCOT's
Reg-Down awards on seven days in 2026 (31,450 battery-runs): with each battery's own efficiency and 30 minutes for
Reg-Down no award breaks the charge-side row and one in five sits exactly on it.

Checked against ERCOT's own awards on five days in 2026 (about 260,000 battery-runs with upward awards): none breaks
the discharge-side row, and about 40% sit exactly on it.

Both sides are floored at what the battery's energy dispatch alone can reach, so a battery that cannot move loses
reserves instead of making the program infeasible.

An older reading, rules.storage_charge_offset, lets a charging battery count every MW it could stop charging as
reserve that needs no stored energy at all (w below: w <= r, sum of w <= charging MW). It is kept as an option, off by
default: with it, a linear program finds it pays to charge at peak prices only to sell reserve. Under that option
settle_direction() also stops a battery from using charging and discharging blocks at once.
"""
import numpy as np


def variables(P, S, rules):
    S['wv'] = {}
    esr = np.where(S['esr'])[0] if rules.storage_charge_offset else np.array([], int)   # w exists only under the offset option
    for p in rules.products:
        if p.direction == 'up':
            idx = np.intersect1d(S['rv'][p.name], esr)
            S['wv'][p.name] = idx
            P.add(f'w_{p.name}', np.zeros(len(idx)), np.full(len(idx), np.inf))


def rows(P, S, rules):
    from opensced.core.features.reserves import rcol
    B, stp = S['B'], rules.interval_hours
    bhi, blo = B.hi.to_numpy(), B.lo.to_numpy()
    up = [p for p in rules.products if p.direction == 'up']
    down = [p for p in rules.products if p.direction == 'down']
    signed = rules.storage_signed_energy and not rules.storage_charge_offset
    for i in np.where(S['esr'])[0]:
        bl = S['blocks_of'].get(i, np.array([], int))
        neg, pos = bl[bhi[bl] <= 1e-9], bl[blo[bl] >= -1e-9]
        lo = S['lo'][i]
        d0, c0 = max(lo, 0.0), max(-lo, 0.0)                             # discharge / charging at the resource's floor
        span = float((bhi[bl] - blo[bl]).sum()) if len(bl) else 0.0
        energy = list(bl) if signed else list(pos)                       # signed: every block moves stored energy
        cols, vals, ws = list(energy), [stp] * len(energy), []
        for p in up:
            r = rcol(P, S, p.name, i)
            if r is None:
                continue
            cols.append(r); vals.append(p.duration_hours)
            if rules.storage_charge_offset:
                w = P.start(f'w_{p.name}') + int(np.searchsorted(S['wv'][p.name], i))
                cols.append(w); vals.append(-p.duration_hours)
                ws.append(w)
                P.row([w, r], [1.0, -1.0], 0.0)
        P.row(cols, vals, max(S['head'][i] - (lo if signed else d0) * stp, 0.0))
        if ws:
            P.row(ws + list(neg), [1.0] * (len(ws) + len(neg)), c0)
        eff = S['eff'][i] if signed else 1.0                             # share of charging energy that ends up stored
        charging = bl[bhi[bl] <= 1e-9]                                   # blocks below 0 MW; the rest discharge
        other = bl[bhi[bl] > 1e-9] if signed else np.array([], int)
        cols, vals = list(charging) + list(other), [-eff * stp] * len(charging) + [-stp] * len(other)
        for p in down:
            r = rcol(P, S, p.name, i)
            if r is not None:
                cols.append(r); vals.append(eff * p.duration_hours)
        reach = -(eff * float((bhi[charging] - blo[charging]).sum()) + float((bhi[other] - blo[other]).sum())) * stp
        start = (eff * min(lo, 0.0) + max(lo, 0.0)) if signed else -c0
        P.row(cols, vals, max(S['room'][i] + start * stp, reach))


def settle_direction(P, S, x, rules):
    """Bounds that stop batteries charging and discharging at once in the solution x. -> (lower, upper) dicts of
    variable index -> bound; both empty when no battery did."""
    B, tol = S['B'], max(rules.tolerance_mw, 1e-4)
    bhi, blo = B.hi.to_numpy(), B.lo.to_numpy()
    width = bhi - blo
    lower, upper = {}, {}
    for i in np.where(S['esr'])[0]:
        bl = S['blocks_of'].get(i, np.array([], int))
        neg, pos = bl[bhi[bl] <= 1e-9], bl[blo[bl] >= -1e-9]
        if not len(neg) or not len(pos):
            continue
        unused_charging = float((width[neg] - x[neg]).sum())
        discharging = float(x[pos].sum())
        if unused_charging <= tol or discharging <= tol:
            continue
        net = S['lo'][i] + float(x[bl].sum())
        if net >= 0:                                                     # it is discharging: no charging to give up
            for k in neg:
                lower[int(k)] = float(width[k])
            for p_, idx in S['wv'].items():
                j = int(np.searchsorted(idx, i))
                if j < len(idx) and idx[j] == i:
                    upper[P.start(f'w_{p_}') + j] = 0.0
        else:                                                            # it is charging: nothing above 0 MW
            for k in pos:
                upper[int(k)] = 0.0
    return lower, upper
