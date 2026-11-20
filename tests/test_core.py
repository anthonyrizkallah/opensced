import numpy as np
import pandas as pd
import pytest

import opensced
from opensced import Inputs, Limit, Product, Rules, clear


def case(units, demand, **kw):
    """units: {name: (low, high, price)} with flat offers."""
    res = pd.DataFrame([{'name': n, 'low': lo, 'high': hi} for n, (lo, hi, _) in units.items()])
    off = pd.DataFrame([{'resource': n, 'mw': m, 'price': p} for n, (lo, hi, p) in units.items() for m in (lo, hi)])
    return Inputs(resources=res, demand=demand, energy_offers=off, **kw)


LINE = pd.DataFrame([{'name': 'line', 'limit': 60.0, 'flow': 0.0, 'max_shadow_price': 3500.0}])


def test_merit_order_sets_lambda():
    out = clear(case({'cheap': (0, 100, 20.0), 'dear': (0, 100, 50.0)}, 150))
    assert out.solved and out.system_lambda == pytest.approx(50.0)
    assert out.dispatch['cheap'] == pytest.approx(100) and out.dispatch['dear'] == pytest.approx(50)


def test_shortage_prices_at_the_rulebook_price():
    out = clear(case({'only': (0, 100, 20.0)}, 120), Rules(shortage_price=9000.0))
    assert out.system_lambda == pytest.approx(9000.0) and out.shortfall == pytest.approx(20.0)


def test_a_resource_that_is_not_dispatchable_stays_at_its_output():
    c = case({'held': (0, 100, 0.0), 'unit': (0, 100, 30.0)}, 90)
    c.resources['dispatchable'] = [False, True]
    c.resources['output'] = [40.0, 0.0]
    out = clear(c)
    assert out.dispatch['held'] == pytest.approx(40) and out.dispatch['unit'] == pytest.approx(50)


def test_ramp_limits_narrow_the_range():
    c = case({'slow': (0, 100, 10.0), 'dear': (0, 100, 50.0)}, 90)
    c.resources['ramp_high'] = [30.0, 100.0]
    assert clear(c).dispatch['slow'] == pytest.approx(30)


def test_congestion_splits_node_prices():
    sf = pd.DataFrame([[1.0, 0.0]], index=['line'], columns=['cheap', 'dear'])
    out = clear(case({'cheap': (0, 100, 20.0), 'dear': (0, 100, 50.0)}, 90, constraints=LINE, shift_factors=sf))
    assert out.dispatch['cheap'] == pytest.approx(60) and out.system_lambda == pytest.approx(50.0)
    assert out.shadow_prices['line'] == pytest.approx(30.0)
    assert out.node_prices()['cheap'] == pytest.approx(20.0)
    assert list(out.binding.index) == ['line']


def test_flow_is_measured_at_each_resources_output():
    sf = pd.DataFrame([[1.0, 0.0]], index=['line'], columns=['cheap', 'dear'])
    c = case({'cheap': (0, 100, 20.0), 'dear': (0, 100, 50.0)}, 90, constraints=LINE.assign(flow=80.0), shift_factors=sf)
    c.resources['output'] = [80.0, 10.0]                # 80 MW on the line with cheap at 80: it must back down 20
    assert clear(c).dispatch['cheap'] == pytest.approx(60)


def test_a_constraint_nothing_can_relieve_prices_at_its_cap():
    sf = pd.DataFrame([[1.0, 0.0]], index=['line'], columns=['must', 'dear'])
    out = clear(case({'must': (70, 70, 0.0), 'dear': (0, 100, 50.0)}, 90, constraints=LINE, shift_factors=sf))
    assert out.solved and out.shadow_prices['line'] == pytest.approx(3500.0)
    assert out.violations['line'] == pytest.approx(10.0)


