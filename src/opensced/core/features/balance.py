"""Energy: each dispatchable resource's offer curve cut into blocks, and the power balance.

A resource may move between lo = max(ramp_low, low) and hi = min(ramp_high, high). Its curve is cut at its own points
and into steps of at most rules.block_mw, each priced at the curve's value at the step's midpoint (the curve is linear
in price between points and flat beyond the ends). A resource that is not dispatchable is held at its output.

rules.offer_curves = 'exact' does without steps: each stretch of a curve between two of its points is one variable
whose cost is the area under the sloped line, price_at_start x + 1/2 slope x^2. The program is then quadratic and
dispatch lands exactly where each line meets the price. This is the same answer the refined steps converge to.

An offer curve is a sloped line between its points, so the cost of a resource is quadratic and its dispatch lands
where the line meets the price. Steps only approximate that: a 5 MW step on a steep stretch misprices the marginal MW
by its slope times up to 2.5 MW. rules.block_refine solves again with the curve cut finer around where each resource
landed (`focus`), each pass ten times finer than the last, until the steps are small enough not to matter.

    balance   sum of dispatch + shortfall - surplus = demand            (its dual is the system lambda)
"""
import numpy as np
import pandas as pd


def blocks(S, energy_offers, rules, focus=None):
    """-> DataFrame res (resource index), lo, hi, price: the energy blocks of every resource that can move.
    focus  {resource index: [(center MW, half width MW, step MW), ...]}: extra cuts around a dispatch, on sloped stretches."""
    lo, hi = S['lo'], S['hi']
    block_mw, tol = rules.block_mw, rules.tolerance_mw
    below = rules.offer_floor if rules.curve_extension == 'floor' else None      # price below a curve's lowest point
    curves = {}
    if energy_offers is not None and len(energy_offers):
        at = S['at']
        idx = energy_offers['resource'].map(at)
        ok = idx.notna().to_numpy()
        e = pd.DataFrame({'i': idx[ok].astype(int).to_numpy(), 'mw': pd.to_numeric(energy_offers['mw'])[ok].to_numpy(float),
                          'price': pd.to_numeric(energy_offers['price'])[ok].to_numpy(float)})
        e = e[np.isfinite(e.mw) & np.isfinite(e.price)]
        curves = {i: (g.mw.to_numpy(), g.price.to_numpy()) for i, g in e.groupby('i', sort=False)}
    rows, exact = [], rules.offer_curves == 'exact'
    for i in np.where(S['disp'] & (hi - lo > tol))[0]:
        m, p = curves.get(i, (np.array([lo[i], hi[i]]), np.full(2, rules.no_offer_price)))
        o = np.argsort(m, kind='stable')
        m, p = m[o], p[o]
        extra = []
        for c, half, step in (focus or {}).get(i, ()):
            a, b = max(c - half, lo[i]), min(c + half, hi[i])
            if b - a > tol and abs(np.interp(b, m, p, left=below) - np.interp(a, m, p, left=below)) > 1e-9:   # flat: nothing to gain
                extra.append(np.arange(a, b + step / 2, step))
        knots = np.unique(np.clip(np.r_[lo[i], m, hi[i], [0.0] if rules.zero_split else [], *extra], lo[i], hi[i]))   # 0: charging | discharging
        for a, b in zip(knots[:-1], knots[1:]):
            if b - a <= tol:
                continue
            if exact:                                                    # one variable per stretch of the curve: the price
                pa, pb = (float(np.interp(a + 1e-9, m, p, left=below)), float(np.interp(b - 1e-9, m, p, left=below)))   # runs
                slope = (pb - pa) / (b - a)                              # from pa to pb, so its cost is pa x + 1/2 slope x^2
                rows.append((i, a, b, pa, slope) if slope > 0 else (i, a, b, (pa + pb) / 2, 0.0))   # a falling stretch: its mean
                continue
            e = np.linspace(a, b, max(2, int(np.ceil((b - a) / block_mw)) + 1))
            for u, v in zip(e[:-1], e[1:]):
                rows.append((i, u, v, float(np.interp((u + v) / 2, m, p, left=below)), 0.0))
    return pd.DataFrame(rows, columns=['res', 'lo', 'hi', 'price', 'slope'])


def variables(P, S, rules):
    B = S['B']
    P.add('energy', B.price.to_numpy(), (B.hi - B.lo).to_numpy(), B.slope.to_numpy())
    P.add('slack', [rules.shortage, -rules.surplus_price], [np.inf, np.inf])      # shortfall, surplus


def equation(P, S, demand):
    eq = np.zeros(P.n)
    eq[:len(S['B'])] = 1.0
    st = P.start('slack')
    eq[st], eq[st + 1] = 1.0, -1.0
    return eq, demand - S['lo'].sum()
