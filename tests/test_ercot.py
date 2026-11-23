"""The ERCOT adapter. The repository ships no market data, so the tests that read ERCOT's files need a folder of
your own: one SCED run or more of an operating day on or after January 1, 2026, laid out as docs/ercot.md describes.
Point OPENSCED_ERCOT_FOLDER at it (default: examples/ercot/2026-08-12_1700, which is not in the repository). Without
it those tests are skipped; the others build their own small tables."""
import os

import numpy as np
import pandas as pd
import pytest

import opensced

FOLDER = os.environ.get('OPENSCED_ERCOT_FOLDER') or os.path.join(os.path.dirname(__file__), '..', 'examples', 'ercot', '2026-08-12_1700')
EXTRA = os.path.join(FOLDER, 'not_published_by_ercot')
ercot = opensced.market('ercot')


@pytest.fixture(scope='module')
def day():
    if not os.path.isdir(FOLDER):
        pytest.skip('no ERCOT files: set OPENSCED_ERCOT_FOLDER to a folder of your own')
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
    assert out.system_lambda <= 5000 and {lim.name for lim in ercot.rules.latest.limits} == {'FFR', 'relay loads + FFR', 'ECRS from loads', 'Non-Spin from loads'}


def test_non_spin_from_loads_is_the_requirement_less_the_largest_contingency(day):
    t = pd.Timestamp(day.times[0])
    plan = pd.DataFrame({'postedDatetime': [t - pd.Timedelta(days=1), t - pd.Timedelta(hours=6), t + pd.Timedelta(hours=1)],
                         'deliveryDate': str(t.date()), 'hourEnding': f'{t.hour + 1:02d}:00', 'ancillaryType': 'NSPIN',
                         'quantity': [9000, 1440, 8000], 'DSTFlag': False})
    need = ercot.adapter.reserve_requirements(plan, t)                   # the latest posting made before the run
    assert need.to_dict('records') == [{'product': 'NonSpin', 'mw': 1440.0}]
    assert ercot.adapter.reserve_requirements(plan.assign(deliveryDate='2020-01-01'), t) is None
    i = day.inputs(t)
    nclr = i.resources.name[i.resources.type == 'NCLR']
    held = lambda x: ercot.clear(x).reserve_awards.pipe(lambda a: a.loc[a.index.isin(nclr), 'NonSpin'].sum())
    assert held(i.copy(reserve_requirements=need)) <= 1440 - 1430.2 + 1e-6   # (the cap's arithmetic is tested in test_core)


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
    assert st['STARTUP'].reserves == {} and st['STARTUP-NS'].reserves == {'ONRES': ('NonSpin',)} and not st['STARTUP-NS'].dispatchable
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


def test_pricing_run_caps_mitigated_ruc_units_at_their_step_one_price():
    from opensced.markets.ercot import pricing
    rules = opensced.Rules(shortage_price=5001.0, block_refine=3)
    c = _small_system()
    line = pd.DataFrame([{'name': 'line', 'limit': 80.0, 'flow': 100.0, 'max_shadow_price': 3500.0, 'competitive': False}])
    c = c.copy(constraints=line, shift_factors=pd.DataFrame([[1.0, 0.0, 0.0]], index=['line'], columns=['cheap', 'ruc', 'dear']))
    left = pricing.pricing_run(c, rules)                                   # not subject to mitigation: stays at the penalty price
    assert left.pricing.dispatch['ruc'] == pytest.approx(0.0, abs=0.01) and left.energy_adder == pytest.approx(80.0, abs=0.3)
    p = pricing.pricing_run(c, rules, mitigated=['ruc'])
    assert p.dispatch.system_lambda == pytest.approx(160.0, abs=0.2)       # cheap held to 80, ruc at 40, dear at 30
    assert p.pricing.step1.system_lambda == pytest.approx(200.0, abs=0.2)  # step 1, the line left out: ruc priced out, dear at 50
    assert p.pricing.reference_prices['ruc'] == pytest.approx(200.0, abs=0.2)
    # step 2, the line back: dear would need 70 MW at $240, so the RUC unit comes back at its $200 reference price
    assert p.pricing.dispatch['ruc'] == pytest.approx(20.0, abs=0.5) and p.energy_adder == pytest.approx(40.0, abs=0.3)