def test_node_shift_factors_with_a_resource_to_node_map():
    node_sf = pd.DataFrame([[1.0, 0.0, 0.5]], index=['line'], columns=['export', 'load', 'hub'])
    c = case({'cheap': (0, 100, 20.0), 'dear': (0, 100, 50.0), 'lost': (0, 10, 500.0)}, 90, constraints=LINE,
             shift_factors=node_sf, resource_nodes={'cheap': 'export', 'dear': 'load'})
    out = clear(c)
    assert out.shadow_prices['line'] == pytest.approx(30.0)
    assert out.node_prices()['hub'] == pytest.approx(35.0)                 # a node with no resource is still priced
    assert out.resource_prices()['cheap'] == pytest.approx(20.0)
    assert opensced.unmapped(c) == ['lost']


def test_a_resource_split_over_two_nodes_takes_the_weighted_shift_factor():
    node_sf = pd.DataFrame([[1.0, 0.0]], index=['line'], columns=['a', 'b'])
    where = pd.DataFrame({'resource': ['train', 'train', 'solo'], 'node': ['a', 'b', 'b'], 'share': [0.25, 0.75, 1.0]})
    sf = opensced.resource_shift_factors(node_sf, where)
    assert sf.loc['line', 'train'] == pytest.approx(0.25) and sf.loc['line', 'solo'] == pytest.approx(0.0)


def test_sloped_curve_is_cut_into_blocks_priced_at_midpoints():
    res = pd.DataFrame([{'name': 'u', 'low': 0.0, 'high': 20.0}])
    off = pd.DataFrame({'resource': 'u', 'mw': [0.0, 20.0], 'price': [10.0, 30.0]})
    assert clear(Inputs(res, 12, off)).system_lambda == pytest.approx(22.5)
    assert clear(Inputs(res, 12, off), Rules(block_mw=1.0)).system_lambda == pytest.approx(21.5)


RESERVE = Rules(products=(Product('Up', 'up', duration_hours=1.0),))


def with_reserve(units, demand, width=30.0, price=200.0, can=None):
    c = case(units, demand)
    c.reserve_limits = pd.DataFrame([{'resource': n, 'product': 'Up', 'mw': 1000.0} for n in (can or units)])
    c.reserve_demand = pd.DataFrame({'product': 'Up', 'mw': [0.0, width], 'price': [price, price]})
    return c


def test_reserves_raise_the_energy_price_when_headroom_is_short():
    slack = clear(with_reserve({'u': (0, 100, 20.0)}, 60), RESERVE)        # 40 MW of headroom covers 30 MW of reserve
    tight = clear(with_reserve({'u': (0, 100, 20.0)}, 90), RESERVE)        # 10 MW left: energy displaces reserve
    assert slack.system_lambda == pytest.approx(20.0) and slack.reserve_prices['Up'] == pytest.approx(0.0)
    assert tight.system_lambda == pytest.approx(220.0) and tight.reserve_prices['Up'] == pytest.approx(200.0)
    assert tight.reserve_awards.loc['u', 'Up'] == pytest.approx(10.0)


def test_reserve_offers_limit_and_price_awards():
    c = with_reserve({'a': (0, 100, 20.0), 'b': (0, 100, 25.0)}, 50)
    c.reserve_offers = pd.DataFrame([{'resource': 'a', 'block': '1', 'mw': 10.0, 'product': 'Up', 'price': 5.0},
                                     {'resource': 'b', 'block': '1', 'mw': 50.0, 'product': 'Up', 'price': 8.0}])
    out = clear(c, RESERVE)
    assert out.reserve_awards.loc['a', 'Up'] == pytest.approx(10.0) and out.reserve_awards.loc['b', 'Up'] == pytest.approx(20.0)
    assert out.reserve_prices['Up'] == pytest.approx(8.0)


