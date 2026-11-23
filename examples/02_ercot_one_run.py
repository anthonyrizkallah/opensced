"""One real ERCOT SCED run, rebuilt from ERCOT's public files and scored against the prices ERCOT published.

    python examples/02_ercot_one_run.py <folder> [<folder with your shift factors>]

<folder> holds one operating day of ERCOT's public reports, which you download yourself: docs/ercot.md, "Getting the
files", says where each one is and what to name it. This repository ships no market data.

With only the 60-day disclosure in the folder the run still clears, energy only. The reserve demand curves add the
reserves, and the published prices add the comparison with ERCOT.

ERCOT does not publish shift factors or which settlement point each resource sits at. If the second folder (default:
<folder>/not_published_by_ercot) holds shift_factors.csv.gz (constraint x settlement point) and resource_nodes.csv
(resource, node), they are used. Otherwise the run is cleared without the network and only the system price is compared.
"""
import os
import sys

import pandas as pd

import opensced

if len(sys.argv) < 2:
    sys.exit(__doc__)
FOLDER = sys.argv[1]
EXTRA = sys.argv[2] if len(sys.argv) > 2 else os.path.join(FOLDER, 'not_published_by_ercot')

ercot = opensced.market('ercot')
day = ercot.read_day(FOLDER)
print(day, '\n')

shift_factors = resource_nodes = None
if os.path.isdir(EXTRA):
    shift_factors = pd.read_csv(os.path.join(EXTRA, 'shift_factors.csv.gz'), index_col=0)     # constraint x settlement point
    resource_nodes = pd.read_csv(os.path.join(EXTRA, 'resource_nodes.csv'))                   # resource, node

run = day.times[len(day.times) * 17 // 24]            # a run at about 17:00
inputs = day.inputs(run, shift_factors=shift_factors, resource_nodes=resource_nodes)
print(inputs, '\n')

result = ercot.clear(inputs)            # picks the rulebook in force on the run's date
print(result, '\n')

if day.tables['reserve_demand'] is None:
    print('No dam_sced_as_demand_curves file: cleared for energy only, without reserves. ERCOT clears both together, so '
          'expect the price to be off.\n')
if day.tables['system_lambda'] is None:
    sys.exit('No sced_system_lambda file: nothing to compare the price with. docs/ercot.md, "Getting the files".')
published = day.published_lambda()[run]
print(f'System lambda: replica ${result.system_lambda:,.2f}, ERCOT ${published:,.2f}\n')

if shift_factors is not None and day.tables['lmp'] is not None and day.tables['reserve_prices'] is not None:
    report = opensced.score(result, system_lambda=published, node_prices=day.published_node_prices().loc[run],
                            reserve_prices=day.published_reserve_prices().loc[run])
    print(report, '\n')
    print('Largest misses by settlement point, $/MWh')
    print(report.by_node.head(5).round(2))
elif shift_factors is None:
    print('No shift factors found: cleared without the network. Add your own to see node prices.')
