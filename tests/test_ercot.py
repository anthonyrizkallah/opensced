"""The ERCOT adapter on the example run shipped with the repository (public files, August 12, 2026 17:00)."""
import os

import numpy as np
import pandas as pd
import pytest

import opensced

FOLDER = os.path.join(os.path.dirname(__file__), '..', 'examples', 'ercot', '2026-08-12_1700')
EXTRA = os.path.join(FOLDER, 'not_published_by_ercot')
ercot = opensced.market('ercot')


@pytest.fixture(scope='module')
def day():
    return ercot.read_day(FOLDER)


def test_rulebook_by_date():
    assert ercot.rules.on('2025-12-20').name == 'ercot/2025-12-05'
    assert ercot.rules.on('2026-08-12').name == 'ercot/2026-01-01'
    change = ercot.rules.get('ercot/2025-12-05').diff(ercot.rules.latest)
    assert list(change) == ['products.RRS-PFR']
    with pytest.raises(LookupError):
        ercot.rules.on('2025-01-01')


def test_tables_are_valid(day):
    i = day.inputs(day.times[0])
    i.validate(ercot.rules.latest)
    assert i.constraints is None                                         # no shift factors given: no network
    assert set(i.resources.kind) == {'generator', 'storage', 'load'}
    assert i.demand == pytest.approx(i.resources.output.sum())


def test_system_price_without_the_network_is_far_off_and_with_it_is_close(day):
    run = day.times[0]
    published = day.published_lambda()[run]
    bare = ercot.clear(day.inputs(run))
    assert bare.solved and abs(bare.system_lambda - published) > 1.0
    if not os.path.isdir(EXTRA):
        pytest.skip('shift factors and the resource-node map are not shipped')
    sf = pd.read_csv(os.path.join(EXTRA, 'shift_factors.csv.gz'), index_col=0)
    nodes = pd.read_csv(os.path.join(EXTRA, 'resource_nodes.csv'))
    full = ercot.clear(day.inputs(run, shift_factors=sf, resource_nodes=nodes))
    assert abs(full.system_lambda - published) < 0.25
    s = opensced.score(full, system_lambda=published, node_prices=day.published_node_prices().loc[run])
    assert s.table.loc['node prices', 'mean_abs_error'] < 0.5


def test_a_draft_rule_changes_the_clearing(day):
    i = day.inputs(day.times[0])
    base = ercot.clear(i)
    draft = ercot.rules.latest.replace(name='draft', shortage_price=100.0)
    assert ercot.clear(i.copy(demand=i.demand + 50_000), rules=draft).system_lambda == pytest.approx(100.0)
    assert base.rules.name == 'ercot/2026-01-01'


def test_rrs_is_three_products_on_one_demand_curve(day):
    r = ercot.clear(day.inputs(day.times[0]))
    assert {'RRS-PFR', 'RRS-FFR', 'RRS-UFR'} <= set(r.reserve_awards.columns) and 'RRS' in r.reserve_prices.index
    rrs = r.reserve_awards[['RRS-PFR', 'RRS-FFR', 'RRS-UFR']].sum()
    assert rrs.sum() == pytest.approx(r.reserve_bought['RRS'])
    curve = day.inputs(day.times[0]).reserve_demand.query("product == 'RRS'").mw.max()
    assert rrs['RRS-FFR'] + rrs['RRS-UFR'] <= curve - 1377.0 + 1e-6          # 1,377 MW is kept for RRS-PFR
    loose = ercot.clear(day.inputs(day.times[0]), rules=ercot.rules.latest.replace(products={'RRS-PFR': {'reserved_mw': 0.0}}))
    assert rrs['RRS-PFR'] == pytest.approx(1377.0)                           # ERCOT awarded 1,376.99 MW in this run
    assert loose.reserve_awards['RRS-PFR'].sum() < rrs['RRS-PFR'] - 100      # without the rule the cheaper kinds take over


def test_controllable_loads_are_dispatched(day):
    i, fixed = day.inputs(day.times[0]), day.inputs(day.times[0], controllable_loads=False)
    clr = i.resources[i.resources.type == 'CLR']
    assert len(clr) and (clr.output <= 0).all() and clr.dispatchable.any()
    assert 'CLR' not in set(fixed.resources.type)
    assert i.demand == pytest.approx(fixed.demand + clr.output.sum())    # their consumption leaves demand
    out = ercot.clear(i)
    assert (out.dispatch[clr.name] <= 1e-9).all()