def test_a_battery_cannot_sell_reserve_it_has_no_energy_for():
    c = with_reserve({'gen': (0, 100, 20.0), 'bat': (-20, 20, 0.0)}, 50, can=['bat'])
    c.energy_offers = c.energy_offers[c.energy_offers.resource == 'gen']
    c.energy_offers = pd.concat([c.energy_offers, pd.DataFrame({'resource': 'bat', 'mw': [-20.0, 0.0, 0.0, 20.0], 'price': [100.0, 100.0, 500.0, 500.0]})])   # it will pay up to $100 to charge
    c.storage = pd.DataFrame([{'resource': 'bat', 'soc': 5.0, 'soc_min': 0.0, 'soc_max': 40.0}])
    out = clear(c, RESERVE)
    # it charges at 20 MW for 5 minutes, which adds 20/12 MWh to the 5 MWh it holds: that sustains 6.67 MW for the hour
    assert out.dispatch['bat'] == pytest.approx(-20.0)
    assert out.reserve_awards.loc['bat', 'Up'] == pytest.approx(5.0 + 20.0 / 12)
    assert clear(c, RESERVE.replace(features=('network', 'reserves'))).reserve_awards.loc['bat', 'Up'] >= 30.0   # no energy check at all
    old = clear(c, RESERVE.replace(storage_charge_offset=True))         # the older reading: all 20 MW of charging count
    assert old.reserve_awards.loc['bat', 'Up'] == pytest.approx(25.0)


def test_several_products_can_serve_one_demand_curve_and_one_can_have_mw_reserved():
    def run(reserved):
        rules = Rules(products=(Product('Slow', 'up', demand='Up', reserved_mw=reserved), Product('Fast', 'up', demand='Up')))
        c = case({'gen': (0, 200, 20.0), 'relay': (0, 100, 0.0)}, 50)
        c.resources['dispatchable'] = [True, False]
        c.reserve_limits = pd.DataFrame([{'resource': 'gen', 'product': 'Slow', 'mw': 100.0}, {'resource': 'relay', 'product': 'Fast', 'mw': 100.0}])
        c.reserve_offers = pd.DataFrame([{'resource': 'gen', 'block': '1', 'mw': 100.0, 'product': 'Slow', 'price': 10.0},
                                         {'resource': 'relay', 'block': '1', 'mw': 100.0, 'product': 'Fast', 'price': 1.0}])
        c.reserve_demand = pd.DataFrame({'product': 'Up', 'mw': [0.0, 60.0], 'price': [200.0, 200.0]})
        return clear(c, rules)
    free, kept = run(0.0), run(40.0)
    assert free.reserve_awards['Fast'].sum() == pytest.approx(60.0)             # the cheap product fills the curve
    assert kept.reserve_awards['Fast'].sum() == pytest.approx(20.0) and kept.reserve_awards['Slow'].sum() == pytest.approx(40.0)
    assert list(kept.reserve_prices.index) == ['Up'] and kept.reserve_prices['Up'] == pytest.approx(10.0)
    assert kept.reserve_bought['Up'] == pytest.approx(60.0)


