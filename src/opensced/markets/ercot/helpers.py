"""ERCOT's own calculations, for when you have the underlying numbers instead of ERCOT's published result.

A replay reads dispatch limits, proxy curves, proxy reserve offers and constraint caps straight from ERCOT's files. A
forecast has to build them. Each function here follows the Protocol paragraph named in its docstring and takes its
numbers from the rulebook, so a rule change is a rulebook change.

    dispatch_limits        ramp_low / ramp_high from output and ramp rates          6.5.7.2
    max_shadow_prices      a constraint's cap from its kind and voltage             Section 22 Attachment P
    proxy_energy_curves    offer curves for resources without a full curve          6.5.7.3(4)
    proxy_reserve_offers   the linked reserve offer for unoffered capacity          6.5.7.3(5)
    demand                 the demand to serve from ERCOT's demand target           6.5.7.3(3)
    generic_offer_caps     mitigated offer caps from the gas index price            4.4.9.4.1
    battery_efficiency     each battery's charging efficiency, off ERCOT's awards   3.7.1.3(1)(c)
"""
import numpy as np
import pandas as pd


def dispatch_limits(resources, rules):
    """Fill ramp_low and ramp_high (ERCOT's LDL and HDL) from where each resource is and how fast it can move.

    Needs columns output, low, high, ramp_up, ramp_down (MW per minute) and, when present, status and kind.
        generation, storage   high limit = min(output + ramp_up x minutes, high); low = max(output - ramp_down x minutes, low)
        SHUTDOWN              high limit = output - ramp_down x minutes
        STARTUP               low limit  = output + ramp_up x minutes
        ONHOLD (storage)      both 0;  ONTEST (storage): both held at output, inside low..high
        loads                 the same formulas on their negative output: ramping "down" consumes more
    minutes is rules.dispatch_minutes. -> a copy of the table."""
    r = resources.copy()
    m = rules.dispatch_minutes
    out, low, high = (pd.to_numeric(r[c], errors='coerce').to_numpy(float) for c in ('output', 'low', 'high'))
    up, dn = (pd.to_numeric(r[c], errors='coerce').to_numpy(float) for c in ('ramp_up', 'ramp_down'))
    status = r['status'].astype(str).str.upper().to_numpy() if 'status' in r else np.full(len(r), '')
    hi, lo = np.minimum(out + up * m, high), np.maximum(out - dn * m, low)
    hi = np.where(status == 'SHUTDOWN', out - dn * m, hi)
    lo = np.where(np.isin(status, ('STARTUP', 'STARTUP-NS')), out + up * m, lo)
    hold = np.clip(out, low, high)
    test, held = status == 'ONTEST', status == 'ONHOLD'
    hi, lo = np.where(test, hold, hi), np.where(test, hold, lo)
    hi, lo = np.where(held, 0.0, hi), np.where(held, 0.0, lo)
    r['ramp_high'], r['ramp_low'] = hi, lo
    return r


def max_shadow_prices(constraints, rules):
    """Fill max_shadow_price from each constraint's kind ('base' or 'contingency') and voltage, using
    rules.shadow_price_caps: the base-case cap, or the contingency cap for its voltage (above 200 kV, 100 to 200 kV,
    below 100 kV). A constraint with no voltage, or of another kind, gets rules.default_max_shadow_price.
    The higher caps ERCOT sets for irresolvable and stability-limit constraints are not computed here: give those
    directly. -> a copy of the table."""
    c = constraints.copy()
    caps = rules.shadow_price_caps
    kind = c['kind'].astype(str).str.lower() if 'kind' in c else pd.Series('contingency', index=c.index)
    kv = pd.to_numeric(c['kv'], errors='coerce') if 'kv' in c else pd.Series(np.nan, index=c.index)
    by_kv = np.select([kv > 200, kv >= 100, kv < 100], [caps.get('above_200kv'), caps.get('100_to_200kv'), caps.get('below_100kv')], default=np.nan).astype(float)
    cap = np.where(kind == 'base', caps.get('base', np.nan), np.where(kind == 'contingency', by_kv, np.nan)).astype(float)
    c['max_shadow_price'] = np.where(np.isfinite(cap), cap, rules.default_max_shadow_price)
    return c


