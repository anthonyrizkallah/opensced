"""ERCOT: public reports -> opensced input tables.

Everything here reads files anyone can download from ERCOT (data.ercot.com or the public API). Nothing else is
needed, except the two inputs ERCOT does not publish, which you bring yourself:

    shift_factors    constraint x settlement point
    resource_nodes   resource -> settlement point

The reports, by the file name read_day() looks for (the name of the report's API endpoint):

    60_sced_gen_res_data          60-Day SCED Disclosure, generation resources     NP3-965-ER   required
    60d_sced_esr_data             60-Day SCED Disclosure, storage resources        NP3-965-ER   required
    60d_sced_resource_as_offers   60-Day SCED Disclosure, reserve offers           NP3-965-ER
    60_load_res_data_in_sced      60-Day SCED Disclosure, Load Resources           NP3-965-ER
    dam_sced_as_demand_curves     Ancillary Service Demand Curves                  NP4-212-CD   every point, as posted
    dam_as_plan                   DAM Ancillary Service Plan                       NP4-33-CD    the hourly requirements
    shdw_prices_bnd_trns_const    SCED Shadow Prices and Binding Constraints       NP6-86-CD
    lmp_node_zone_hub             LMPs by Resource Node, Load Zone and Hub         NP6-788-CD   for scoring
    sced_system_lambda            SCED System Lambda                               NP6-322-CD   for scoring
    rt_clear_price_cap_sced       Real-Time Clearing Prices for Capacity           NP6-332-CD   for scoring
    2day_agg_sced_as_offers       2-Day Aggregate SCED Ancillary Service Offers    NP3-906-EX   days before Feb 3, 2026
    reference_sced_resource_as_offers   the same disclosure for a day on or after Feb 3, 2026 (optional, with the line above)
                                  (the nine product files in one table, with a `product` column)

Each may be a .parquet or .csv file (optionally .csv.gz) holding one operating day, with ERCOT's own column names.
Both of ERCOT's naming styles are understood ("Base Point" from the website's files, "basePoint" from the API).

How a SCED run becomes the tables
    status      a resource SCED can move (telemetered status in DISPATCHABLE, which includes units on an Output Schedule
                and off-line quick-start units) is dispatchable. Anything else is held at its base point.
    limits      low / high are LSL / HSL; ramp_low / ramp_high are LDL / HDL; output is the base point.
    offers      the SCED2 curve: the curve SCED dispatched on, after mitigation, including the proxy curves ERCOT
                builds for resources without a full curve (6.5.7.3(4) and (6)). If a file has no curve for a
                dispatchable resource it gets the wind and solar proxy: free to 1 MW below its ceiling, then $1,500.
    reserves    limits are the disclosed capabilities times the rulebook's minutes of ramp. RRS is three products
                (RRS-PFR, RRS-FFR, RRS-UFR), each with its own capability and offer price, serving one RRS demand curve.
                Offers come from the reserve offer disclosure, including ERCOT's proxy offer for unoffered capacity.
                On-line resources offer through ONRES and REGDN blocks, off-line ones through OFFNS; an off-line
                unit may carry Non-Spin only, a quick-start unit ECRS and Non-Spin, a synchronous condenser RRS and ECRS.
    loads       a non-controllable Load Resource is a resource of kind 'load' that carries reserves up to the
                consumption it can drop. A controllable one is dispatched as negative output on its bid-to-buy curve.
                What either self-arranged is offered at $0, so it is taken first.
    demand      the sum of the run's base points (what SCED dispatched), less what controllable loads consume.
    constraints every constraint ERCOT reported in the run, with its reported flow, limit and maximum shadow price.
"""
import os

import numpy as np
import pandas as pd

from opensced.core.tables import Inputs
from opensced.markets.ercot.rulebooks import ALL

TS, RES, REP = 'SCED Time Stamp', 'Resource Name', 'Repeated Hour Flag'
NPT = 35                                                               # points on an offer curve
STORAGE_TYPES = ('ESR', 'PWRSTR')
# ERCOT's resource type -> the category its mitigated offer floor is set by (Protocols 4.4.9.4.2). Whether a unit is a
# Qualifying Facility is not in the disclosure: pass categories={resource: 'qf'} for those.
CATEGORY = {'NUC': 'nuclear', 'HYDRO': 'hydro', 'CLLIG': 'coal', 'CCGT90': 'combined_cycle', 'CCLE90': 'combined_cycle',
            'SCGT90': 'gas_steam_ct', 'SCLE90': 'gas_steam_ct', 'GSREH': 'gas_steam_ct', 'GSNONR': 'gas_steam_ct',
            'GSSUP': 'gas_steam_ct', 'DSL': 'gas_steam_ct', 'WIND': 'wind', 'PVGR': 'pv', 'ESR': 'esr', 'PWRSTR': 'esr'}
ZERO_FILL_END = pd.Timestamp('2026-02-03')                             # before this, ERCOT wrote unpriced cells as 0
PRODUCT = {'REGUP': 'RegUp', 'REGDN': 'RegDown', 'RRS': 'RRS', 'ECRS': 'ECRS', 'NSPIN': 'NonSpin'}   # demand curve names
# ERCOT's aggregate reserve offer curves (NP3-906-EX): aggregate product -> (rulebook product, price column, who offers it)
AGGREGATE = {'REGUP': ('RegUp', 'REGUP', 'resource'), 'REGDN': ('RegDown', 'REGDN', 'resource'), 'RRSPFR': ('RRS-PFR', 'RRSPFR', 'resource'),
             'RRSFFR': ('RRS-FFR', 'RRSFFR', 'any'), 'RRSUFR': ('RRS-UFR', 'RRSUFR', 'load'), 'ECRSS': ('ECRS', 'ECRS', 'resource'),
             'ECRSM': ('ECRS', 'ECRS', 'load'), 'NSPIN': ('NonSpin', 'NSPIN', 'resource'), 'NSPNM': ('NonSpin', 'NSPIN', 'load')}
GEN_CAPABILITY = ('ASCapREGUP', 'ASCapREGDN', 'ASCapRRSPFR', 'ASCapRRSFFR', 'ASCapECRS', 'ASCapNSPIN')   # in the generation and storage files
MCPC = {'REGUP': 'RegUp', 'REGDN': 'RegDown', 'RRS': 'RRS', 'ECRS': 'ECRS', 'NSPIN': 'NonSpin'}

