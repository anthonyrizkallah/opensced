"""One real ERCOT SCED run: August 12, 2026 at 17:00, rebuilt from ERCOT's public files and scored against the
prices ERCOT published.

    python examples/02_ercot_one_run.py

The folder examples/ercot/2026-08-12_1700 holds the public files for that run. ERCOT does not publish shift factors
or which settlement point each resource sits at; if the folder `not_published_by_ercot` is present they are read
from there, otherwise the run is cleared without the network and only the system price is compared.
"""
import os

import pandas as pd

import opensced

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(HERE, 'ercot', '2026-08-12_1700')
EXTRA = os.path.join(FOLDER, 'not_published_by_ercot')

ercot = opensced.market('ercot')
day = ercot.read_day(FOLDER)
print(day, '\n')

shift_factors = resource_nodes = None
if os.path.isdir(EXTRA):
    shift_factors = pd.read_csv(os.path.join(EXTRA, 'shift_factors.csv.gz'), index_col=0)     # constraint x settlement point
    resource_nodes = pd.read_csv(os.path.join(EXTRA, 'resource_nodes.csv'))                   # resource, node

run = day.times[0]
inputs = day.inputs(run, shift_factors=shift_factors, resource_nodes=resource_nodes)
print(inputs, '\n')

result = ercot.clear(inputs)            # picks the rulebook in force on August 12, 2026
print(result, '\n')

published = day.published_lambda()[run]
print(f'System lambda: replica ${result.system_lambda:,.2f}, ERCOT ${published:,.2f}\n')

if shift_factors is not None:
    report = opensced.score(result, system_lambda=published, node_prices=day.published_node_prices().loc[run],
                            reserve_prices=day.published_reserve_prices().loc[run])
    print(report, '\n')
    print('Largest misses by settlement point, $/MWh')
    print(report.by_node.head(5).round(2))
else:
    print('No shift factors found: cleared without the network. Add your own to see node prices.')