def proxy_energy_curves(resources, energy_offers, rules, intermittent=('wind', 'pv')):
    """Give every dispatchable generator a full-range offer curve, as ERCOT does before SCED (6.5.7.3(4)).

        no curve, on an Output Schedule   low at the offer floor; the schedule one step above the floor; 1 MW above the
                                          schedule just under the offer cap; high at the offer cap        (4)(a)
        no curve, wind or solar           low at the offer floor; 1 MW below high one step above the floor;
                                          high at rules.irr_proxy_price                                   (4)(c)(i)
        a curve that stops short          extended flat from its top to high; 1 MW below its bottom one step above
                                          the floor, and low at the floor                                 (4)(b)
    Wind and solar are the resources whose `category` is in `intermittent`. Storage, controllable loads and
    RUC-committed resources have proxies of their own (6.5.7.3(4)(d), (6), (8), (9)) that are not built here.
    -> the energy_offers table with the proxy points added."""
    r = resources
    e = energy_offers if energy_offers is not None else pd.DataFrame(columns=['resource', 'mw', 'price'])
    floor, step, mw1, cap = rules.offer_floor, rules.proxy_price_step, rules.proxy_mw_step, rules.offer_cap
    if cap is None:
        raise ValueError('proxy_energy_curves needs rules.offer_cap')
    span = e.groupby('resource')['mw'].agg(['min', 'max']) if len(e) else pd.DataFrame(columns=['min', 'max'])
    top = e.sort_values('mw').groupby('resource')['price'].last() if len(e) else pd.Series(dtype=float)
    add = []
    for x in r.itertuples(index=False):
        if getattr(x, 'kind', 'generator') != 'generator' or not getattr(x, 'dispatchable', True):
            continue
        lo, hi, n = float(x.low), float(x.high), x.name
        if n not in span.index:
            sched = getattr(x, 'output_schedule', np.nan)
            if getattr(x, 'category', 'other') in intermittent:
                pts = [(lo, floor), (max(hi - mw1, lo), floor + step), (hi, rules.irr_proxy_price)]
            elif pd.notna(sched):
                pts = [(lo, floor), (float(sched), floor + step), (min(float(sched) + mw1, hi), cap - step), (hi, cap)]
            else:
                continue
        else:
            pts = []
            if hi > span.loc[n, 'max']:
                pts.append((hi, float(top[n])))
            if lo < span.loc[n, 'min']:
                pts += [(max(span.loc[n, 'min'] - mw1, lo), floor + step), (lo, floor)]
        add += [{'resource': n, 'mw': mw, 'price': p} for mw, p in pts]
    return pd.concat([e, pd.DataFrame(add)], ignore_index=True) if add else e