def test_a_limit_caps_a_group_of_products_or_some_resources():
    def run(*limits):
        rules = Rules(products=(Product('Slow', 'up', demand='Up'), Product('Fast', 'up', demand='Up')), limits=limits)
        c = case({'gen': (0, 200, 20.0), 'relay': (0, 100, 0.0)}, 50)
        c.resources['dispatchable'] = [True, False]
        c.resources['type'] = ['GEN', 'LOAD']
        c.reserve_limits = pd.DataFrame([{'resource': 'gen', 'product': 'Slow', 'mw': 100.0}, {'resource': 'relay', 'product': 'Fast', 'mw': 100.0}])
        c.reserve_demand = pd.DataFrame({'product': 'Up', 'mw': [0.0, 60.0], 'price': [200.0, 200.0]})
        return clear(c, rules).reserve_awards.sum()
    assert run(Limit('all', ('Fast', 'Slow'), max_mw=0.0)).sum() == pytest.approx(0.0)
    assert run(Limit('fast', ('Fast',), max_mw=15.0), Limit('slow', ('Slow',), max_mw=0.0))['Fast'] == pytest.approx(15.0)
    assert run(Limit('fast', ('Fast',), max_share=0.5, of='Up'), Limit('slow', ('Slow',), max_mw=0.0))['Fast'] == pytest.approx(30.0)
    loads_only = run(Limit('loads', ('Fast', 'Slow'), max_mw=10.0, where=(('type', 'LOAD'),)), Limit('slow', ('Slow',), max_mw=0.0))
    assert loads_only['Fast'] == pytest.approx(10.0)
    left = lambda mw: run(Limit('loads', ('Fast',), max_less=mw, of='Up', where=(('type', 'LOAD'),)), Limit('slow', ('Slow',), max_mw=0.0))['Fast']
    assert left(45.0) == pytest.approx(15.0)                             # a 60 MW requirement less 45 MW
    assert left(80.0) == pytest.approx(0.0)                              # never below zero
    with pytest.raises(ValueError, match='max_mw or max_share'):
        Limit('bad', ('Fast',))
    with pytest.raises(ValueError, match='need `of`'):
        Limit('bad', ('Fast',), max_less=10.0)


def test_prices_are_capped_after_the_solve_when_the_rulebook_says_so():
    sf = pd.DataFrame([[1.0, 0.0]], index=['line'], columns=['a', 'b'])
    c = case({'a': (0, 100, 20.0), 'b': (0, 10, 50.0)}, 120, constraints=LINE.assign(limit=500.0), shift_factors=sf)
    raw = clear(c, Rules(shortage_price=9000.0))
    capped = clear(c, Rules(shortage_price=9000.0, price_cap=5000.0))
    assert raw.system_lambda == pytest.approx(9000.0) and capped.system_lambda == pytest.approx(5000.0)
    assert capped.uncapped['system_lambda'] == pytest.approx(9000.0)
    assert (capped.node_prices() <= 5000.0 + 1e-9).all()


def test_small_shift_factors_are_ignored_below_the_cutoff():
    sf = pd.DataFrame([[0.00005, 0.0]], index=['line'], columns=['cheap', 'dear'])
    c = case({'cheap': (0, 100, 20.0), 'dear': (0, 100, 50.0)}, 90, constraints=LINE.assign(limit=0.001, max_shadow_price=1e9), shift_factors=sf)
    assert clear(c).dispatch['cheap'] < 90 and clear(c, Rules(shift_factor_cutoff=0.0001)).dispatch['cheap'] == pytest.approx(90)


def test_rulebooks_by_date_and_drafts():
    books = opensced.Rulebooks([Rules(name='a', effective='2025-01-01'), Rules(name='b', effective='2026-01-01', shortage_price=9000.0)])
    assert books.on('2025-06-01').name == 'a' and books.on('2026-06-01').name == 'b' and books.latest.name == 'b'
    with pytest.raises(LookupError, match='earliest'):
        books.on('2024-01-01')
    draft = RESERVE.replace(name='draft', products={'Up': {'duration_hours': 2.0}})
    assert draft.product('Up').duration_hours == 2.0 and RESERVE.product('Up').duration_hours == 1.0
    assert list(RESERVE.diff(draft)) == ['products.Up']


@pytest.mark.parametrize('change, message', [
    (lambda c: c.resources.__setitem__('low', 150.0), 'low > high'),
    (lambda c: setattr(c, 'resources', pd.concat([c.resources, c.resources])), 'must be unique'),
    (lambda c: setattr(c, 'resources', c.resources.drop(columns='high')), "missing column"),
    (lambda c: setattr(c, 'demand', 'lots'), 'expected one number'),
    (lambda c: setattr(c, 'constraints', LINE), 'without shift_factors'),
    (lambda c: setattr(c, 'energy_offers', c.energy_offers.assign(resource='ghost')), 'not in the resources table'),
])
def test_validation_names_the_table_and_the_problem(change, message):
    c = case({'u': (0, 100, 20.0)}, 10)
    change(c)
    with pytest.raises(ValueError, match=message):
        clear(c)