CANON = {
    'SCEDTimestamp': TS, 'SCED Timestamp': TS, 'repeatHourFlag': REP, 'repeatedHourFlag': REP,
    'resourceName': RES, 'resourceType': 'Resource Type',
    'telemeteredResourceStatus': 'Telemetered Resource Status', 'telemeteredNetOutput': 'Telemetered Net Output',
    'basePoint': 'Base Point', 'Ramp Rate Up': 'rampRateUp', 'Ramp Rate Down': 'rampRateDown', 'Normal Ramp Rate Up': 'rampRateUp',
    'Normal Ramp Rate Down': 'rampRateDown',
    **{f'SCED{n} Curve-{k}{i}': f'SCED{n}Curve{k}{i}' for n in (1, 2) for k in ('MW', 'Price') for i in range(1, NPT + 1)},
    **{f'AS Awards {a}': f'ASAwards{a}' for a in ('ECRS', 'NSPIN', 'REGDN', 'REGUP', 'RRSFFR', 'RRSPFR', 'RRSUFR')},
}
FILES = {'gen': '60_sced_gen_res_data', 'esr': '60d_sced_esr_data', 'reserve_offers': '60d_sced_resource_as_offers',
         'load_resources': '60_load_res_data_in_sced', 'reserve_demand': 'dam_sced_as_demand_curves', 'reserve_plan': 'dam_as_plan',
         'constraints': 'shdw_prices_bnd_trns_const', 'lmp': 'lmp_node_zone_hub', 'system_lambda': 'sced_system_lambda',
         'reserve_prices': 'rt_clear_price_cap_sced', 'aggregate_offers': '2day_agg_sced_as_offers',
         'reference_offers': 'reference_sced_resource_as_offers'}


# ---------------------------------------------------------------- the SCED disclosure
def _merge_collisions(df):
    """Columns that share a name after renaming: keep the first non-null value per row."""
    if not df.columns.duplicated().any():
        return df
    out = {}
    for name in dict.fromkeys(df.columns):
        block = df.loc[:, df.columns == name]
        out[name] = block.iloc[:, 0] if block.shape[1] == 1 else block.bfill(axis=1).iloc[:, 0]
    return pd.DataFrame(out, index=df.index)


def normalize(df):
    """The SCED disclosure with one set of column names; one row per resource and SCED run."""
    df = df.copy()
    df.columns = df.columns.str.strip()
    df = _merge_collisions(df)
    df = _merge_collisions(df.rename(columns={k: v for k, v in CANON.items() if k in df.columns}))
    if RES not in df or TS not in df:
        raise ValueError(f'this does not look like the 60-Day SCED Disclosure: no resource name or SCED timestamp column. '
                         f'Columns start: {list(df.columns[:6])}')
    df[TS] = pd.to_datetime(df[TS], errors='coerce')
    df[RES] = df[RES].astype(str).str.strip()
    return df.drop_duplicates(subset=[c for c in (RES, TS, REP) if c in df.columns])


def _num(x, c):
    return pd.to_numeric(x[c], errors='coerce').to_numpy(float) if c in x else np.full(len(x), np.nan)


def _flag(s):
    return s.astype(str).str.strip().str.upper().isin(['TRUE', 'Y', '1']).to_numpy()


def _run_rows(df, when, ts_col):
    """rows of a per-run report at the run `when`: the same SCED timestamp, else the same 5-minute interval."""
    t, w = pd.to_datetime(df[ts_col], errors='coerce'), pd.Timestamp(when)
    exact = (t == w).to_numpy()
    return df[exact] if exact.any() else df[(t.dt.floor('5min') == w.floor('5min')).to_numpy()]


def _sced_tables(x, rules, storage_types=STORAGE_TYPES, curve_points=NPT, curve='SCED2'):
    """generation and storage rows of one run -> resources, energy_offers, storage, reserve_limits, flags."""
    x = x.reset_index(drop=True)
    names = x[RES].to_numpy()
    status = x['Telemetered Resource Status'].astype(str).str.strip().str.upper().to_numpy()
    typ = x['Resource Type'].astype(str).str.strip().to_numpy() if 'Resource Type' in x else np.full(len(x), '')
    ldl, hdl, lsl, hsl = (_num(x, c) for c in ('LDL', 'HDL', 'LSL', 'HSL'))
    bp = np.nan_to_num(_num(x, 'Base Point'))
    if rules.dispatch_limits == 'ramp':                                  # SCED moves a resource between LDL and HDL
        lo, hi = np.where(np.isfinite(ldl), ldl, lsl), np.where(np.isfinite(hdl), hdl, hsl)
    else:
        lo, hi = np.fmax(ldl, lsl), np.fmin(hdl, hsl)
    can = {st.name for st in rules.statuses if st.dispatchable}
    held = {st.name for st in rules.statuses if not st.dispatchable and st.reserves}
    disp = np.isin(status, list(can)) & np.isfinite(lo) & np.isfinite(hi) & (hi >= lo)
    off = np.isin(status, list(held)) & np.isfinite(hsl)
    fill = lambda a, b: np.where(np.isfinite(a), a, np.where(np.isfinite(b), b, bp))
    low, high = fill(lsl, ldl), fill(hsl, hdl)
    high = np.maximum(high, low)
    storage_kind = np.isin(typ, storage_types)
    resources = pd.DataFrame({'name': names, 'low': low, 'high': high, 'ramp_low': fill(ldl, lsl), 'ramp_high': fill(hdl, hsl),
                              'output': bp, 'dispatchable': disp, 'kind': np.where(storage_kind, 'storage', 'generator'),
                              'type': typ, 'status': status, 'category': [CATEGORY.get(t, 'other') for t in typ],
                              'ramp_up': _num(x, 'rampRateUp'), 'ramp_down': _num(x, 'rampRateDown'),
                              'telemetered': _num(x, 'Telemetered Net Output')})
    if f'{curve}CurveMW1' not in x:
        raise ValueError(f'the SCED table has no {curve} offer curve columns ({curve}CurveMW1, {curve}CurvePrice1, ...)')
    M = np.column_stack([_num(x, f'{curve}CurveMW{j}') for j in range(1, curve_points + 1)])
    Pr = np.column_stack([_num(x, f'{curve}CurvePrice{j}') for j in range(1, curve_points + 1)])
    tol = rules.tolerance_mw
    ok = np.isfinite(M) & np.isfinite(Pr) & (disp & (hi - lo > tol))[:, None]
    ri, _ = np.where(ok)
    offers = pd.DataFrame({'resource': names[ri], 'mw': M[ok], 'price': Pr[ok]})
    bare = np.where(disp & (hi - lo > tol) & ~ok.any(axis=1))[0]         # no curve: the wind and solar proxy, 6.5.7.3(4)(c)
    if len(bare):
        a, b = np.fmax(ldl, lsl)[bare], np.fmin(hdl, hsl)[bare]         # the proxy is anchored on LSL and HSL, inside the range
        proxy = pd.DataFrame({'resource': np.repeat(names[bare], 3),
                              'mw': np.c_[a, np.maximum(b - rules.proxy_mw_step, a), b].ravel(),
                              'price': np.tile((rules.offer_floor, rules.offer_floor + rules.proxy_price_step, rules.irr_proxy_price), len(bare))})
        offers = pd.concat([offers, proxy], ignore_index=True)
    soc, smin, smax = _num(x, 'SOC'), _num(x, 'minSOC'), _num(x, 'maxSOC')
    s = storage_kind & np.isfinite(soc)
    storage = pd.DataFrame({'resource': names[s], 'soc': soc[s], 'soc_min': np.nan_to_num(smin[s]), 'soc_max': np.where(np.isfinite(smax[s]), smax[s], soc[s])})
    lim = []
    for p in rules.products:
        cap = sum(np.nan_to_num(_num(x, c)) for c in p.capability_columns) * (p.ramp_minutes or 1.0)
        cap = cap + np.zeros(len(x))
        keep = (cap > 0) & (disp | off)
        lim.append(pd.DataFrame({'resource': names[keep], 'product': p.name, 'mw': cap[keep]}))
    return resources, offers, storage, pd.concat(lim, ignore_index=True), dict(zip(names, status)), dict(zip(names, disp))


