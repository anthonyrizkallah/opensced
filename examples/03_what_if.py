"""What-if questions on a real ERCOT run: change an input, or change a rule, and compare prices.

    python examples/03_what_if.py <folder> [<folder with your shift factors>]

The folders are the same as in 02_ercot_one_run.py. This repository ships no market data.
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
kw = {}
if os.path.isdir(EXTRA):
    kw = dict(shift_factors=pd.read_csv(os.path.join(EXTRA, 'shift_factors.csv.gz'), index_col=0),
              resource_nodes=pd.read_csv(os.path.join(EXTRA, 'resource_nodes.csv')))
inputs = day.inputs(day.times[0], **kw)
base = ercot.clear(inputs)
print(f'Base case: system lambda ${base.system_lambda:,.2f}\n')

# 1. An input: what if demand were 2,000 MW higher?
more = ercot.clear(inputs.copy(demand=inputs.demand + 2000))
print(f'Demand +2,000 MW: system lambda ${more.system_lambda:,.2f}  ({more.system_lambda - base.system_lambda:+,.2f})')

# 2. An input: what if every solar resource produced 20% less?
res = inputs.resources.copy()
solar = res['type'] == 'PVGR'
res.loc[solar, ['high', 'ramp_high']] *= 0.8
less_sun = ercot.clear(inputs.copy(resources=res))
print(f'Solar -20%:       system lambda ${less_sun.system_lambda:,.2f}  ({less_sun.system_lambda - base.system_lambda:+,.2f})')

# 3. A rule: what if ECRS had to be sustained for 2 hours instead of 1?
rules = ercot.rules.on(inputs.time)
draft = rules.replace(name='draft/ecrs-2h', products={'ECRS': {'duration_hours': 2.0}})
print('\nRule change:', rules.diff(draft))
changed = ercot.clear(inputs, rules=draft)
print(pd.DataFrame({'today': base.reserve_prices, 'draft': changed.reserve_prices}).round(3))
print(f'System lambda ${changed.system_lambda:,.2f}  ({changed.system_lambda - base.system_lambda:+,.4f})')