def test_opted_out_units_are_read_off_the_relaxed_capacity():
    from opensced.markets.ercot import pricing
    c = _small_system()
    extra = c.resources[c.resources.name == 'ruc'].assign(name='ruc2', low=25.0, ramp_low=25.0, output=25.0, telemetered=25.0)
    c = c.copy(resources=pd.concat([c.resources, extra], ignore_index=True),
               energy_offers=pd.concat([c.energy_offers, pd.DataFrame({'resource': 'ruc2', 'mw': [0.0, 60.0], 'price': 250.0})], ignore_index=True))
    assert pricing.opted_out_from_relaxed(c, 65.0) == []                 # both relaxed
    assert pricing.opted_out_from_relaxed(c, 40.0) == ['ruc2'] and pricing.opted_out_from_relaxed(c, 25.0) == ['ruc']
    assert pricing.opted_out_from_relaxed(c, 0.0) == ['ruc', 'ruc2'] and pricing.opted_out_from_relaxed(c, 50.0) is None


def test_qualified_mw_caps_a_reserve_limit(day):
    t = day.times[0]
    i = day.inputs(t)
    lim = i.reserve_limits[i.reserve_limits['product'] == 'NonSpin'].sort_values('mw').iloc[-1]
    q = pd.DataFrame([{'resource': lim.resource, 'product': 'NonSpin', 'mw': 1.5}])
    capped = day.inputs(t, qualified_mw=q).reserve_limits.set_index(['resource', 'product']).mw
    assert capped[(lim.resource, 'NonSpin')] == pytest.approx(1.5) and lim.mw > 1.5
    assert capped.drop((lim.resource, 'NonSpin')).sum() == pytest.approx(i.reserve_limits.mw.sum() - lim.mw)   # nothing else moved
    from opensced.markets.ercot import helpers
    seen = helpers.qualified_mw(pd.concat([day.tables['load_resources']] * 3), min_runs=3)   # the same run three times
    L = day.tables['load_resources']
    has_bid = pd.to_numeric(L['SCEDBidCurveMW1'], errors='coerce').notna()
    assert set(seen['resource']) <= set(L.loc[has_bid, 'resourceName'].astype(str).str.strip()) and (seen['mw'] > 0).all()


def test_a_controllable_load_with_no_bid_gets_the_proxy_bid(day):
    t = day.times[0]
    L = day.tables['load_resources'].copy()
    ctrl = pd.to_numeric(L['SCEDBidCurveMW1'], errors='coerce').notna() & (L['telResStatus'].astype(str).str.strip() == 'ONL')
    name = L.loc[ctrl, 'resourceName'].astype(str).str.strip().iloc[0]
    row = L['resourceName'].astype(str).str.strip() == name
    L.loc[row, [c for c in L.columns if c.startswith('SCEDBidCurve')]] = np.nan
    i = ercot.adapter.inputs(day.sced, t, load_resources=L)
    bid = i.energy_offers[i.energy_offers.resource == name]
    r = i.resources.set_index('name').loc[name]
    assert (bid.price == 5000.0).all() and bid.mw.min() == pytest.approx(r.low) and bid.mw.max() == pytest.approx(r.high)


