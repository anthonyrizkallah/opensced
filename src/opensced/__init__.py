"""opensced: an open market-clearing engine for power markets.

Offers, limits, reserve demand and network constraints in; the system price, the price at every node, dispatch and
reserve awards out.

    import opensced

    case = opensced.examples.three_bus()          # a small made-up grid, no data needed
    result = opensced.clear(case)
    print(result)
    result.node_prices()

    ercot = opensced.market('ercot')              # a real market: its rulebooks and file adapter
    day = ercot.read_day('my_data/2026-08-12')
    result = ercot.clear(day.inputs(day.times[0]))

    print(opensced.schema())                      # the input tables, column by column
"""
from opensced import examples
from opensced.core.features.network import resource_shift_factors, unmapped
from opensced.core.market import list_markets, market
from opensced.core.model import clear
from opensced.core.result import DayResult, Result
from opensced.core.rules import Limit, Product, Rulebooks, Rules
from opensced.core.score import Score, score
from opensced.core.sequence import carry_forward, clear_sequence
from opensced.core.tables import SCHEMA_VERSION, Inputs, schema, validate
from opensced import markets as _markets  # noqa: F401  (registers the built-in markets)

__version__ = '0.1.0'
__all__ = ['clear', 'clear_sequence', 'carry_forward', 'market', 'list_markets', 'Inputs', 'Rules', 'Product', 'Limit', 'Rulebooks', 'Result', 'DayResult', 'score', 'Score',
           'schema', 'validate', 'unmapped', 'resource_shift_factors', 'examples', 'SCHEMA_VERSION', '__version__']