def _offer_types(o):
    """the offer type of each row of the reserve offer disclosure: ONRES, REGDN or OFFNS.

    ERCOT left the offerType column empty in the first weeks of RTC+B (seen on December 14, 2025). Block 6, ERCOT's
    proxy offer, still tells the rows apart: it is priced for Reg-Down alone on a REGDN row, for Non-Spin alone on an
    OFFNS row, and for the other products on an ONRES row. On three days that have the column (January 25, January 28,
    February 24, 2026; 4.6 million rows) this recovers it with no row wrong."""
    given = o['offer_type'].astype(str).str.strip()
    missing = o['offer_type'].isna().to_numpy() | given.isin(['', 'None', 'nan', 'NaN']).to_numpy()
    if not missing.any():
        return given
    on = {}
    for c in o.columns:
        if c.startswith('price6'):
            v = pd.to_numeric(o[c], errors='coerce').to_numpy(float)
            on[c[6:]] = np.isfinite(v) & (v != 0)
    other = np.zeros(len(o), bool)
    for q, m in on.items():
        if q not in ('REGDN', 'NSPIN'):
            other |= m
    dn, ns = on.get('REGDN', np.zeros(len(o), bool)), on.get('NSPIN', np.zeros(len(o), bool))
    found = np.where(other, 'ONRES', np.where(dn & ~ns, 'REGDN', np.where(ns & ~dn, 'OFFNS', '')))
    out = np.where(missing, found, given.to_numpy())
    lost = missing & (out == '')
    if lost.any():
        offered = np.zeros(len(o), bool)
        for k in range(1, 6):
            if f'quantityMW{k}' in o:
                offered |= pd.to_numeric(o[f'quantityMW{k}'], errors='coerce').fillna(0).to_numpy() > 0
        if (lost & offered).any():
            raise ValueError(f'reserve_offers: {int((lost & offered).sum()):,} rows have no offerType and no proxy block to tell it '
                             f'from, e.g. {o["resource"].to_numpy()[lost & offered][0]!r}')
    return pd.Series(out, index=o.index)


def zero_offer_habits(reference):
    """A day of the reserve offer disclosure on which blanks are real (February 3, 2026 or later) -> the cells that
    held a genuine $0 offer: resource, offer_type, product (ERCOT's column name), block, hour. Used as evidence of
    which zero-filled cells of an earlier day were real offers (see _reserve_offers)."""
    r = reference.rename(columns={'resourceName': 'resource', 'offerType': 'offer_type'})
    cols = [c for c in r.columns if c.startswith('price') and c[5:6] in '12345']
    if not len(cols) or not r[cols].isna().to_numpy().any():
        raise ValueError('reference_offers: this file has no blank prices, so its zeros cannot be told from blanks. Use a day on '
                         'or after 2026-02-03')
    hour = pd.to_datetime(r['SCEDTimestamp']).dt.hour.to_numpy()
    name, kind = r['resource'].astype(str).str.strip().to_numpy(), _offer_types(r).to_numpy()
    out = []
    for c in cols:
        k = int(c[5])
        m = (pd.to_numeric(r[c], errors='coerce') == 0).to_numpy() & (pd.to_numeric(r[f'quantityMW{k}'], errors='coerce') > 0).to_numpy()
        if m.any():
            out.append(pd.DataFrame({'resource': name[m], 'offer_type': kind[m], 'product': c[6:], 'block': k, 'hour': hour[m]}).drop_duplicates())
    return pd.concat(out, ignore_index=True).drop_duplicates() if out else pd.DataFrame(columns=['resource', 'offer_type', 'product', 'block', 'hour'])


