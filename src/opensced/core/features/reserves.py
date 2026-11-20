"""Reserves cleared together with energy.

  variables   r[i, s]   MW of product s awarded to resource i (up to its reserve limit)
              z[j, s]   MW of offer block j used for product s          (when reserve offers are given)
              q[s, k]   MW bought on segment k of product s's demand curve
  objective   + offer price x z   - demand curve price x q
  rows        ramp        p + share x regulation-up   <= ramp_high        (rules.regulation_share)
                          p - share x regulation-down >= ramp_low
              headroom    p + all up awards           <= high   (or the top of the dispatch range, if that is higher)
                          p - all down awards         >= low    (or the bottom of the dispatch range, if lower)
              offers      sum over products of z[j]   <= block MW  (one MW serves one product)
                          r[i, s]                      = sum of z over i's blocks for s
              demand      sum of q[d]                 <= sum of r[., s] over the products s serving demand curve d
                                                                  (its dual is the clearing price)
              reserved    when a product has reserved_mw of its demand curve, the other products serving that curve
                          together get at most the curve's total MW less the reserved MW
              limits      rules.limits: the awards of a group of products, from all or some resources, add up to
                          at most a number of MW, a share of a requirement, or a requirement less a number of MW

Without reserve offers every resource with a limit may carry the product at $0.
"""
import numpy as np
import pandas as pd


def limits(S, inputs, rules):
    """-> {product: MW array over resources}, zero where a resource may not carry it; and the offer blocks
    [(resource index, MW, {product: price})] or None."""
    n, at = S['n'], S['at']
    cap = {p: np.zeros(n) for p in rules.product_names}
    L = inputs.reserve_limits
    if L is not None and len(L):
        i = L['resource'].map(at)
        ok = i.notna().to_numpy() & L['product'].isin(cap).to_numpy()
        for p, g in pd.DataFrame({'i': i[ok].astype(int).to_numpy(), 'p': L['product'][ok].to_numpy(),
                                  'mw': pd.to_numeric(L['mw'])[ok].to_numpy(float)}).groupby('p', sort=False):
            cap[p][g.i.to_numpy()] = np.maximum(np.nan_to_num(g.mw.to_numpy()), 0.0)
    O, OB = inputs.reserve_offers, None
    if O is not None:
        OB = []
        o = O[O['resource'].isin(at) & O['product'].isin(cap)]
        o = o[(pd.to_numeric(o['mw']) > 0) & np.isfinite(pd.to_numeric(o['price']))]
        for (res, _), g in o.groupby(['resource', 'block'], sort=False):
            OB.append((at[res], float(g['mw'].iloc[0]), dict(zip(g['product'], g['price'].astype(float)))))
        for p in cap:
            offered = np.zeros(n, bool)
            offered[[i for i, _, pr in OB if p in pr]] = True
            cap[p] = np.where(offered, cap[p], 0.0)
    return cap, OB


def segments(curve, pricing='mean'):
    """One product's demand curve points (mw, price) -> segments (width, price): the mean price over each stretch."""
    c = curve.sort_values('mw')
    q, p = pd.to_numeric(c['mw']).to_numpy(float), pd.to_numeric(c['price']).to_numpy(float)
    if len(q) and q[0] > 0:                                              # the first point holds from 0
        q, p = np.r_[0.0, q], np.r_[p[0], p]
    w, pr = q[1:] - q[:-1], ((p[:-1] + p[1:]) / 2 if pricing == 'mean' else p[:-1])
    return w[w > 0], pr[w > 0]


def award_variables(P, S, rules):
    S['rv'] = {}
    for p in rules.product_names:
        idx = np.where(S['cap'][p] > rules.tolerance_mw)[0]
        S['rv'][p] = idx
        P.add(f'r_{p}', np.full(len(idx), 0.0 if S['OB'] is not None else rules.no_reserve_offer_price), S['cap'][p][idx])


def offer_variables(P, S, rules):
    S['zv'] = []                                                         # (block, product, resource, price) per z
    if S['OB'] is None:
        return
    rset = {p: set(S['rv'][p]) for p in S['rv']}
    for j, (i, _, pr) in enumerate(S['OB']):
        for p, price in pr.items():
            if i in rset[p]:
                S['zv'].append((j, p, i, max(price, rules.reserve_offer_floor)))
    P.add('z', [z[3] for z in S['zv']], np.full(len(S['zv']), np.inf))


def demand_variables(P, S, inputs, rules):
    """the demand curves; and each curve's requirement: inputs.reserve_requirements, else the curve's total MW."""
    D = inputs.reserve_demand
    S['need'] = {}
    given = {} if inputs.reserve_requirements is None else dict(zip(inputs.reserve_requirements['product'], pd.to_numeric(inputs.reserve_requirements['mw'])))
    for d in rules.demand_names:
        w, pr = segments(D[D['product'] == d], rules.demand_curve_pricing)
        S['need'][d] = float(given.get(d, w.sum()))
        P.add(f'q_{d}', -pr, w)