def test_statuses_follow_the_protocols(day):
    i = day.inputs(day.times[0])
    r = i.resources.set_index('name')
    assert r[r.status == 'ONOS'].dispatchable.any()                     # on an Output Schedule: moved on ERCOT's proxy curve
    assert r[r.status == 'OFFQS'].dispatchable.all()                    # off-line quick start: SCED may deploy it
    assert not r[r.status.isin(['ONTEST', 'OFF', 'ONSC', 'OUT'])].dispatchable.any()
    offered = i.reserve_offers.assign(status=i.reserve_offers.resource.map(r.status)).groupby('status')['product'].agg(set)
    assert offered['OFF'] == {'NonSpin'} and offered['OFFQS'] <= {'NonSpin', 'ECRS'}
    assert offered.get('ONSC', set()) <= {'RRS-PFR', 'RRS-FFR', 'RRS-UFR', 'ECRS'}


def test_rulebook_limits_hold(day):
    i = day.inputs(day.times[0])
    out = ercot.clear(i)
    a, need = out.reserve_awards, i.reserve_demand.groupby('product').mw.max()
    assert a['RRS-FFR'].sum() <= 450 + 1e-6
    assert a['RRS-FFR'].sum() + a['RRS-UFR'].sum() <= 0.6 * need['RRS'] + 1e-6
    nclr = i.resources.name[i.resources.type == 'NCLR']
    assert a.loc[a.index.isin(nclr), 'ECRS'].sum() <= 0.5 * need['ECRS'] + 1e-6
    assert out.system_lambda <= 5000 and {lim.name for lim in ercot.rules.latest.limits} == {'FFR', 'relay loads + FFR', 'ECRS from loads'}


def test_every_rule_number_is_an_input(day):
    rules = ercot.rules.latest
    assert rules.shortage == pytest.approx(11052.01) and rules.cap == 5000.0          # voll + offer_cap + adder; cap = voll
    assert rules.replace(voll=9000.0).shortage == pytest.approx(15052.01)
    run = day.times[0]
    base = day.inputs(run)
    assert day.inputs(run, demand=base.demand + 500.0).demand > base.demand + 250.0   # your own demand target
    assert ercot.clear(base.copy(limit_values=pd.DataFrame([{'limit': 'RRS-PFR', 'min_mw': 1500.0}]))).reserve_awards['RRS-PFR'].sum() >= 1500 - 1e-6
    tight = ercot.clear(base.copy(limit_values=pd.DataFrame([{'limit': 'FFR', 'max_mw': 5.0}])))
    assert tight.reserve_awards['RRS-FFR'].sum() <= 5.0 + 1e-6
    need = base.copy(reserve_requirements=pd.DataFrame([{'product': 'RRS', 'mw': 2000.0}]))
    a = ercot.clear(need).reserve_awards
    assert a['RRS-FFR'].sum() + a['RRS-UFR'].sum() <= 2000.0 - 1377.0 + 1e-6
    held = rules.replace(statuses=tuple(s for s in rules.statuses if s.name != 'OFFQS'))
    r = day.inputs(run, rules=held).resources
    assert not r[r.status == 'OFFQS'].dispatchable.any()


def test_helpers_build_what_ercot_publishes(day):
    h, rules = ercot.helpers, ercot.rules.latest
    i = day.inputs(day.times[0])
    proxy = h.proxy_reserve_offers(i.resources.head(1), None, i.reserve_demand, rules).set_index('product').price
    assert proxy['RegUp'] == pytest.approx(1400.97, abs=0.02) and proxy['RegDown'] == pytest.approx(1999.99)   # ERCOT's own floors that hour
    r = pd.DataFrame({'name': ['g', 'l'], 'kind': ['generator', 'load'], 'low': [50.0, -30.0], 'high': [200.0, -5.0],
                      'output': [100.0, -20.0], 'ramp_up': [4.0, 1.0], 'ramp_down': [5.0, 2.0]})
    lim = h.dispatch_limits(r, rules).set_index('name')
    assert lim.loc['g', ['ramp_low', 'ramp_high']].tolist() == [75.0, 120.0] and lim.loc['l', ['ramp_low', 'ramp_high']].tolist() == [-30.0, -15.0]
    c = pd.DataFrame({'name': list('abcd'), 'limit': 1.0, 'flow': 0.0, 'kind': ['base', 'contingency', 'contingency', 'contingency'], 'kv': [345, 345, 138, 69]})
    assert h.max_shadow_prices(c, rules).max_shadow_price.tolist() == [5251.0, 4500.0, 3500.0, 2800.0]
    g = pd.DataFrame({'name': ['w', 's'], 'low': [0.0, 100.0], 'high': [80.0, 300.0], 'category': ['wind', 'other'], 'output_schedule': [float('nan'), 150.0]})
    curve = h.proxy_energy_curves(g, None, rules)
    assert curve[curve.resource == 'w'].price.tolist() == [-250.0, -249.99, 1500.0]
    assert curve[curve.resource == 's'].price.tolist() == [-250.0, -249.99, 1999.99, 2000.0]
    assert h.demand(60000.0, 250.0) == 59750.0