def _reserve_offers(o, status, when, rules, zero_price_is_blank=None, aggregate=None, loads=None, habits=None):
    """the run's rows of the reserve offer disclosure -> the reserve_offers table.

    Each row holds up to six blocks. Blocks 1-5 are what the QSE submitted. Block 6 is ERCOT's proxy offer
    (6.5.7.3(5)): the rest of the resource's capacity, linked across every product it is qualified for, priced at the
    higher of a floor taken from the demand curve and the resource's own highest offer. A status may carry only the
    products the rulebook's `statuses` list for it.

    Before February 3, 2026 ERCOT wrote every unpriced cell as 0, so a 0 may be "not offered" or a real $0 offer. A 0 is
    read as not offered. When `aggregate` (ERCOT's aggregate offer curves for the run, NP3-906-EX) is given, the real
    $0 offers are put back. The aggregate curve is the exact sum of every resource's offers, whatever its status
    (checked on February 24, 2026, to 0.1 MW at every price), so its MW at $0 is the total to restore for each product.
    Which cells held them is not in the file. The total is given out in this order, each cell whole until it runs out:
      1. cells that must be real: a block with MW needs one price, and this is the only product the row could price
      2. cells that were a $0 offer on the reference day (`habits`): same resource, offer type, product, block, hour
      3. cells whose resource offered that product at $0 at any time on the reference day
      4. what is left, over the remaining zero cells in proportion to their MW
    Without a reference day everything but step 1 falls to step 4, which gets the total right and the resources wrong."""
    o = o.rename(columns={'resourceName': 'resource', 'offerType': 'offer_type'}).reset_index(drop=True)
    o = o.assign(resource=o['resource'].astype(str).str.strip())
    o['offer_type'] = _offer_types(o)
    may_carry = {x.name: x.reserves for x in rules.statuses}
    no_proxy = {x.name for x in rules.statuses if not x.proxy_reserves}
    group = o['resource'].map(status).to_numpy()
    allowed = np.array([bool(may_carry.get(g)) for g in group])          # the resource's status may carry reserves at all
    carries = lambda ot, p: np.array([bool(may_carry.get(g)) and ot in may_carry[g] and (may_carry[g][ot] is None or p in may_carry[g][ot]) for g in group])
    zero_blank = (pd.Timestamp(when) < ZERO_FILL_END) if zero_price_is_blank is None else zero_price_is_blank
    kinds = sorted({k for p in rules.products for k in p.offer_kinds})
    name, kind = o['resource'].to_numpy(), o['offer_type'].to_numpy()
    out = []
    for k in range(1, 7):
        if f'quantityMW{k}' not in o:
            continue
        w = pd.to_numeric(o[f'quantityMW{k}'], errors='coerce').to_numpy(float)
        if k == 6 and no_proxy:                                          # block 6 is ERCOT's proxy offer
            w = np.where(np.isin(group.astype(str), list(no_proxy)), np.nan, w)
        for ot in kinds:
            m = (kind == ot) & np.isfinite(w) & (w > 0) & allowed
            if not m.any():
                continue
            for prod in rules.products:
                if ot not in prod.offer_kinds:
                    continue
                p = prod.name
                may = carries(ot, p)
                cols = [f'price{k}{q}' for q in prod.offer_price_columns if f'price{k}{q}' in o]
                if not cols or not (m & may).any():
                    continue
                v = o.loc[m & may, cols].apply(pd.to_numeric, errors='coerce')
                if zero_blank:
                    v = v.mask(v == 0)
                price = v.min(axis=1).to_numpy(float)
                has = np.isfinite(price)
                idx = np.where(m & may)[0][has]
                out.append(pd.DataFrame({'resource': name[idx], 'block': [f'{ot}-{i}-{k}' for i in idx],
                                         'mw': w[idx], 'product': p, 'price': price[has], '_o': idx * 10 + k}))
    restored, report = [], []
    if zero_blank and aggregate is not None and len(aggregate) and len(o):
        a = aggregate.copy()
        pc = [c for c in a.columns if c.endswith('OfferPrice')]
        a['_p'] = a[pc].apply(pd.to_numeric, errors='coerce').bfill(axis=1).iloc[:, 0] if pc else pd.to_numeric(a['price'], errors='coerce')
        a['_mw'] = pd.to_numeric(a['MWOffered'] if 'MWOffered' in a else a['mw'], errors='coerce')
        is_load = np.isin(name, list(loads)) if loads is not None else (group == 'ONL')
        can_price = {ot: sum(ot in p.offer_kinds for p in rules.products) for ot in kinds}   # products a row of this type could price
        hour = pd.Timestamp(when).hour
        exact, ever = set(), set()
        if habits is not None and len(habits):
            h = habits[habits['hour'] == hour]
            exact = set(zip(h['resource'], h['offer_type'], h['product'], h['block']))
            ever = set(zip(habits['resource'], habits['offer_type'], habits['product']))
        priced = {}                                                      # block k -> rows with a price above 0 for any product
        for k in range(1, 6):
            any_price = np.zeros(len(o), bool)
            for c in o.columns:
                if c.startswith(f'price{k}'):
                    any_price |= (pd.to_numeric(o[c], errors='coerce') > 0).to_numpy()
            priced[k] = any_price
        for agg, (prod, col, who) in AGGREGATE.items():
            if prod not in rules.product_names:
                continue
            g = a[a['product'].astype(str).str.upper() == agg]
            at_zero = g['_mw'][g['_p'] <= 1e-9]
            left = float(at_zero.max()) if len(at_zero) else 0.0         # MW ERCOT counts at exactly $0, all resources
            report.append({'product': prod, 'aggregate': agg, 'mw_at_zero': left, 'certain': 0.0, 'same_cell': 0.0, 'same_resource': 0.0, 'spread': 0.0, 'unplaced': 0.0})
            if left <= 0:
                continue
            side = is_load if who == 'load' else ~is_load if who == 'resource' else np.ones(len(o), bool)
            types = np.isin(kind, list(rules.product(prod).offer_kinds))
            cells = []                                                   # (row, block, MW, tier)
            for k in range(1, 6):
                c, q = f'price{k}{col}', f'quantityMW{k}'
                if c not in o or q not in o:
                    continue
                mw = pd.to_numeric(o[q], errors='coerce').to_numpy(float)
                z = (pd.to_numeric(o[c], errors='coerce') == 0).to_numpy() & (mw > 0) & side & types
                for i in np.where(z)[0]:
                    tier = (0 if not priced[k][i] and can_price[kind[i]] == 1 else 1 if (name[i], kind[i], col, k) in exact
                            else 2 if (name[i], kind[i], col) in ever else 3)
                    cells.append((i, k, mw[i], tier))
            for tier, label in enumerate(('certain', 'same_cell', 'same_resource', 'spread')):
                mine = [c for c in cells if c[3] == tier]
                pool = sum(c[2] for c in mine)
                share = min(left / pool, 1.0) if pool > 0 else 0.0
                if share <= 0:
                    continue
                report[-1][label] = share * pool
                left -= share * pool
                may = carries
                for i, k, mw, _ in mine:                                 # only resources whose status may carry it enter the run
                    ot = kind[i]
                    g_ = group[i]
                    if not (bool(may_carry.get(g_)) and ot in may_carry[g_] and (may_carry[g_][ot] is None or prod in may_carry[g_][ot])):
                        continue
                    whole = share > 0.999                                # a whole cell joins its block, linked with the block's other products
                    restored.append((name[i], f'{ot}-{i}-{k}' if whole else f'zero-{prod}-{i}-{k}', mw if whole else share * mw, prod, 0.0))
            report[-1]['unplaced'] = max(left, 0.0)
    cols = ['resource', 'block', 'mw', 'product', 'price']
    r = pd.concat(out, ignore_index=True).sort_values('_o', kind='stable').drop(columns='_o') if out else pd.DataFrame(columns=cols)
    if restored:
        r = pd.concat([r, pd.DataFrame(restored, columns=cols)], ignore_index=True)
    r.attrs['zero_offers'] = pd.DataFrame(report) if report else None
    return r