def rcol(P, S, p, i):
    """index of the award variable of resource i for product p, or None."""
    rv = S['rv'][p]
    j = np.searchsorted(rv, i)
    return P.start(f'r_{p}') + j if j < len(rv) and rv[j] == i else None


def resource_rows(P, S, rules):
    up = [p.name for p in rules.products if p.direction == 'up']
    down = [p.name for p in rules.products if p.direction == 'down']
    reg_up = [p.name for p in rules.products if p.direction == 'up' and p.regulation]
    reg_down = [p.name for p in rules.products if p.direction == 'down' and p.regulation]
    share = rules.regulation_share
    have = set().union(*[set(v) for v in S['rv'].values()]) if S['rv'] else set()
    for i in sorted(have):
        bl = list(S['blocks_of'].get(i, ()))
        lo, hdl, ldl, hsl, lsl = S['lo'][i], S['ramp_high'][i], S['ramp_low'][i], S['high'][i], S['low'][i]
        for p in reg_up:
            r = rcol(P, S, p, i)
            if r is not None:
                P.row(bl + [r], [1.0] * len(bl) + [share], hdl - lo)
        for p in reg_down:
            r = rcol(P, S, p, i)
            if r is not None:
                P.row(bl + [r], [-1.0] * len(bl) + [share], lo - ldl)
        ups = [c for c in (rcol(P, S, p, i) for p in up) if c is not None]
        if ups:                                                          # a held resource carries reserves only
            P.row(bl + ups, [1.0] * (len(bl) + len(ups)), max(hsl, S['hi'][i]) - lo)   # never tighter than the dispatch range
        downs = [c for c in (rcol(P, S, p, i) for p in down) if c is not None]
        if downs:
            P.row(bl + downs, [-1.0] * len(bl) + [1.0] * len(downs), lo - min(lsl, lo))


def offer_rows(P, S):
    if not S['zv']:
        return
    zst = P.start('z')
    by_block, by_award = {}, {}
    for k, (j, p, i, _) in enumerate(S['zv']):
        by_block.setdefault(j, []).append(zst + k)
        by_award.setdefault((i, p), []).append(zst + k)
    for j, zs in by_block.items():
        P.row(zs, [1.0] * len(zs), S['OB'][j][1])
    for (i, p), zs in by_award.items():                                  # an award is exactly the offer MW used for it:
        r = rcol(P, S, p, i)                                             # with "at most", a block priced below zero (self-
        P.row([r] + zs, [1.0] + [-1.0] * len(zs), 0.0)                   # provided reserves) could be counted as used, and
        P.row([r] + zs, [-1.0] + [1.0] * len(zs), 0.0)                   # its price collected, with nothing awarded


def demand_rows(P, S, inputs, rules):
    S['reserve_rows'] = {}
    for d in rules.demand_names:
        qs, qn = P.var[f'q_{d}']
        cols = [c for p in rules.serving(d) for c in range(P.var[f'r_{p}'][0], sum(P.var[f'r_{p}']))]
        S['reserve_rows'][d] = P.row(list(range(qs, qs + qn)) + cols, [1.0] * qn + [-1.0] * len(cols), 0.0)
    V = inputs.limit_values                                              # this interval's own numbers for named limits
    V = {} if V is None else {r['limit']: r for r in V.to_dict('records')}
    own = lambda name, key, default: default if name not in V or pd.isna(V[name].get(key, np.nan)) else float(V[name][key])
    for p in rules.products:                                             # MW of a demand curve only one product may fill
        kept = own(p.name, 'min_mw', p.reserved_mw)
        if kept > 0:
            cols = [c for o in rules.serving(p.serves) if o != p.name for c in range(P.var[f'r_{o}'][0], sum(P.var[f'r_{o}']))]
            if cols:
                P.row(cols, [1.0] * len(cols), max(S['need'][p.serves] - kept, 0.0))
    for lim in rules.limits:                                             # caps and floors on groups of products
        ok = np.ones(S['n'], bool)
        for col, val in lim.where:
            ok &= (S['table'][col].to_numpy() == val) if col in S['table'] else False
        cols = [P.start(f'r_{p}') + k for p in lim.products if p in S['rv'] for k, i in enumerate(S['rv'][p]) if ok[i]]
        share = lambda x: None if x is None else x * S['need'][lim.of]
        less = None if lim.max_less is None else max(S['need'][lim.of] - lim.max_less, 0.0)
        hi = [v for v in (own(lim.name, 'max_mw', lim.max_mw), share(lim.max_share), less) if v is not None]
        lo = [v for v in (own(lim.name, 'min_mw', lim.min_mw), share(lim.min_share)) if v is not None]
        if cols and hi:
            P.row(cols, [1.0] * len(cols), min(hi))
        if lo:
            P.row(cols, [-1.0] * len(cols), -max(lo))