def test_a_misspelled_product_is_caught():
    c = with_reserve({'u': (0, 100, 20.0)}, 60)
    c.reserve_limits['product'] = 'up'
    with pytest.raises(ValueError, match="unknown product 'up'"):
        clear(c, RESERVE)


def test_examples_and_schema():
    r = clear(opensced.examples.three_bus())
    assert r.node_prices()['WEST'] == pytest.approx(5.0) and len(r.binding) == 1
    assert 'max_shadow_price' in opensced.schema('constraints') and 'resources' in opensced.schema()
    assert 'ercot' in opensced.list_markets()
    with pytest.raises(NotImplementedError):
        opensced.market('pjm')
    assert np.isfinite(float(repr(r).split('$')[1].split()[0]))


def test_clip_curve_cuts_exactly_where_the_curve_crosses_a_bound():
    from opensced.core.features.mitigation import clip_curve
    mw, price = clip_curve([0.0, 10.0, 20.0], [-250.0, 50.0, 90.0], floor=-20.0, cap=70.0)
    assert price.min() == pytest.approx(-20.0) and price.max() == pytest.approx(70.0)
    assert mw[1] == pytest.approx(10 * 230 / 300) and mw[-2] == pytest.approx(15.0)      # the two crossing points
    assert np.interp(9.0, mw, price) == pytest.approx(20.0)                                # untouched in between
    mw, price = clip_curve([0.0, 10.0], [0.0, 100.0], cap=([0.0, 10.0], [50.0, 30.0]))     # a cap that falls with output
    assert price[-1] == pytest.approx(30.0) and np.interp(2.0, mw, price) == pytest.approx(20.0)


def test_two_step_clearing_floors_every_offer_and_caps_the_mitigated_one():
    # cheap is behind a non-competitive line; dear, at the load, can name its price when the line binds
    res = pd.DataFrame({'name': ['cheap', 'dear'], 'low': [0.0, 0.0], 'high': [100.0, 100.0],
                        'category': ['wind', 'gas'], 'mitigated': [False, True]})
    off = pd.DataFrame({'resource': ['cheap', 'cheap', 'dear', 'dear'], 'mw': [0.0, 100.0, 0.0, 100.0], 'price': [-200.0, -200.0, 900.0, 900.0]})
    cons = LINE.assign(competitive=False)
    sf = pd.DataFrame([[1.0, 0.0]], index=['line'], columns=['cheap', 'dear'])
    case_ = Inputs(res, 90, off, constraints=cons, shift_factors=sf,
                   mitigated_offer_caps=pd.DataFrame({'resource': 'dear', 'mw': [0.0, 100.0], 'price': [40.0, 40.0]}))
    one = clear(case_)
    assert one.system_lambda == pytest.approx(900.0) and one.reference_prices is None
    rules = Rules(two_step=True, mitigated_offer_floors={'wind': -100.0, 'other': -50.0})
    two = clear(case_, rules)
    assert two.step1.system_lambda == pytest.approx(-200.0)             # step 1: no line, the cheap unit sets the price
    assert two.reference_prices['dear'] == pytest.approx(-200.0)
    assert two.system_lambda == pytest.approx(40.0)                     # step 2: dear is capped at its mitigated offer cap
    assert two.dispatch['cheap'] == pytest.approx(60.0)
    offers = two._inputs.energy_offers.groupby('resource').price.max()
    assert offers['cheap'] == pytest.approx(-200.0)                     # floor = lesser of reference price and -100
    assert clear(case_.copy(mitigated=True), rules).system_lambda == pytest.approx(900.0)   # offers already mitigated: one step
    no_cap = clear(case_.copy(mitigated_offer_caps=None), rules)
    assert no_cap.system_lambda == pytest.approx(-200.0)                # no cap known: capped at its reference price