def _load_tables(L, rules, controllable=True, load_room='consumption-lpc'):
    """the run's Load Resource rows -> resources of kind 'load', their energy bids, reserve limits, self-arranged MW
    as $0 offer blocks, and which of them the clearing may move.

    A non-controllable Load Resource carries reserves only: up to the consumption it can drop (its consumption less
    its low power consumption). It has no output of its own in the clearing.

    A controllable Load Resource (one with a base point or a bid curve) is dispatched like a generator with negative
    output: it consumes between its LDL and HDL, and its bid-to-buy curve says what each MW of consumption is worth
    to it. Online with a bid curve and room to move, it is dispatchable; otherwise it is held at its base point.
    controllable=False leaves these out, as if their consumption were fixed demand."""
    L = L.assign(_n=L['resourceName'].astype(str).str.strip()).drop_duplicates('_n').reset_index(drop=True)
    raw = lambda c: pd.to_numeric(L[c], errors='coerce').to_numpy(float) if c in L else np.full(len(L), np.nan)
    num = lambda c: np.nan_to_num(raw(c))
    names = L['_n'].to_numpy()
    bp, has_bid = raw('basePoint'), np.isfinite(raw('SCEDBidCurveMW1'))
    ctrl = np.isin(names, list(controllable)) if isinstance(controllable, (list, tuple, set)) else (np.abs(np.nan_to_num(bp)) > 0) | has_bid
    controllable = bool(controllable) if not isinstance(controllable, bool) else controllable
    tel = L['telResStatus'].astype(str).str.strip().str.upper().to_numpy() if 'telResStatus' in L else np.full(len(L), 'ONL')
    online = np.isin(tel, [x.name for x in rules.statuses if x.dispatchable])
    room = np.clip(num('maxPowerConsumption' if load_room == 'mpc-lpc' else 'realPowerConsumption') - num('lowPowerConsumption'), 0, None)
    n = ~ctrl
    res = [pd.DataFrame({'name': names[n], 'low': 0.0, 'high': room[n], 'ramp_low': 0.0, 'ramp_high': 0.0, 'output': 0.0,
                         'dispatchable': False, 'kind': 'load', 'type': 'NCLR', 'status': tel[n],
                         'max_consumption': num('maxPowerConsumption')[n], 'low_consumption': num('lowPowerConsumption')[n]})]
    offers = pd.DataFrame(columns=['resource', 'mw', 'price'])
    moves = {}
    if controllable and ctrl.any():
        c = ctrl
        use = np.where(np.isfinite(bp), bp, num('realPowerConsumption'))            # consumption going in, MW
        hdl, ldl = raw('HDL'), raw('LDL')
        hdl, ldl = np.where(np.isfinite(hdl), hdl, use), np.where(np.isfinite(ldl), ldl, use)
        most, least = np.maximum(num('maxPowerConsumption'), hdl), np.minimum(num('lowPowerConsumption'), ldl)
        disp = c & online & has_bid & (hdl - ldl > rules.tolerance_mw)
        res.append(pd.DataFrame({'name': names[c], 'low': -most[c], 'high': -least[c], 'ramp_low': -hdl[c], 'ramp_high': -ldl[c],
                                 'output': -use[c], 'dispatchable': disp[c], 'kind': 'load', 'type': 'CLR',
                                 'status': tel[c], 'max_consumption': num('maxPowerConsumption')[c], 'low_consumption': num('lowPowerConsumption')[c]}))
        moves = dict(zip(names[c], disp[c]))
        pts = [pd.DataFrame({'resource': names[disp], 'mw': -raw(f'SCEDBidCurveMW{k}')[disp], 'price': raw(f'SCEDBidCurvePrice{k}')[disp]})
               for k in range(10, 0, -1) if f'SCEDBidCurveMW{k}' in L]   # last point first: as output (minus consumption) the
        # curve runs the other way, and where two points share a MW the one for more consumption must come first
        if pts:
            offers = pd.concat(pts, ignore_index=True).dropna()
    keep = n | (ctrl if controllable else False)
    cap = {p.name: sum(num(c) for c in p.capability_columns) * (p.ramp_minutes or 1.0) + np.zeros(len(L)) for p in rules.products}
    lim = pd.concat([pd.DataFrame({'resource': names[(v > 0) & keep], 'product': p, 'mw': v[(v > 0) & keep]}) for p, v in cap.items()], ignore_index=True)
    # Self-provided reserves (6.4.2(3): RRS and ECRS from loads on under-frequency relays) are awarded before anything
    # is bought from the load, RRS first, as far as the consumption it can drop allows. Offered at a price low enough
    # that the clearing always takes them, twice as low for RRS. A load that is not on line provides nothing.
    carries = np.isin(tel, [x.name for x in rules.statuses if x.reserves])
    own, left = [], room.copy()
    for p, v, rank in (('RRS-UFR', num('selfRRSUFR'), 2.0), ('RRS-FFR', num('selfRRSFFR'), 2.0), ('ECRS', num('selfECRS'), 1.0)):
        take = np.minimum(v, left)
        left = left - take
        m = (take > 0) & keep & carries
        own.append(pd.DataFrame({'resource': names[m], 'block': f'self-{p}', 'mw': take[m], 'product': p, 'price': rank * rules.self_arranged_price}))
    return pd.concat(res, ignore_index=True), offers, lim, pd.concat(own, ignore_index=True), moves


def _reserve_demand(curves, when):
    """Ancillary Service Demand Curves -> the reserve_demand table for the run's hour. When the report holds several
    postings, each product's curve comes from the latest posting made before the run that contains it (a posting can be
    incomplete: the one made on September 7, 2026 for September 8 holds five hours only)."""
    c = curves.copy()
    c.columns = c.columns.str.strip()
    t = pd.Timestamp(when)
    if 'hourEnding' in c:
        he = c['hourEnding'].astype(str).str.slice(0, 2).astype(int)
        c = c[(he == t.hour + 1).to_numpy()]
        if 'deliveryDate' in c:
            c = c[(pd.to_datetime(c['deliveryDate']).dt.date == t.date()).to_numpy()]
        if 'repeatHourFlag' in c:
            c = c[~_flag(c['repeatHourFlag'])]
        if 'postedDatetime' in c and len(c):                       # ERCOT re-posts when the reserve plan changes (6.4.9.1.2).
            posted = pd.to_datetime(c['postedDatetime'])               # For each product: the latest posting made before the
            pick = []                                                  # run that holds it; if none does, the first that does
            for _, g in c.assign(_posted=posted).groupby('ASType'):
                before = g['_posted'][g['_posted'] <= t]
                pick.append(g[g['_posted'] == (before.max() if len(before) else g['_posted'].min())])
            c = pd.concat(pick).drop(columns='_posted')
        c = c.rename(columns={'ASType': 'product', 'quantity': 'mw'})
    elif 'he' in c:
        c = c[(c['he'] == t.hour + 1).to_numpy()]
    c = c.assign(product=c['product'].map(lambda p: PRODUCT.get(str(p).strip(), p)))
    return c[['product', 'mw', 'price']].apply(lambda s: pd.to_numeric(s) if s.name != 'product' else s).reset_index(drop=True)


