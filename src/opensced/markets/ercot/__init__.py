"""ERCOT's real-time market (SCED under real-time co-optimization, RTC+B)."""
from opensced.core.market import Market, register
from opensced.markets.ercot import adapter, helpers, rulebooks

ERCOT = Market(name='ercot', title="ERCOT real-time market (SCED, co-optimized energy and ancillary services)",
               rulebooks=rulebooks.ALL, adapter=adapter, interval_minutes=5)
ERCOT.helpers = helpers
register(ERCOT)