def test_a_starting_unit_keeps_non_spin_only_when_named(day):
    t = day.times[0]
    base = day.inputs(t)
    ro = base.reserve_offers
    on = base.resources[(base.resources['status'] == 'ON') & (base.resources['kind'] == 'generator')]['name']
    offers_ns = set(ro.loc[(ro['product'] == 'NonSpin') & ro['block'].str.startswith('ONRES'), 'resource'])
    name = next(n for n in on if n in offers_ns)
    g = day.sced.copy()
    g.loc[g['Resource Name'].astype(str).str.strip() == name, 'Telemetered Resource Status'] = 'STARTUP'
    kw = dict(reserve_offers=day.tables['reserve_offers'], load_resources=day.tables['load_resources'],
              reserve_demand=day.tables['reserve_demand'])
    plain = ercot.adapter.inputs(g, t, **kw)                         # 3.9.1(5)(b): a unit in STARTUP carries no reserve
    assert name not in set(plain.reserve_offers['resource']) and name not in set(plain.reserve_limits['resource'])
    kept = ercot.adapter.inputs(g, t, startup_non_spin=[name], **kw)   # 6.4.9.1.1(4)-(5): the named ones keep Non-Spin
    r = kept.resources.set_index('name').loc[name]
    assert r['status'] == 'STARTUP-NS' and not r['dispatchable']
    mine = kept.reserve_offers[kept.reserve_offers['resource'] == name]
    assert len(mine) and set(mine['product']) == {'NonSpin'} and mine['block'].str.startswith('ONRES').all()
    assert set(kept.reserve_limits.loc[kept.reserve_limits['resource'] == name, 'product']) >= {'NonSpin'}


def test_day_names_the_starting_units_that_keep_non_spin():
    from opensced.markets.ercot.adapter import Day, TS, RES
    T = pd.date_range('2026-01-28 07:00', periods=4, freq='5min')
    rows = []
    for n, st, ns in [('CARRIED', ['OFF', 'OFF', 'STARTUP', 'STARTUP'], [58, 58, 0, 0]),      # held off-line Non-Spin, then starts
                      ('SELF', ['OFF', 'OFF', 'STARTUP', 'STARTUP'], [0, 0, 0, 0]),             # starts with no award before
                      ('QUICK', ['OFFQS', 'OFFQS', 'STARTUP', 'ON'], [0, 0, 0, 0])]:            # a quick-start unit
        rows += [{TS: t, RES: n, 'Telemetered Resource Status': s, 'ASAwardsNSPIN': a} for t, s, a in zip(T, st, ns)]
    d = object.__new__(Day)
    d.sced = pd.DataFrame(rows)
    d.quick_start = ['QUICK']
    d._startup = d._startups(pd.DataFrame({'product': ['NonSpin'], 'start': ['2026-01-28 07:12'], 'end': ['2026-01-28 09:15']}))
    assert d.startup_non_spin(T[2]) == ['QUICK']                     # 07:10: Non-Spin not deployed yet
    assert d.startup_non_spin(T[3]) == ['CARRIED', 'QUICK']          # 07:15: deployed, and it carried Non-Spin before starting
    d._startup = d._startups(None)
    assert d.startup_non_spin(T[3]) == ['QUICK']                     # no deployment times: only quick-start units


def test_the_websites_reserve_offer_csv_reads_like_the_apis(day):
    from opensced.markets.ercot import adapter as A
    t = day.times[0]
    api = day.tables['reserve_offers']
    back = {'ECRS': 'ECRS', **{v: k for k, v in A._OFFER_PRODUCT.items() if k != v}}   # the short codes of the files posted to April 2026
    names = {'SCEDTimestamp': 'SCED Timestamp', 'repeatHourFlag': 'Repeated Hour Flag', 'resourceName': 'Resource Name', 'offerType': 'Offer Type'}
    for c in api.columns:
        if c.startswith('price'):
            names[c] = f'PRICE{c[5]}_{back[c[6:]]}'
        elif c.startswith('quantityMW'):
            names[c] = f'QUANTITY_MW{c[-1]}'
    web = api.rename(columns=names)
    web['SCED Timestamp'] = pd.to_datetime(web['SCED Timestamp']).dt.strftime('%m/%d/%Y %H:%M:%S')
    web['Repeated Hour Flag'] = 'N'
    kw = dict(load_resources=day.tables['load_resources'], reserve_demand=day.tables['reserve_demand'])
    a = ercot.adapter.inputs(day.sced, t, reserve_offers=api, **kw).reserve_offers
    b = ercot.adapter.inputs(day.sced, t, reserve_offers=web, **kw).reserve_offers
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))
    later = web.rename(columns={c: c[:c.index('_') + 1] + p for c in web.columns for p in back if c.startswith('PRICE') and c.split('_', 1)[1] == back[p]})
    assert 'PRICE1_NSPIN' in later and 'PRICE1_NS' not in later       # later files spell the product codes as the API does
    c = ercot.adapter.inputs(day.sced, t, reserve_offers=later, **kw).reserve_offers
    pd.testing.assert_frame_equal(a.reset_index(drop=True), c.reset_index(drop=True))
    with pytest.raises(ValueError, match='does not know'):
        ercot.adapter.inputs(day.sced, t, reserve_offers=later.rename(columns={'PRICE1_NSPIN': 'PRICE1_NEWPRODUCT'}), **kw)