def reserve_requirements(plan, when):
    """DAM Ancillary Service Plan -> the reserve_requirements table (product, mw) for the run's hour: each product's
    requirement from the latest posting made before the run, else the first posting. None if the hour is not in the plan.
    The Non-Spin demand curve runs far past the requirement, so limits written against the Non-Spin requirement need this."""
    c = plan.copy()
    c.columns = c.columns.str.strip()
    t = pd.Timestamp(when)
    c = c[(c['hourEnding'].astype(str).str.slice(0, 2).astype(int) == t.hour + 1).to_numpy()]
    c = c[(pd.to_datetime(c['deliveryDate']).dt.date == t.date()).to_numpy()]
    if 'DSTFlag' in c:
        c = c[~_flag(c['DSTFlag'])]
    if not len(c):
        return None
    posted = pd.to_datetime(c['postedDatetime']) if 'postedDatetime' in c else pd.Series(t, index=c.index)
    out = []
    for p, g in c.assign(_posted=posted).groupby('ancillaryType'):
        before = g['_posted'][g['_posted'] <= t]
        g = g[g['_posted'] == (before.max() if len(before) else g['_posted'].min())]
        out.append({'product': PRODUCT.get(str(p).strip(), p), 'mw': float(pd.to_numeric(g['quantity']).iloc[0])})
    return pd.DataFrame(out)


def constraint_name(df):
    """The id this adapter gives a constraint: '<constraint name>|<from station>|<to station>|<contingency>'.
    Your shift_factors index must use the same ids."""
    return (df['constraintName'].astype(str).str.strip() + '|' + df['fromStation'].fillna('').astype(str).str.strip() + '|'
            + df['toStation'].fillna('').astype(str).str.strip() + '|' + df['contingencyName'].fillna('').astype(str).str.strip())


def _constraints(c, rules):
    """the run's rows of SCED Shadow Prices and Binding Transmission Constraints -> the constraints table."""
    c = c.copy()
    c['name'] = constraint_name(c)
    c['shadowPrice'] = pd.to_numeric(c['shadowPrice'], errors='coerce')
    c = c.sort_values('shadowPrice').drop_duplicates('name', keep='last')
    return pd.DataFrame({'name': c['name'].to_numpy(), 'limit': pd.to_numeric(c['limit'], errors='coerce').to_numpy(float),
                         'flow': pd.to_numeric(c['value'], errors='coerce').to_numpy(float),
                         'max_shadow_price': pd.to_numeric(c['maxShadowPrice'], errors='coerce').fillna(rules.default_max_shadow_price).to_numpy(float),
                         'published_shadow_price': c['shadowPrice'].to_numpy(float),
                         'competitive': (c['CCTStatus'].astype(str).str.strip().str.upper() != 'NONCOMP').to_numpy() if 'CCTStatus' in c else True}).dropna(subset=['limit', 'flow']).reset_index(drop=True)