def test_two_step_on_ercot_step_one_curves(day):
    run = day.times[0]
    published = day.published_lambda()[run]
    final = day.inputs(run)                                              # ERCOT's mitigated curves: one step
    assert final.mitigated and ercot.clear(final).reference_prices is None
    raw = day.inputs(run, curve='SCED1')                                 # the curves before mitigation: both steps
    assert not raw.mitigated and ercot.rules.latest.two_step
    out = ercot.clear(raw)
    assert out.reference_prices is not None and out.step1.solved
    gas = raw.resources[(raw.resources.category == 'combined_cycle') & raw.resources.dispatchable].name
    before = raw.energy_offers[raw.energy_offers.resource.isin(gas)].price.min()
    after = out._inputs.energy_offers[out._inputs.energy_offers.resource.isin(gas)].price.min()
    assert before < -200 and after == pytest.approx(-20.0)               # raised to the combined-cycle floor
    assert abs(out.system_lambda - ercot.clear(final).system_lambda) < 5.0
    caps = ercot.helpers.generic_offer_caps(raw.resources.head(3), 2.42, ercot.rules.latest)
    assert caps.price.iloc[0] == pytest.approx(25.41)                    # 10.5 x the gas index price


def test_ercot_ramp_rates_reproduce_ercots_dispatch_range(day):
    i = day.inputs(day.times[0])
    r = i.resources[(i.resources.kind != 'load') & i.resources.dispatchable & i.resources.ramp_up.notna()]
    assert len(r) > 500
    again = opensced.carry_forward(i, ercot.clear(i), ercot.rules.latest, carry=('ramp',))    # limits rebuilt from ramp rates
    assert again.notes['carried'] == ('ramp',) and {'ramp_low', 'ramp_high'} <= set(again.resources.columns)
    assert (again.resources.ramp_high <= again.resources.high + 1e-6)[again.resources.dispatchable].all()


def test_an_incomplete_demand_curve_file_is_an_error_not_a_silent_energy_only_run(day):
    curves = day.tables['reserve_demand']
    sced = day._by_run[pd.Timestamp(day.times[0])]
    with pytest.raises(ValueError, match='no demand curve for'):
        ercot.inputs(sced, reserve_demand=curves[curves['product'] != 'ECRS'])
    assert ercot.inputs(sced, reserve_demand=None).reserve_demand is None      # energy only, on purpose


def _offer_rows(**cells):
    """a tiny reserve offer disclosure: one ONRES row per resource, block 1 of 10 MW, proxy block priced for every product."""
    P = ['REGUP', 'REGDN', 'RRSPFR', 'RRSUFR', 'RRSFFR', 'NSPIN', 'ECRS']
    rows = []
    for name, prices in cells.items():
        r = {'SCEDTimestamp': '2026-01-10T12:00:10', 'resourceName': name, 'offerType': 'ONRES', 'quantityMW1': 10.0, 'quantityMW6': 5.0}
        r.update({f'price1{p}': prices.get(p, 0.0) for p in P})
        r.update({f'price6{p}': 0.0 if p == 'REGDN' else 900.0 for p in P})
        rows.append(r)
    return pd.DataFrame(rows)


def test_a_missing_offer_type_is_read_from_the_proxy_block():
    from opensced.markets.ercot import adapter as A
    o = _offer_rows(A={'ECRS': 3.0}).rename(columns={'resourceName': 'resource', 'offerType': 'offer_type'})
    o['offer_type'] = None
    blank = o.assign(**{c: 0.0 for c in o.columns if c.startswith('price6')})
    down, offline = blank.assign(price6REGDN=1999.99), blank.assign(price6NSPIN=200.0)
    assert list(A._offer_types(pd.concat([o, down, offline], ignore_index=True))) == ['ONRES', 'REGDN', 'OFFNS']
    with pytest.raises(ValueError, match='no offerType'):
        A._offer_types(blank)