def test_a_file_with_blank_prices_before_february_2026_is_read_as_corrected():
    """ERCOT's daily files for December 5, 2025 to February 2, 2026 write a blank price as 0; its corrected files do not."""
    from opensced.markets.ercot import adapter as A
    rules = opensced.market('ercot').rules.on('2026-01-10')
    zero_filled = _offer_rows(U={'ECRS': 3.0})                       # every other block-1 price is 0
    r = A._reserve_offers(zero_filled, {'U': 'ON'}, '2026-01-10 12:00:10', rules)
    assert not ((r['price'] == 0) & r['block'].str.endswith('-1')).any()         # a 0 reads as "not offered"
    corrected = zero_filled.copy()
    corrected[[c for c in corrected.columns if c.startswith('price1') and c not in ('price1ECRS', 'price1REGUP')]] = np.nan
    r = A._reserve_offers(corrected, {'U': 'ON'}, '2026-01-10 12:00:10', rules)
    zero = r[(r['price'] == 0) & r['block'].str.endswith('-1')]
    assert set(zero['product']) == {'RegUp'} and zero.mw.iloc[0] == 10.0           # the 0 that is left is a real $0 offer


def test_a_blank_status_takes_the_units_previous_status(day):
    from opensced.markets.ercot.adapter import Day, TS, RES
    t = day.times[0]
    base = day.inputs(t)
    r0 = base.resources.set_index('name')
    name = next(n for n in r0.index[(r0['status'] == 'ON') & (r0['kind'] == 'generator') & r0['dispatchable']]
                if n in set(base.reserve_limits['resource']))
    g = day.sced.copy()
    g.loc[g['Resource Name'].astype(str).str.strip() == name, 'Telemetered Resource Status'] = None      # ERCOT's file prints NA
    kw = dict(reserve_offers=day.tables['reserve_offers'], load_resources=day.tables['load_resources'], reserve_demand=day.tables['reserve_demand'])
    blank = ercot.adapter.inputs(g, t, **kw)
    assert not blank.resources.set_index('name').loc[name, 'dispatchable'] and name not in set(blank.reserve_limits['resource'])
    kept = ercot.adapter.inputs(g, t, status_overrides={name: 'ON'}, **kw)
    assert kept.resources.set_index('name').loc[name, 'dispatchable'] and name in set(kept.reserve_limits['resource'])
    T = pd.date_range('2026-01-28 06:55', periods=3, freq='5min')         # Day works the previous status out
    d = object.__new__(Day)
    d.sced = pd.DataFrame([{TS: T[0], RES: 'HYDRO', 'Telemetered Resource Status': 'OFFQS'}, {TS: T[1], RES: 'HYDRO', 'Telemetered Resource Status': None},
                           {TS: T[2], RES: 'HYDRO', 'Telemetered Resource Status': 'ON'}, {TS: T[1], RES: 'NEW', 'Telemetered Resource Status': None}])
    assert d._previous_status() == {T[1]: {'HYDRO': 'OFFQS'}}            # a unit blank from its first run has no previous status
    assert day.blank_status == 'previous'
    with pytest.raises(ValueError, match="'none' or 'previous'"):
        day.inputs(t, blank_status='next')