def proxy_reserve_offers(resources, reserve_offers, reserve_demand, rules, reserve_requirements=None, qualified=None):
    """Add ERCOT's proxy reserve offer for every resource (6.5.7.3(5)): one block linked across the products it is
    qualified for, sized at its high limit (high - low for storage, maximum consumption for loads).

    Price per product = the higher of
        the floor      the lesser of rules.proxy_reserve_cap and the demand curve's price at
                       rules.proxy_reserve_plan_share of the requirement, less rules.proxy_price_step
        its own        the resource's highest submitted price for that product, and for the products above it in the
                       order Reg-Up/RRS > ECRS > Non-Spin, the highest price of the ones below
    A RUC-committed resource (`ruc_committed`) is offered at the higher of its own highest price and
    rules.ruc_reserve_offer_price over its whole range (6.5.7.3(5)(e)).
    qualified: {resource: products}. Default: the products in reserve_limits are not known here, so every resource is
    taken as qualified for every product; pass it to narrow that. -> the reserve_offers table with a 'proxy' block each."""
    o = reserve_offers if reserve_offers is not None else pd.DataFrame(columns=['resource', 'block', 'mw', 'product', 'price'])
    need = {} if reserve_requirements is None else dict(zip(reserve_requirements['product'], reserve_requirements['mw']))
    floor = {}
    for d, c in reserve_demand.groupby('product'):
        c = c.sort_values('mw')
        plan = float(need.get(d, c['mw'].max()))
        floor[d] = min(rules.proxy_reserve_cap, float(np.interp(rules.proxy_reserve_plan_share * plan, c['mw'], c['price']))) - rules.proxy_price_step
    own = o.groupby(['resource', 'product'])['price'].max() if len(o) else pd.Series(dtype=float)
    names = [p.name for p in rules.products]
    below = {p.name: [q.name for q in rules.products[k + 1:] if q.direction == 'up'] if p.direction == 'up' else [] for k, p in enumerate(rules.products)}
    rows = []
    for x in resources.itertuples(index=False):
        kind = getattr(x, 'kind', 'generator')
        mw = float(x.high - x.low) if kind == 'storage' else float(getattr(x, 'max_consumption', np.nan)) if kind == 'load' else float(x.high)
        if not np.isfinite(mw) or mw <= 0:
            continue
        ruc = bool(getattr(x, 'ruc_committed', False))
        price = {}
        for p in reversed(names):                                        # bottom of the order first, so "below" is ready
            if qualified is not None and p not in qualified.get(x.name, ()):
                continue
            mine = own.get((x.name, p), np.nan)
            base = rules.ruc_reserve_offer_price if ruc else floor.get(rules.product(p).serves, np.nan)
            price[p] = np.nanmax([base, mine] + ([] if ruc else [price[q] for q in below[p] if q in price]))
        rows += [{'resource': x.name, 'block': 'proxy', 'mw': mw, 'product': p, 'price': v} for p, v in price.items() if np.isfinite(v)]
    return pd.concat([o, pd.DataFrame(rows)], ignore_index=True) if rows else o


def demand(gtbd, controllable_load_consumption=0.0):
    """The demand the clearing serves: ERCOT's Generation To Be Dispatched less what controllable loads consume
    (6.5.7.3(3)), because those loads are resources in the clearing. ERCOT does not publish GTBD or its formula."""
    return float(gtbd) - float(controllable_load_consumption)


def generic_offer_caps(resources, fuel_index_price, rules, after_2004=(), verifiable=None):
    """The mitigated offer cap ERCOT uses when it has nothing better (4.4.9.4.1): a generic heat rate times the fuel
    index price, the same at every output.

        fuel_index_price   $/MMBtu, the day's natural gas index price
        after_2004         names of resources that began commercial operation after January 1, 2004 (heat rate 14.5
                           instead of 10.5, from rules.generic_heat_rates)
        verifiable         optional table resource, mw, price: cost-based caps you know. The cap is the higher of the
                           two at each point. ERCOT's verifiable costs are confidential, so without this the result
                           is a lower bound on the true cap
    -> the mitigated_offer_caps table (resource, mw, price) for generators and storage."""
    hr = rules.generic_heat_rates
    late = set(after_2004)
    rows = []
    known = {} if verifiable is None else {n: g.sort_values('mw') for n, g in verifiable.groupby('resource')}
    for x in resources.itertuples(index=False):
        if getattr(x, 'kind', 'generator') == 'load':
            continue
        generic = hr['in_service_after_2004' if x.name in late else 'in_service_by_2004'] * float(fuel_index_price)
        if x.name in known:
            g = known[x.name]
            rows += [{'resource': x.name, 'mw': float(m), 'price': max(generic, float(p))} for m, p in zip(g['mw'], g['price'])]
        else:
            rows += [{'resource': x.name, 'mw': float(x.low), 'price': generic}, {'resource': x.name, 'mw': float(x.high), 'price': generic}]
    return pd.DataFrame(rows, columns=['resource', 'mw', 'price'])