def inputs(sced, when=None, reserve_offers=None, load_resources=None, reserve_demand=None, constraints=None, aggregate_offers=None,
           shift_factors=None, resource_nodes=None, rules=None, controllable_loads=True, demand=None,
           reserve_requirements=None, limit_values=None, storage_types=STORAGE_TYPES, zero_price_is_blank=None,
           load_room='consumption-lpc', missing_shift_factors='drop', curve_points=NPT, curve='SCED2', mitigated=None,
           mitigated_offer_caps=None, categories=None, reference_offers=None, battery_efficiency=None, quick_start=None):
    """One SCED run's Inputs from ERCOT's published tables (pandas DataFrames, ERCOT's column names).

    sced             60-Day SCED Disclosure rows, generation and storage together. One run, or a whole day with `when`
    when             the run's SCED timestamp. Needed when the tables hold more than one run
    reserve_offers   60-Day SCED reserve offers                       -> reserve_offers
    aggregate_offers 2-Day Aggregate SCED reserve offers, for days before February 3, 2026: restores real $0 offers
    reference_offers the reserve offers of a day on or after February 3, 2026 (or zero_offer_habits() of it): says which
                     resources the restored $0 offers belong to. Without it only their total is right
    load_resources   60-Day SCED Load Resource data                   -> resources of kind 'load'
    reserve_demand   Ancillary Service Demand Curves                  -> reserve_demand (switches reserves on)
    constraints      SCED Shadow Prices and Binding Constraints       -> constraints
    shift_factors, resource_nodes   yours; passed straight through
    rules            the rulebook. Default: the one in force at `when`
    controllable_loads   False treats controllable Load Resources as fixed demand instead of dispatching them. A list
                     of names says which Load Resources are controllable (default: those with a base point or a bid curve)
    demand           MW to serve, if you have ERCOT's demand target (GTBD) or a forecast. Default: the sum of base
                     points. Controllable loads' consumption is taken off it either way
    reserve_requirements, limit_values   passed through (see opensced.schema())
    storage_types    resource types treated as storage
    zero_price_is_blank   read a reserve offer price of 0 as "not offered". Default: true before February 3, 2026
    load_room        'consumption-lpc' (what a load can drop from where it is now) or 'mpc-lpc' (from its maximum)
    missing_shift_factors   'drop' a constraint with no shift factors (listed in notes) or raise an 'error'
    curve_points     points on an offer curve in the files
    curve            'SCED2': the curves SCED dispatched on, already mitigated (the clearing then runs once).
                     'SCED1': the curves before mitigation; the clearing runs both steps and mitigates them itself
    mitigated        names of the resources whose offers are capped in step 2 (only used with curve='SCED1')
    mitigated_offer_caps   table resource, mw, price: their cost-based caps (see opensced.schema())
    quick_start      names of quick-start units. One that telemeters OFF is still offered ERCOT's proxy Non-Spin offer.
                     Day uses every unit seen in OFFQS during the day
    battery_efficiency   {resource: share of charging energy stored}, e.g. helpers.battery_efficiency(sced). ERCOT does not
                     publish it; a battery not named gets rules.storage_charge_efficiency
    categories       {resource: category} to override the category taken from the resource type, e.g. 'qf'

    Reserves are only cleared when reserve_demand is given. Constraints are only enforced when shift_factors is given."""
    x = normalize(sced)
    if when is None:
        if x[TS].nunique() != 1:
            raise ValueError(f'the SCED table holds {x[TS].nunique():,} runs: say which with when="YYYY-MM-DD HH:MM"')
        when = x[TS].iloc[0]
    else:
        x = _run_rows(x, when, TS)
        if x.empty:
            raise ValueError(f'no SCED run at {when} in the SCED table')
        when = x[TS].iloc[0]
    rules = rules or ALL.on(when)
    if reserve_demand is not None:                                     # never clear with a product nobody can carry by accident
        caps = [c for p in rules.products for c in p.capability_columns if c in GEN_CAPABILITY]
        empty = [c for c in caps if c not in x or not pd.to_numeric(x[c], errors='coerce').notna().any()]
        if empty and len(empty) < len(caps):
            raise ValueError(f'the SCED table has no values in {", ".join(empty)} at {when}, so no generator or battery could carry '
                             f'that product. Files of December 2025 downloaded early lack these columns; ERCOT\'s API has them')
    res, eo, sto, lim, status, disp = _sced_tables(x, rules, storage_types, curve_points, curve)
    if quick_start is not None and len(quick_start):               # a quick-start unit that telemeters OFF
        qs = res['name'].isin(set(quick_start)) & (res['status'] == 'OFF')
        res.loc[qs, 'status'] = 'OFF-QS'
        status.update({n: 'OFF-QS' for n in res.loc[qs, 'name']})
    if len(sto):
        known = sto['resource'].map(dict(battery_efficiency)) if battery_efficiency is not None else pd.Series(np.nan, index=sto.index)
        sto['efficiency'] = pd.to_numeric(known, errors='coerce').fillna(rules.storage_charge_efficiency).to_numpy(float)
    if categories:
        res['category'] = res['name'].map(categories).fillna(res['category'])
    res['mitigated'] = res['name'].isin(set(mitigated)) if mitigated is not None else False
    own = None
    if load_resources is not None:
        L = _run_rows(load_resources, when, 'SCEDTimestamp')
        lres, leo, llim, own, moves = _load_tables(L, rules, controllable_loads, load_room)
        if reserve_offers is None:                                     # no offers: loads that only carry reserves add nothing
            lres = lres[lres['type'] == 'CLR']
        lres = lres[~lres['name'].isin(res['name'])]
        mine = lambda t: t[t['resource'].isin(lres['name'])]
        status.update(zip(lres['name'], lres['status']))
        disp.update({k: v for k, v in moves.items() if k in set(lres['name'])})
        res = pd.concat([res, lres], ignore_index=True)
        eo = pd.concat([eo, mine(leo)], ignore_index=True)
        lim, own = pd.concat([lim, mine(llim)], ignore_index=True), mine(own)
    ro = None
    if reserve_offers is not None:
        habits = reference_offers
        if habits is not None and 'hour' not in habits:                # a raw day of offers: reduce it to its $0 cells
            habits = zero_offer_habits(habits)
        load_names = None if load_resources is None else set(L['resourceName'].astype(str).str.strip())
        ro = _reserve_offers(_run_rows(reserve_offers, when, 'SCEDTimestamp'), status, when, rules, zero_price_is_blank,
                             None if aggregate_offers is None else _run_rows(aggregate_offers, when, 'SCEDTimestamp'), load_names, habits)
        zero_report = ro.attrs.get('zero_offers')
        if own is not None:
            ro = pd.concat([ro, own[own['product'].isin(rules.product_names)]], ignore_index=True)
    cons = None
    if constraints is not None:
        cons = _constraints(_run_rows(constraints, when, 'SCEDTimestamp'), rules)
    notes = {'published_shadow_prices': cons.set_index('name')['published_shadow_price'] if cons is not None else None}
    if reserve_offers is not None and zero_report is not None:
        notes['zero_offers_restored'] = zero_report
    if cons is not None:                                               # enforce the constraints that have shift factors
        have = cons['name'].isin(shift_factors.index) if shift_factors is not None else pd.Series(False, index=cons.index)
        notes['constraints_published'] = len(cons)
        notes['constraints_without_shift_factors'] = list(cons['name'][~have])
        if missing_shift_factors == 'error' and shift_factors is not None and (~have).any():
            raise ValueError(f'shift_factors: no row for {int((~have).sum()):,} of {len(cons):,} constraints, e.g. {cons["name"][~have].iloc[0]!r}')
        cons = cons[have].reset_index(drop=True) if have.any() else None
    curves = None
    if reserve_demand is not None:
        curves = _reserve_demand(reserve_demand, when)
        lacking = [d for d in rules.demand_names if d not in set(curves['product'])]
        if lacking:                                                    # never clear without reserves by accident
            raise ValueError(f'reserve_demand: no demand curve for {", ".join(lacking)} in hour ending {pd.Timestamp(when).hour + 1} of '
                             f'{pd.Timestamp(when).date()}. The demand curve file is incomplete for this run. Pass reserve_demand=None '
                             f'to clear energy only on purpose')
    served = float(res['output'].sum()) if demand is None else float(demand) + float(res.loc[res['type'] == 'CLR', 'output'].sum())
    return Inputs(resources=res, demand=served, mitigated=(curve == 'SCED2'), mitigated_offer_caps=mitigated_offer_caps, reserve_requirements=reserve_requirements, limit_values=limit_values, energy_offers=eo, storage=sto, reserve_limits=lim,
                  reserve_offers=ro, reserve_demand=curves,
                  constraints=None if cons is None else cons.drop(columns='published_shadow_price'),
                  shift_factors=shift_factors, resource_nodes=resource_nodes, time=pd.Timestamp(when), notes=notes)


# ---------------------------------------------------------------- a folder of downloaded files
def _read(folder, stem):
    for ext in ('.parquet', '.csv', '.csv.gz'):
        f = os.path.join(folder, stem + ext)
        if os.path.exists(f):
            return pd.read_parquet(f) if ext == '.parquet' else pd.read_csv(f, low_memory=False)
    return None


