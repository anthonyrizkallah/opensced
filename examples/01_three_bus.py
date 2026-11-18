"""Start here: a made-up three-node grid. No data needed.

    python examples/01_three_bus.py
"""
import opensced

# 1. A case is a set of plain tables. Print it to see what is in it.
case = opensced.examples.three_bus()
print(case, '\n')
print(case.resources, '\n')

# 2. Clear it.
result = opensced.clear(case)
print(result, '\n')

# 3. The line WEST-CITY is full, so the three nodes clear at different prices.
print('Price at each node, $/MWh')
print(result.node_prices().round(2), '\n')
print('Dispatch, MW')
print(result.dispatch.round(1), '\n')

# 4. Change one input and clear again: a bigger line removes the congestion.
relaxed = opensced.clear(opensced.examples.three_bus(line_limit=500))
print('With a 500 MW line every node clears at', round(relaxed.system_lambda, 2), '\n')

# 5. Add a reserve requirement, and raise demand until headroom runs short. The system values reserve at $200 a MW,
#    so every MW of energy that takes headroom away from reserves now costs that much more: the energy price jumps.
tight = opensced.clear(opensced.examples.three_bus_with_reserves(demand=380), rules=opensced.examples.three_bus_rules())
print(tight, '\n')
print('Reserve awards, MW')
print(tight.reserve_awards)