def test_restored_zero_offers_go_to_the_resources_that_offer_at_zero_on_the_reference_day():
    """Before February 3, 2026 a $0 offer and a blank look the same. ERCOT's aggregate curve says 10 MW of ECRS were
    offered at $0; the reference day says it is B that offers ECRS at $0, so B gets all of it and A none."""
    from opensced.markets.ercot import adapter as A
    rules = opensced.market('ercot').rules.on('2026-01-10')
    o = _offer_rows(A={'REGUP': 4.0}, B={'REGUP': 4.0})
    agg = pd.DataFrame({'SCEDTimestamp': '2026-01-10T12:00:10', 'product': 'ECRSS', 'MWOffered': [10.0, 30.0], 'ECRSSOfferPrice': [0.0, 900.0]})
    status = {'A': 'ON', 'B': 'ON'}
    ref = _offer_rows(B={'REGUP': 4.0}).assign(SCEDTimestamp='2026-02-10T12:00:10')
    ref[[c for c in ref.columns if c.startswith('price1') and c not in ('price1REGUP', 'price1ECRS')]] = np.nan
    r = A._reserve_offers(o, status, '2026-01-10 12:00:10', rules, aggregate=agg, habits=A.zero_offer_habits(ref))
    ecrs = r[(r['product'] == 'ECRS') & (r['price'] == 0)]
    assert ecrs.set_index('resource').mw.to_dict() == {'B': 10.0}
    assert ecrs.block.iloc[0] == r[(r.resource == 'B') & (r['product'] == 'RegUp') & (r.price == 4.0)].block.iloc[0]   # linked with its block
    spread = A._reserve_offers(o, status, '2026-01-10 12:00:10', rules, aggregate=agg)        # no reference: the total only
    z = spread[(spread['product'] == 'ECRS') & (spread['price'] == 0)].set_index('resource').mw
    assert z.to_dict() == {'A': 5.0, 'B': 5.0}
    with pytest.raises(ValueError, match='no blank prices'):
        A.zero_offer_habits(o)


def test_an_empty_capability_column_is_an_error(day):
    sced = day._by_run[pd.Timestamp(day.times[0])].copy()
    sced['ASCapRRSPFR'] = np.nan                                       # how the December 2025 files arrive
    with pytest.raises(ValueError, match='ASCapRRSPFR'):
        ercot.inputs(sced, reserve_demand=day.tables['reserve_demand'])


def test_battery_efficiency_is_read_off_reg_down_awards():
    """ten runs of one battery held by state of charge at 85%: room = 0.85 x 0.5 h x award."""
    from opensced.markets.ercot import helpers
    award = np.linspace(10, 28, 10)
    sced = pd.DataFrame({'SCED Time Stamp': pd.date_range('2026-05-01 12:00', periods=10, freq='5min'), 'Resource Name': 'BAT', 'Resource Type': 'ESR',
                         'Telemetered Resource Status': 'ON', 'Base Point': 0.0, 'SOC': 100 - 0.85 * 0.5 * award, 'maxSOC': 100.0, 'ASAwardsREGDN': award})
    loose = sced.assign(**{'Resource Name': 'IDLE', 'SOC': 20.0})        # never held by state of charge: no value
    eff = helpers.battery_efficiency(pd.concat([sced, loose]))
    assert eff.to_dict() == {'BAT': pytest.approx(0.85)}


def test_ercot_run_uses_each_batterys_efficiency(day):
    i = day.inputs(day.times[0])
    assert i.storage.efficiency.between(0.5, 1.0).all() and (i.storage.efficiency == ercot.rules.latest.storage_charge_efficiency).any()
    assert ercot.rules.latest.product('RegDown').duration_hours == 0.5 and ercot.rules.latest.block_refine == 3