def seq_case(demand, time):
    res = pd.DataFrame({'name': ['slow', 'fast'], 'low': [0.0, 0.0], 'high': [100.0, 100.0], 'ramp_up': [2.0, 100.0], 'ramp_down': [2.0, 100.0]})
    off = pd.DataFrame({'resource': ['slow', 'slow', 'fast', 'fast'], 'mw': [0.0, 100.0, 0.0, 100.0], 'price': [10.0, 10.0, 80.0, 80.0]})
    return Inputs(res, demand, off, time=pd.Timestamp(time))


def test_a_sequence_starts_each_interval_where_the_last_one_ended():
    steps = [seq_case(40, '2026-01-01 00:00'), seq_case(90, '2026-01-01 00:05'), seq_case(90, '2026-01-01 00:10')]
    alone = opensced.clear_sequence(steps, carry=())
    assert alone.dispatch['slow'].tolist() == pytest.approx([40.0, 90.0, 90.0])          # each interval on its own
    chained = opensced.clear_sequence(steps, Rules(dispatch_minutes=5.0))
    assert chained.dispatch['slow'].tolist() == pytest.approx([40.0, 50.0, 60.0])        # 2 MW a minute for 5 minutes
    assert chained.system_lambda.tolist() == pytest.approx([10.0, 80.0, 80.0])           # the fast unit fills the gap
    second = list(chained.results.values())[1]._inputs.resources.set_index('name')
    assert second.at['slow', 'output'] == pytest.approx(40.0) and second.at['slow', 'ramp_high'] == pytest.approx(50.0)
    with pytest.raises(ValueError, match='unknown'):
        opensced.carry_forward(steps[1], list(chained.results.values())[0], Rules(), carry=('speed',))


def test_state_of_charge_is_carried_and_runs_out():
    def step(time):
        res = pd.DataFrame({'name': ['bat', 'gen'], 'low': [-10.0, 0.0], 'high': [10.0, 100.0]})
        off = pd.DataFrame({'resource': ['bat', 'bat', 'gen', 'gen'], 'mw': [-10.0, 10.0, 0.0, 100.0], 'price': [5.0, 5.0, 50.0, 50.0]})
        c = Inputs(res, 30, off, time=pd.Timestamp(time))
        c.storage = pd.DataFrame([{'resource': 'bat', 'soc': 15.0, 'soc_min': 0.0, 'soc_max': 40.0}])
        c.reserve_limits = pd.DataFrame([{'resource': 'gen', 'product': 'Up', 'mw': 50.0}])
        c.reserve_demand = pd.DataFrame({'product': 'Up', 'mw': [0.0, 5.0], 'price': [1.0, 1.0]})
        return c
    rules = Rules(products=(Product('Up', 'up', duration_hours=1.0),), interval_hours=1.0)
    out = opensced.clear_sequence([step(f'2026-01-01 0{h}:00') for h in range(3)], rules, carry=('soc',))
    soc = [r._inputs.storage.soc.iloc[0] for r in out.results.values()]
    assert soc == pytest.approx([15.0, 5.0, 0.0])                        # 10 MWh out, then the last 5
    assert out.dispatch['bat'].tolist() == pytest.approx([10.0, 5.0, 0.0])
    assert out.system_lambda.iloc[0] == pytest.approx(50.0)


def test_carrying_output_moves_each_constraints_flow_with_it():
    sf = pd.DataFrame([[1.0, 0.0]], index=['line'], columns=['slow', 'fast'])
    def step(demand, time):
        c = seq_case(demand, time)
        c.resources['ramp_up'] = c.resources['ramp_down'] = 1000.0       # ramps never bind here
        c.constraints, c.shift_factors = LINE.copy(), sf                 # 60 MW limit, flow 0 with every unit at output 0
        return c
    steps = [step(40, '2026-01-01 00:00'), step(90, '2026-01-01 00:05')]
    chained = opensced.clear_sequence(steps)
    second = list(chained.results.values())[1]._inputs
    assert second.constraints.flow.iloc[0] == pytest.approx(40.0)        # the slow unit now starts at 40 on the line
    assert chained.dispatch['slow'].tolist() == pytest.approx([40.0, 60.0])   # and the limit still binds at 60