def test_off_line_units_on_ercots_proxy_offer_are_read_off_the_awards():
    from opensced.markets.ercot import helpers
    from opensced.markets.ercot.adapter import TS, RES
    t = '2026-01-28T06:45:20'
    sced = pd.DataFrame([{TS: t, RES: n, 'Telemetered Resource Status': st, 'ASAwardsNSPIN': a}
                         for n, st, a in [('PROXY', 'OFF', 155.0), ('OFFERED', 'OFF', 60.0), ('IDLE', 'OFF', 0.0), ('RUNNING', 'ON', 40.0)]])
    P = ['REGUP', 'REGDN', 'RRSPFR', 'RRSUFR', 'RRSFFR', 'NSPIN', 'ECRS']
    def row(name, own):                                                  # an off-line offer row: block 1 the QSE's, block 6 ERCOT's proxy
        r = {'SCEDTimestamp': t, 'resourceName': name, 'offerType': 'OFFNS', 'quantityMW1': 50.0 if own else 0.0, 'quantityMW6': 155.0}
        r.update({f'price1{p}': (20.0 if own and p == 'NSPIN' else np.nan) for p in P})
        r.update({f'price6{p}': (14.99 if p == 'NSPIN' else np.nan) for p in P})
        return r
    offers = pd.DataFrame([row('PROXY', False), row('OFFERED', True), row('IDLE', False), row('RUNNING', False)])
    assert helpers.offline_proxy_units(sced, offers) == ['PROXY']        # awarded while OFF with no Non-Spin offer of its own
    assert helpers.offline_proxy_units(sced, offers, min_runs=2) == []


def test_the_websites_disclosure_csvs_read_like_the_apis(day, tmp_path):
    """ERCOT's website names the columns "AS Capability REGUP", "State of Charge", "SCED Bid to Buy Curve-MW1", ...;
    its API names them ASCapREGUP, SOC, SCEDBidCurveMW1. Both give the same input tables."""
    from opensced.markets.ercot import adapter
    back = {v: k for k, v in adapter.CANON.items() if k.startswith(('AS Capability', 'State of', 'Minimum SOC', 'Maximum SOC'))}
    load_back = {v: k for k, v in adapter.LOAD_CANON.items() if k != 'SCED Timestamp'}
    for key, stem in adapter.FILES.items():
        t = day.tables[key]
        if t is None:
            continue
        raw = adapter._read(FOLDER, stem)
        if key in ('gen', 'esr'):
            raw = raw.rename(columns=back)
        if key == 'load_resources':
            raw = raw.rename(columns=load_back)
            assert 'Resource Name' in raw and 'resourceName' not in raw
        raw.to_csv(tmp_path / f'{stem}.csv', index=False)
    web = ercot.read_day(str(tmp_path))
    run = day.times[0]
    a, b = web.inputs(run), day.inputs(run)
    assert len(a.storage) == len(b.storage) > 0
    for name in ('resources', 'storage', 'reserve_limits', 'reserve_offers', 'energy_offers'):
        x, y = getattr(a, name), getattr(b, name)
        assert len(x) == len(y), name
        num = [c for c in x.columns if pd.api.types.is_numeric_dtype(x[c]) and not pd.api.types.is_bool_dtype(x[c])]
        assert np.allclose(x[num].to_numpy(float), y[num].to_numpy(float), equal_nan=True), name


def test_a_day_without_state_of_charge_or_capability_columns_warns(day, tmp_path):
    from opensced.markets.ercot import adapter
    for key in ('gen', 'esr'):
        raw = adapter._read(FOLDER, adapter.FILES[key])
        raw.drop(columns=[c for c in raw.columns if c in ('SOC', 'minSOC', 'maxSOC') or c.startswith('ASCap')]).to_csv(
            tmp_path / f'{adapter.FILES[key]}.csv', index=False)
    with pytest.warns(UserWarning) as seen:
        ercot.read_day(str(tmp_path))
    text = ' '.join(str(w.message) for w in seen)
    assert 'state of charge' in text and 'reserve capability' in text


def test_a_missing_scoring_file_names_the_report(day, tmp_path):
    from opensced.markets.ercot import adapter
    adapter._read(FOLDER, adapter.FILES['gen']).to_csv(tmp_path / f'{adapter.FILES["gen"]}.csv', index=False)
    partial = ercot.read_day(str(tmp_path))
    with pytest.raises(FileNotFoundError, match='NP6-322-CD'):
        partial.published_lambda()