def test_loads_use_their_own_status_and_self_provided_reserves_come_first():
    from opensced.markets.ercot import adapter as A
    rules = ercot.rules.latest
    L = pd.DataFrame({'resourceName': ['ON_LD', 'OUT_LD', 'SHORT_LD'], 'telResStatus': ['ONL', 'OUTL', 'ONL'], 'maxPowerConsumption': [20.0, 20.0, 20.0],
                      'lowPowerConsumption': [0.0, 0.0, 0.0], 'realPowerConsumption': [10.0, 10.0, 3.0], 'selfRRSUFR': [2.0, 2.0, 2.0], 'selfECRS': [5.0, 5.0, 5.0],
                      'ASCapRRSUFR': [2.0, 2.0, 2.0], 'ASCapECRS': [1.0, 1.0, 1.0]})
    res, _, _, own, _ = A._load_tables(L, rules)
    assert res.set_index('name').status.to_dict() == {'ON_LD': 'ONL', 'OUT_LD': 'OUTL', 'SHORT_LD': 'ONL'}
    mw = own.set_index(['resource', 'product']).mw
    assert 'OUT_LD' not in own.resource.values                           # not on line: provides nothing
    assert mw['ON_LD', 'RRS-UFR'] == 2.0 and mw['ON_LD', 'ECRS'] == 5.0
    assert mw['SHORT_LD', 'RRS-UFR'] == 2.0 and mw['SHORT_LD', 'ECRS'] == 1.0    # 3 MW of room: RRS first, ECRS gets the rest
    price = own.set_index(['resource', 'product']).price
    assert price['ON_LD', 'RRS-UFR'] < price['ON_LD', 'ECRS'] < 0        # taken before any bought offer, RRS before ECRS


def test_status_rules_measured_on_ercot_awards():
    st = {s.name: s for s in ercot.rules.latest.statuses}
    assert st['STARTUP'].reserves == {'OFFNS': ('NonSpin',)} and not st['STARTUP'].dispatchable
    assert st['OFFQS'].proxy_reserves and st['OFF-QS'].proxy_reserves and not st['OFF'].proxy_reserves
    assert st['OFFQS'].reserves == {'ONRES': ('ECRS', 'NonSpin')}


def _small_system(ruc_price=250.0):
    """a cheap unit, a RUC-committed unit held on at its 40 MW minimum, and a dear unit at the margin."""
    res = pd.DataFrame([{'name': 'cheap', 'low': 0.0, 'high': 100.0, 'status': 'ON'}, {'name': 'ruc', 'low': 40.0, 'high': 60.0, 'status': 'ONRUC'},
                        {'name': 'dear', 'low': 0.0, 'high': 100.0, 'status': 'ON'}]).assign(ramp_low=lambda r: r.low, ramp_high=lambda r: r.high, output=[100.0, 40.0, 10.0],
                                                                                            dispatchable=True, kind='generator', telemetered=[100.0, 40.0, 10.0], ramp_up=10.0, ramp_down=10.0)
    off = pd.DataFrame({'resource': ['cheap', 'cheap', 'ruc', 'ruc', 'dear', 'dear'], 'mw': [0.0, 100.0, 0.0, 60.0, 0.0, 100.0],
                        'price': [20.0, 20.0, ruc_price, ruc_price, 100.0, 300.0]})
    return opensced.Inputs(res, 150.0, off, time=pd.Timestamp('2026-06-01 12:00'))


def test_pricing_run_prices_out_ruc_units_and_adds_deployed_loads():
    from opensced.markets.ercot import pricing
    rules = opensced.Rules(shortage_price=5001.0, block_refine=3)
    p = pricing.pricing_run(_small_system(), rules)
    assert p.dispatch.dispatch['ruc'] == pytest.approx(40.0) and p.dispatch.system_lambda == pytest.approx(120.0, abs=0.1)   # dear at 10 MW
    assert p.relaxed_mw == pytest.approx(40.0) and p.pricing.dispatch['ruc'] == pytest.approx(0.0)
    assert p.energy_adder == pytest.approx(80.0, abs=0.2)                  # dear now makes 50 MW: $200 against $120
    q = pricing.pricing_run(_small_system(), rules, deployed_load_mw=30.0)
    assert q.added_demand_mw == pytest.approx(30.0) and q.energy_adder > p.energy_adder
    quiet = _small_system()
    quiet.resources['status'] = 'ON'                                     # no RUC unit, nothing deployed: no pricing run
    assert pricing.pricing_run(quiet, rules).energy_adder == 0.0
    assert pricing.pricing_run(quiet, rules, always=True).pricing is not pricing.pricing_run(quiet, rules).dispatch
    low = _small_system(ruc_price=60.0)
    assert pricing.below_ruc_floor(low) == ['ruc']
    opted = pricing.pricing_run(low, rules, opted_out=['ruc'])           # opted out of RUC settlement: left alone
    assert opted.relaxed_mw == 0.0 and opted.energy_adder == pytest.approx(0.0, abs=1e-6)