def test_refining_the_blocks_prices_a_sloped_curve_where_it_is_met():
    res = pd.DataFrame([{'name': 'u', 'low': 0.0, 'high': 20.0}])
    off = pd.DataFrame({'resource': 'u', 'mw': [0.0, 20.0], 'price': [10.0, 30.0]})        # $1 per MW: 12 MW is met at $22
    assert clear(Inputs(res, 12, off)).system_lambda == pytest.approx(22.5)                 # a 5 MW step's midpoint
    assert clear(Inputs(res, 12, off), Rules(block_refine=3)).system_lambda == pytest.approx(22.0, abs=0.01)


def test_downward_reserve_needs_room_for_what_charging_would_store():
    """A battery with 10 MWh of room and 80% efficiency: 25 MW of a 30-minute downward product would store
    0.8 x 25 x 0.5 = 10 MWh. While it discharges at 12 MW it frees 1 MWh more in the interval: 27.5 MW."""
    rules = Rules(products=(Product('Down', 'down', duration_hours=0.5),))
    def battery(output_price, efficiency=0.8):
        res = pd.DataFrame([{'name': 'gen', 'low': 0.0, 'high': 100.0}, {'name': 'bat', 'low': -50.0, 'high': 50.0}])
        off = pd.DataFrame({'resource': ['gen', 'gen', 'bat', 'bat'], 'mw': [0.0, 100.0, -50.0, 50.0], 'price': [20.0, 20.0, output_price, output_price]})
        c = Inputs(res, 50, off)
        c.reserve_limits = pd.DataFrame([{'resource': 'bat', 'product': 'Down', 'mw': 1000.0}])
        c.reserve_demand = pd.DataFrame({'product': 'Down', 'mw': [0.0, 40.0], 'price': [200.0, 200.0]})
        c.storage = pd.DataFrame([{'resource': 'bat', 'soc': 30.0, 'soc_min': 0.0, 'soc_max': 40.0, 'efficiency': efficiency}])
        return clear(c, rules)
    idle = battery(20.0)                                                 # same price as the generator: reserve decides
    assert idle.reserve_awards.loc['bat', 'Down'] >= 25.0 - 1e-6
    assert battery(20.0, efficiency=1.0).reserve_awards.loc['bat', 'Down'] <= idle.reserve_awards.loc['bat', 'Down'] + 1e-6   # all of it stored: less fits
    cheap = battery(10.0)                                                # cheaper than the generator: it discharges 50 MW
    assert cheap.dispatch['bat'] == pytest.approx(50.0)
    assert cheap.reserve_awards.loc['bat', 'Down'] == pytest.approx((10.0 + 50.0 / 12) / (0.8 * 0.5))
    dear = battery(30.0)                                                 # dearer: it charges, and charging uses the room too
    p = dear.dispatch['bat']
    assert dear.reserve_awards.loc['bat', 'Down'] == pytest.approx((10.0 - 0.8 * max(-p, 0.0) / 12 + max(p, 0.0) / 12) / (0.8 * 0.5), abs=1e-4)


