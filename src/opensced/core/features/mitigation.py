"""Offer mitigation: the two-step clearing some markets run to stop a resource from setting a high price where it
faces no competition.

    step 1   clear with the competitive constraints only. Each resource's price in this run is its reference price.
    step 2   clear with every constraint, after adjusting the energy offer curves:
               floor   every curve's prices are raised to the lesser of the resource's reference price and the
                       mitigated offer floor for its category (rules.mitigated_offer_floors)
               cap     for a resource marked `mitigated`, prices are lowered to the greater of
                         reference price + rules.mitigation_adder_share x its mitigated offer cap at its low limit
                         its mitigated offer cap at that output (inputs.mitigated_offer_caps)
                       With no mitigated offer cap given for it, the cap is the reference price.
             Loads are not mitigated.

Which constraints are competitive (constraints.competitive) and which resources are mitigated in the interval
(resources.mitigated) are inputs: the market's competitiveness test is not run here.
"""
import numpy as np
import pandas as pd


def competitive_only(inputs):
    """the inputs with the non-competitive constraints left out: what step 1 sees."""
    c = inputs.constraints
    if c is None or 'competitive' not in c or c['competitive'].fillna(True).all():
        return inputs
    keep = c[c['competitive'].fillna(True).astype(bool)].reset_index(drop=True)
    return inputs.copy(constraints=keep if len(keep) else None)


def clip_curve(mw, price, floor=-np.inf, cap=None):
    """Hold an offer curve between a floor and a cap, cutting it exactly where it crosses either.

    mw, price   the curve's points (linear in price between them)
    floor       $/MWh
    cap         None, one number, or (mw points, prices) for a cap that varies with output
    -> (mw, price) with a point added at every crossing, so the result is the true clipped curve and not just the
    original points pulled to the bounds."""
    o = np.argsort(mw, kind='stable')
    m, p = np.asarray(mw, float)[o], np.asarray(price, float)[o]
    if cap is None:
        hi = lambda x: np.full(np.shape(x), np.inf)
    elif np.isscalar(cap):
        hi = lambda x: np.full(np.shape(x), float(cap))
    else:
        cm, cp = np.asarray(cap[0], float), np.asarray(cap[1], float)
        inside = cm[(cm > m[0]) & (cm < m[-1])]                           # the cap's own corners become curve points
        if len(inside):
            p = np.r_[p, np.interp(inside, m, p)]
            m = np.r_[m, inside]
            o = np.argsort(m, kind='stable')
            m, p = m[o], p[o]
        hi = lambda x: np.interp(x, cm, cp)
    xs, ps = [m[0]], [p[0]]
    for k in range(len(m) - 1):
        a, b, pa, pb = m[k], m[k + 1], p[k], p[k + 1]
        if b > a:
            cuts = []
            if np.isfinite(floor) and (pa - floor) * (pb - floor) < 0:
                cuts.append(a + (floor - pa) / (pb - pa) * (b - a))
            da, db = pa - hi(a), pb - hi(b)
            if np.isfinite(da) and np.isfinite(db) and da * db < 0:
                cuts.append(a + da / (da - db) * (b - a))
            for x in sorted(cuts):
                xs.append(x); ps.append(pa + (pb - pa) * (x - a) / (b - a))
        xs.append(b); ps.append(pb)
    xs, ps = np.array(xs), np.array(ps)
    return xs, np.maximum(np.minimum(ps, hi(xs)), floor)


def mitigate(inputs, reference_prices, rules):
    """-> the energy_offers table for step 2. reference_prices: Series resource -> $/MWh from step 1."""
    e = inputs.energy_offers
    if e is None or not len(e):
        return e
    r = inputs.resources.set_index('name')
    kind = (r['kind'] if 'kind' in r else pd.Series('generator', index=r.index)).to_dict()
    cat = (r['category'] if 'category' in r else pd.Series('other', index=r.index)).fillna('other').to_dict()
    flagged = set(r.index[r['mitigated'].fillna(False).astype(bool)]) if 'mitigated' in r else set()
    low = r['low'].to_dict()
    floors = rules.mitigated_offer_floors
    other = floors.get('other', -np.inf)
    M = inputs.mitigated_offer_caps
    caps = {} if M is None else {n: (g['mw'].to_numpy(float), g['price'].to_numpy(float)) for n, g in M.sort_values('mw').groupby('resource')}
    ref = reference_prices.to_dict()
    out = []
    for n, g in e.groupby('resource', sort=False):
        mw, price = pd.to_numeric(g['mw']).to_numpy(float), pd.to_numeric(g['price']).to_numpy(float)
        rp = ref.get(n, np.nan)
        if kind.get(n) == 'load' or not np.isfinite(rp) or len(mw) < 1:   # loads are not mitigated
            out.append(pd.DataFrame({'resource': n, 'mw': mw, 'price': price}))
            continue
        floor = min(rp, floors.get(cat.get(n, 'other'), other))
        cap = None
        if n in flagged:
            if n in caps:
                cm, cp = caps[n]
                cap = (cm, np.maximum(rp + rules.mitigation_adder_share * float(np.interp(low[n], cm, cp)), cp))
            else:
                cap = rp
        m2, p2 = clip_curve(mw, price, floor, cap)
        out.append(pd.DataFrame({'resource': n, 'mw': m2, 'price': p2}))
    return pd.concat(out, ignore_index=True)