def battery_efficiency(sced, rules=None, storage_types=('ESR',), min_runs=5, tolerance=0.0015):
    """Each battery's charging efficiency, read off ERCOT's own Reg-Down awards. -> Series resource -> share.

    Round Trip Efficiency is a registered Resource Parameter (3.7.1.3(1)(c)) that ERCOT does not publish. It shows in
    the awards: when state of charge is what holds a battery's Reg-Down award,

        efficiency x (Reg-Down duration x award + charging MW x interval) = soc_max - soc + discharging MW x interval

    so that ratio never falls below the battery's efficiency and keeps returning to it. A battery is given the lowest
    ratio it shows if at least `min_runs` runs sit on it; others are left out (the rulebook's default applies).
    `sced` is 60-Day SCED Disclosure rows for storage, one day or many. On seven days in 2026 this gives 107 of 157
    batteries a value, all between 0.81 and 1.0, the same on every day."""
    from opensced.markets.ercot import adapter, rulebooks
    x = adapter.normalize(sced)
    rules = rules or rulebooks.ALL.latest
    typ = x['Resource Type'].astype(str).str.strip() if 'Resource Type' in x else pd.Series('', index=x.index)
    x = x[typ.isin(storage_types).to_numpy() & (x['Telemetered Resource Status'].astype(str).str.strip() == 'ON').to_numpy()]
    need = ('SOC', 'maxSOC', 'ASAwardsREGDN', 'Base Point')
    if not len(x) or any(c not in x for c in need):
        return pd.Series(dtype=float, name='efficiency')
    n = lambda c: pd.to_numeric(x[c], errors='coerce').to_numpy(float)
    room, award, p = n('maxSOC') - n('SOC'), np.nan_to_num(n('ASAwardsREGDN')), np.nan_to_num(n('Base Point'))
    down = next(q for q in rules.products if q.direction == 'down')
    stp = rules.interval_hours
    ok = (award > 1.0) & (room > 0.05)
    ratio = (room + np.maximum(p, 0) * stp)[ok] / (down.duration_hours * award + np.maximum(-p, 0) * stp)[ok]
    d = pd.DataFrame({'resource': x[adapter.RES].to_numpy()[ok], 'ratio': ratio})
    low = d.groupby('resource').ratio.transform('min')
    at = d[(d.ratio - low) < tolerance].groupby('resource').ratio.agg(['size', 'min'])
    at = at[(at['size'] >= min_runs) & (at['min'] > 0.5) & (at['min'] <= 1.0 + tolerance)]
    return at['min'].clip(upper=1.0).round(4).rename('efficiency')