def test_exact_curves_agree_with_refined_steps():
    """Two sloped units and a reserve: the quadratic solve and the refined steps land on the same prices."""
    pytest.importorskip('highspy')
    res = pd.DataFrame([{'name': 'u', 'low': 0.0, 'high': 20.0}, {'name': 'v', 'low': 0.0, 'high': 20.0}])
    off = pd.DataFrame({'resource': ['u', 'u', 'v', 'v'], 'mw': [0.0, 20.0, 0.0, 20.0], 'price': [10.0, 30.0, 16.0, 26.0]})
    c = Inputs(res, 12, off)
    exact = clear(c, Rules(offer_curves='exact'))
    assert exact.system_lambda == pytest.approx(18.0) and exact.dispatch['u'] == pytest.approx(8.0)   # 10 + p_u = 16 + p_v / 2
    assert clear(c, Rules(block_refine=4)).system_lambda == pytest.approx(18.0, abs=0.01)
    c.reserve_limits = pd.DataFrame([{'resource': n, 'product': 'Up', 'mw': 1000.0} for n in ('u', 'v')])
    c.reserve_demand = pd.DataFrame({'product': 'Up', 'mw': [0.0, 30.0], 'price': [50.0, 50.0]})
    a, b = clear(c, RESERVE.replace(offer_curves='exact')), clear(c, RESERVE.replace(block_refine=4))
    assert a.system_lambda == pytest.approx(b.system_lambda, abs=0.02) and a.reserve_prices['Up'] == pytest.approx(b.reserve_prices['Up'], abs=0.02)


def test_a_curve_that_slopes_away_from_a_limit_is_refined_there_too():
    res = pd.DataFrame([{'name': 'quick', 'low': 0.0, 'high': 30.0}, {'name': 'base', 'low': 0.0, 'high': 100.0}])
    off = pd.DataFrame([{'resource': 'quick', 'mw': 0.0, 'price': -250.0}, {'resource': 'quick', 'mw': 1.0, 'price': 2000.0},
                        {'resource': 'quick', 'mw': 30.0, 'price': 2000.0},
                        {'resource': 'base', 'mw': 0.0, 'price': 200.0}, {'resource': 'base', 'mw': 100.0, 'price': 200.0}])
    c = Inputs(resources=res, demand=50.0, energy_offers=off)
    assert clear(c).dispatch['quick'] == pytest.approx(0.0)               # its first whole step costs 875: left at its limit
    out = clear(c, Rules(block_refine=3))
    assert out.dispatch['quick'] == pytest.approx(0.2, abs=0.01)          # the line from -250 to 2,000 meets 200 at 0.2 MW
    assert out.system_lambda == pytest.approx(200.0)


def test_dispatch_limits_ramp_lets_the_ramp_range_reach_past_the_sustained_limits():
    c = case({'wind': (0, 16.0, -30.0), 'dear': (0, 100, 50.0)}, 60)
    c.resources['ramp_high'] = [16.03, 100.0]
    assert clear(c).dispatch['wind'] == pytest.approx(16.0)
    assert clear(c, Rules(dispatch_limits='ramp')).dispatch['wind'] == pytest.approx(16.03)


def test_a_reserve_offer_priced_below_zero_is_awarded_not_just_counted():
    # 'held' can carry either product on one 10 MW of room. Slow is worth more to the system, but the block it offers
    # for Fast is priced far below zero (self-provided reserves): Fast must be what it is awarded
    rules = Rules(products=(Product('Slow', 'up'), Product('Fast', 'up')), reserve_offer_floor=-1e9)
    c = case({'gen': (0, 200, 20.0), 'held': (0, 10, 0.0)}, 50)
    c.resources['dispatchable'] = [True, False]
    c.reserve_limits = pd.DataFrame([{'resource': 'held', 'product': p, 'mw': 10.0} for p in ('Slow', 'Fast')])
    c.reserve_offers = pd.DataFrame([{'resource': 'held', 'block': 'own', 'mw': 10.0, 'product': 'Slow', 'price': 0.0},
                                     {'resource': 'held', 'block': 'self', 'mw': 10.0, 'product': 'Fast', 'price': -10000.0}])
    c.reserve_demand = pd.DataFrame({'product': ['Slow', 'Slow', 'Fast', 'Fast'], 'mw': [0.0, 10.0, 0.0, 10.0], 'price': [300.0, 300.0, 100.0, 100.0]})
    a = clear(c, rules).reserve_awards.loc['held']
    assert a['Fast'] == pytest.approx(10.0) and a['Slow'] == pytest.approx(0.0)