class Day:
    """One operating day of ERCOT files, loaded by read_day().

    times                       the SCED runs in the folder
    inputs(time)                that run's Inputs
    published_lambda()          Series time -> ERCOT's system lambda
    published_node_prices()     DataFrame time x settlement point
    published_reserve_prices()  DataFrame time x product
    published_shadow_prices()   DataFrame time x constraint"""

    def __init__(self, folder):
        self.folder = folder
        t = {k: _read(folder, stem) for k, stem in FILES.items()}
        if t['gen'] is None:
            have = ', '.join(sorted(os.listdir(folder))) if os.path.isdir(folder) else 'the folder does not exist'
            raise FileNotFoundError(f'{folder}: no {FILES["gen"]}.parquet or .csv (the 60-Day SCED Disclosure for generation '
                                    f'resources). Found: {have}. See help(opensced.market("ercot").adapter) for the file names')
        parts = [normalize(t['gen'])] + ([normalize(t['esr'])] if t['esr'] is not None else [])
        self.sced = pd.concat(parts, ignore_index=True)
        self.tables = t
        self.times = sorted(self.sced[TS].dropna().unique())
        self.missing = [FILES[k] for k in ('esr', 'reserve_offers', 'load_resources', 'reserve_demand', 'constraints') if t[k] is None]
        self._by_run = dict(tuple(self.sced.groupby(TS)))
        self._curves = None                                              # demand curves, cut by hour once (the full report is large)
        rd = t['reserve_demand']
        if rd is not None and ('hourEnding' in rd or 'he' in rd):
            he = rd['hourEnding'].astype(str).str.slice(0, 2).astype(int) if 'hourEnding' in rd else rd['he'].astype(int)
            self._curves = {h: g for h, g in rd.groupby(he.to_numpy())}
        self._habits = None if t['reference_offers'] is None else zero_offer_habits(t['reference_offers'])
        from opensced.markets.ercot import helpers
        self.battery_efficiency = helpers.battery_efficiency(self.sced)      # read off the day's own Reg-Down awards
        self.quick_start = sorted(set(self.sced.loc[self.sced['Telemetered Resource Status'].astype(str).str.strip() == 'OFFQS', RES]))
        self._split = {}                                                 # per-run reports, cut by run once
        for k in ('reserve_offers', 'load_resources', 'constraints', 'aggregate_offers'):
            if t[k] is not None:
                when = pd.Series(self._snap(t[k]['SCEDTimestamp']), index=t[k].index)
                self._split[k] = {u: g for u, g in t[k].groupby(when)}

    def inputs(self, time, shift_factors=None, resource_nodes=None, rules=None, **options):
        t = pd.Timestamp(time)
        if t not in self._by_run:
            near = min(self.times, key=lambda u: abs(u - t))
            raise KeyError(f'no SCED run at {t}. The nearest is {near}. See .times for all {len(self.times):,}')
        cut = lambda k: None if self.tables[k] is None else self._split[k].get(t, self.tables[k].iloc[:0])
        curves = self.tables['reserve_demand'] if self._curves is None else self._curves.get(t.hour + 1, self.tables['reserve_demand'].iloc[:0])
        options.setdefault('reference_offers', self._habits)
        options.setdefault('battery_efficiency', self.battery_efficiency)
        options.setdefault('quick_start', self.quick_start)
        if self.tables['reserve_plan'] is not None:
            options.setdefault('reserve_requirements', reserve_requirements(self.tables['reserve_plan'], t))
        return inputs(self._by_run[t], None, cut('reserve_offers'), cut('load_resources'), curves,
                      cut('constraints'), cut('aggregate_offers'), shift_factors, resource_nodes, rules, **options)

    def published_lambda(self):
        x = self._need('system_lambda')
        col = next(c for c in ('systemLambda', 'cappedSystemLambda', 'SystemLambda') if c in x)
        return pd.Series(pd.to_numeric(x[col]).to_numpy(), index=self._snap(x['SCEDTimestamp']), name='system_lambda').rename_axis('time')

    def published_node_prices(self):
        x = self._need('lmp')
        x = x.rename(columns=lambda c: c.strip())
        node = next(c for c in ('SettlementPoint', 'settlementPoint') if c in x)
        price = next(c for c in ('LMP', 'cappedLMP', 'CappedLMP') if c in x)
        f = pd.DataFrame({'time': self._snap(x['SCEDTimestamp']), 'node': x[node].astype(str).str.strip(), 'price': pd.to_numeric(x[price]).to_numpy()})
        return f.drop_duplicates(['time', 'node']).pivot(index='time', columns='node', values='price')

    def published_reserve_prices(self):
        x = self._need('reserve_prices')
        col = next(c for c in ('cappedMCPC', 'MCPC') if c in x)
        f = pd.DataFrame({'time': self._snap(x['SCEDTimestamp']), 'product': x['ASType'].map(lambda p: MCPC.get(str(p).strip(), p)), 'price': pd.to_numeric(x[col]).to_numpy()})
        return f.drop_duplicates(['time', 'product']).pivot(index='time', columns='product', values='price')

    def published_shadow_prices(self):
        x = self._need('constraints')
        f = pd.DataFrame({'time': self._snap(x['SCEDTimestamp']), 'constraint': constraint_name(x), 'price': pd.to_numeric(x['shadowPrice'], errors='coerce').to_numpy()})
        return f.sort_values('price').drop_duplicates(['time', 'constraint'], keep='last').pivot(index='time', columns='constraint', values='price')

    def _need(self, key):
        if self.tables[key] is None:
            raise FileNotFoundError(f'{self.folder}: no {FILES[key]}.parquet or .csv')
        return self.tables[key]

    def _snap(self, ts):
        """a report's SCED timestamps -> the run times of the SCED disclosure (same timestamp, else same 5 minutes)."""
        ts = pd.to_datetime(ts)
        known = set(pd.DatetimeIndex(self.times))
        by5 = {pd.Timestamp(t).floor('5min'): pd.Timestamp(t) for t in self.times}
        return ts.where(ts.isin(known), ts.dt.floor('5min').map(by5)).to_numpy()

    def __repr__(self):
        day = pd.Timestamp(self.times[0]).date() if self.times else '?'
        out = [f'ERCOT day {day}: {len(self.times):,} SCED runs, {self.sced[RES].nunique():,} resources']
        for k, stem in FILES.items():
            if k in ('gen', 'esr'):
                continue
            out.append(f'  {stem:<28} ' + ('missing' if self.tables[k] is None else f'{len(self.tables[k]):,} rows'))
        return '\n'.join(out)


def read_day(folder):
    """Load a folder holding one operating day of ERCOT files (names in this module's docstring). -> Day"""
    return Day(folder)