def qualified_mw(load_resources, rules=None, min_runs=3, tolerance=0.06):
    """The most of each reserve product a controllable Load Resource is qualified to carry, read off ERCOT's own
    awards. -> table resource, product, mw, for adapter.inputs(qualified_mw=...).

    The qualified amount is registration data ERCOT does not publish. It shows in the awards: with the clearing price
    above the load's own offer and above ERCOT's proxy offer, and room left to drop, the award stops at the same MW
    run after run, month after month, and steps up when the load grows (OB_ALD1 in 2026: Non-Spin 4.4 MW until April
    11, 12.2 MW from April 24, 27.7 MW by August 23). A load and product get the largest award in the rows given, if at
    least `min_runs` runs sit on it; others are left out and stay limited by telemetered capability alone.

    This is a lower bound: the largest award seen, which is the qualified amount only when the award was held by it.
    Give it many days, not one. `load_resources` is 60-Day SCED Load Resource rows, one day or many."""
    from opensced.markets.ercot import rulebooks
    rules = rules or rulebooks.ALL.latest
    L = load_resources.copy()
    L.columns = L.columns.str.strip()
    bid = pd.to_numeric(L['SCEDBidCurveMW1'], errors='coerce').notna() if 'SCEDBidCurveMW1' in L else pd.Series(False, index=L.index)
    L = L[bid.to_numpy()]                                               # controllable: it has a bid curve
    name = L['resourceName'].astype(str).str.strip()
    out = []
    for p in rules.products:
        cols = [c.replace('ASCap', 'ASAwards') for c in p.capability_columns if c.replace('ASCap', 'ASAwards') in L]
        if not cols or not len(L):
            continue
        a = sum(pd.to_numeric(L[c], errors='coerce').fillna(0.0) for c in cols)
        top = a.groupby(name).transform('max')
        at = ((a > top - tolerance) & (top > tolerance)).groupby(name).sum()
        g = a.groupby(name).max()[at >= min_runs]
        out.append(pd.DataFrame({'resource': g.index, 'product': p.name, 'mw': g.to_numpy(float)}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=['resource', 'product', 'mw'])


def offline_proxy_units(sced, reserve_offers, min_runs=1):
    """Units ERCOT awards Non-Spin through its proxy offer while they are OFF. -> sorted names, for
    adapter.inputs(offline_proxy=...).

    An off-line unit is normally awarded only the Non-Spin its QSE offered on an off-line (OFFNS) offer; a quick-start
    unit also gets ERCOT's proxy offer for the rest. A few other units get it too. Measured on 22 days: nine units were
    awarded Non-Spin while OFF with no off-line offer of their own, on 104 of the 122 unit-runs where the proxy price was
    under the clearing price; 78 other units in the same position were never awarded on 4,136 unit-runs. Which units
    is not published, so they are read off the awards: a unit is named when, in at least `min_runs` runs, it is OFF,
    awarded Non-Spin, and its off-line offer row has no Non-Spin price in the blocks a QSE submits (1 to 5).
    `sced` is 60-Day SCED generation rows and `reserve_offers` the 60-Day reserve offers of the same runs."""
    from opensced.markets.ercot import adapter
    s = adapter.normalize(sced)
    st = s['Telemetered Resource Status'].astype(str).str.strip().str.upper()
    won = pd.to_numeric(s['ASAwardsNSPIN'], errors='coerce').fillna(0.0) > 0.05 if 'ASAwardsNSPIN' in s else pd.Series(False, index=s.index)
    a = s.loc[(st == 'OFF') & won, [adapter.TS, adapter.RES]].copy()
    if not len(a):
        return []
    a.columns = ['t', 'n']
    a['t'], a['n'] = pd.to_datetime(a['t']).dt.floor('5min'), a['n'].astype(str).str.strip()
    o = adapter.offer_columns(reserve_offers)
    o = o[o['resourceName'].astype(str).str.strip().isin(set(a['n']))].copy()
    if 'offerType' in o and o['offerType'].notna().any():
        o = o[o['offerType'].astype(str).str.strip() == 'OFFNS']
    else:                                                               # files of December 2025 with no offer type
        o = o.assign(offerType=adapter._offer_types(o.rename(columns={'resourceName': 'resource', 'offerType': 'offer_type'})).to_numpy())
        o = o[o['offerType'] == 'OFFNS']
    own = np.zeros(len(o), bool)
    for k in range(1, 6):
        if f'price{k}NSPIN' in o and f'quantityMW{k}' in o:
            own |= (pd.to_numeric(o[f'price{k}NSPIN'], errors='coerce').notna() & (pd.to_numeric(o[f'quantityMW{k}'], errors='coerce') > 0)).to_numpy()
    o = pd.DataFrame({'t': pd.to_datetime(o['SCEDTimestamp']).dt.floor('5min').to_numpy(), 'n': o['resourceName'].astype(str).str.strip().to_numpy(), 'own': own})
    m = a.merge(o.groupby(['t', 'n'], as_index=False)['own'].max(), on=['t', 'n'], how='left')
    m['own'] = m['own'].fillna(False).astype(bool)                      # no off-line row at all: nothing of its own either
    n = m[~m['own']].groupby('n').size()
    return sorted(n[n >= min_runs].index)
