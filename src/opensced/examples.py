"""Small made-up cases that run with no data. Start here.

    case = opensced.examples.three_bus()
    print(opensced.clear(case))
"""
import pandas as pd

from opensced.core.rules import Product, Rules
from opensced.core.tables import Inputs


def three_bus(demand=250.0, line_limit=80.0):
    """Three nodes, three generators, one battery, one line that can bind.

        WEST   wind, 150 MW at $5            cheap, behind the line
        NORTH  gas,  200 MW at $30-$40       mid-priced
        CITY   peaker, 100 MW at $90         at the load; and a 40 MW battery

    The line WEST->CITY carries 0.6 of what WEST injects, 0.2 of what NORTH injects and nothing from CITY. With the
    default 80 MW limit the wind cannot all get out: the line binds and the three nodes clear at different prices.
    Try three_bus(line_limit=500) to see one price everywhere."""
    resources = pd.DataFrame([
        {'name': 'wind', 'low': 0.0, 'high': 150.0, 'kind': 'generator'},
        {'name': 'gas', 'low': 50.0, 'high': 200.0, 'kind': 'generator'},
        {'name': 'peaker', 'low': 0.0, 'high': 100.0, 'kind': 'generator'},
        {'name': 'battery', 'low': -40.0, 'high': 40.0, 'kind': 'storage'},
    ])
    energy_offers = pd.DataFrame([
        {'resource': 'wind', 'mw': 0.0, 'price': 5.0}, {'resource': 'wind', 'mw': 150.0, 'price': 5.0},
        {'resource': 'gas', 'mw': 50.0, 'price': 30.0}, {'resource': 'gas', 'mw': 200.0, 'price': 40.0},
        {'resource': 'peaker', 'mw': 0.0, 'price': 90.0}, {'resource': 'peaker', 'mw': 100.0, 'price': 90.0},
        {'resource': 'battery', 'mw': -40.0, 'price': 20.0}, {'resource': 'battery', 'mw': 0.0, 'price': 20.0},
        {'resource': 'battery', 'mw': 0.0, 'price': 60.0}, {'resource': 'battery', 'mw': 40.0, 'price': 60.0},
    ])
    constraints = pd.DataFrame([{'name': 'WEST-CITY', 'limit': float(line_limit), 'flow': 0.0, 'max_shadow_price': 3500.0}])
    shift_factors = pd.DataFrame([[0.6, 0.2, 0.0]], index=['WEST-CITY'], columns=['WEST', 'NORTH', 'CITY'])
    resource_nodes = {'wind': 'WEST', 'gas': 'NORTH', 'peaker': 'CITY', 'battery': 'CITY'}
    return Inputs(resources=resources, demand=float(demand), energy_offers=energy_offers, constraints=constraints,
                  shift_factors=shift_factors, resource_nodes=resource_nodes)


def three_bus_rules():
    """A rulebook for three_bus_with_reserves(): one upward reserve product."""
    return Rules(name='example/three-bus', shortage_price=5000.0, block_mw=5.0, interval_hours=5 / 60,
                 products=(Product('Reserve', 'up', duration_hours=1.0),))


def three_bus_with_reserves(demand=250.0, line_limit=80.0, reserve_mw=60.0):
    """three_bus() plus a reserve requirement, to see energy and reserves compete for the same headroom.

    The system values the first `reserve_mw` of reserve at $200 a MW. The gas unit, the peaker and the battery can
    carry it. Clear it with opensced.examples.three_bus_rules()."""
    case = three_bus(demand, line_limit)
    case.storage = pd.DataFrame([{'resource': 'battery', 'soc': 60.0, 'soc_min': 0.0, 'soc_max': 80.0}])
    case.reserve_limits = pd.DataFrame([{'resource': r, 'product': 'Reserve', 'mw': mw}
                                        for r, mw in (('gas', 50.0), ('peaker', 100.0), ('battery', 40.0))])
    case.reserve_demand = pd.DataFrame([{'product': 'Reserve', 'mw': 0.0, 'price': 200.0},
                                        {'product': 'Reserve', 'mw': float(reserve_mw), 'price': 200.0}])
    return case
