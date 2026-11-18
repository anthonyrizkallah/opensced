"""A market: its rulebooks and the adapter that turns its public files into input tables."""
import pandas as pd

from opensced.core.model import clear
from opensced.core.result import DayResult


class Market:
    """Get one with opensced.market('ercot').

    rules                    the market's rulebooks: .on(date), .get(name), .versions()
    inputs(...)              build one interval's Inputs from the market's published tables
    read_day(folder)         load a folder of downloaded files for one operating day
    clear(inputs)            clear one interval under the rulebook in force at inputs.time
    clear_day(day, ...)      clear every interval of a day"""

    def __init__(self, name, title, rulebooks, adapter, interval_minutes):
        self.name, self.title, self.rules, self.adapter, self.interval_minutes = name, title, rulebooks, adapter, interval_minutes
        self.__doc__ = f'{title}\n\n{adapter.__doc__ or ""}'

    def rules_for(self, when=None, rules=None):
        if rules is not None:
            return rules
        return self.rules.latest if when is None else self.rules.on(when)

    def inputs(self, *args, **kw):
        return self.adapter.inputs(*args, **kw)

    def read_day(self, folder):
        return self.adapter.read_day(folder)

    def clear(self, inputs, rules=None, check=True):
        """Clear one interval. rules: defaults to the rulebook in force at inputs.time (the latest if it has none)."""
        return clear(inputs, self.rules_for(inputs.time, rules), check=check)

    def clear_day(self, day, shift_factors=None, resource_nodes=None, rules=None, times=None, progress=True, carry=(), **options):
        """Clear every interval of a day.

        day             what read_day() returned, or any iterable of Inputs
        shift_factors   constraint x node, applied to every interval (a dict time -> table for one per interval)
        resource_nodes  resource -> node
        rules           one rulebook for every interval. Default: the rulebook in force at each interval's time
        times           clear only these intervals
        carry           () clears each interval from its own tables (a replay). ('output', 'ramp', 'soc') or any of
                        them starts each interval from where the one before ended (see opensced.clear_sequence)
        options         passed to the market's adapter, e.g. controllable_loads=False for ERCOT
        -> opensced.DayResult"""
        sf_at = lambda t: shift_factors[t] if isinstance(shift_factors, dict) else shift_factors
        if hasattr(day, 'inputs') and hasattr(day, 'times'):
            ts = list(day.times if times is None else times)
            source = [(t, lambda t=t: day.inputs(t, shift_factors=sf_at(t), resource_nodes=resource_nodes, rules=self.rules_for(t, rules), **options))
                      for t in ts]
        else:
            def given(k, i):
                i = i.copy(notes=dict(i.notes))
                if shift_factors is not None:
                    i.shift_factors = sf_at(i.time if i.time is not None else k)
                if resource_nodes is not None:
                    i.resource_nodes = resource_nodes
                return i
            source = [(i.time if i.time is not None else k, lambda k=k, i=i: given(k, i)) for k, i in enumerate(day)]
        if carry:
            from opensced.core.sequence import clear_sequence
            return clear_sequence([make for _, make in source], lambda t: self.rules_for(t, rules), carry, progress)
        out, n = {}, len(source)
        for k, (t, make) in enumerate(source):
            out[t] = clear(make(), self.rules_for(t, rules))
            if progress and (k + 1 == n or (k + 1) % 24 == 0):
                print(f'  cleared {k + 1:,} of {n:,} intervals', flush=True)
        return DayResult(out)

    def __repr__(self):
        return (f'Market {self.name!r}: {self.title}\n  intervals of {self.interval_minutes} minutes\n'
                f'  {len(self.rules)} rulebook(s), latest {self.rules.latest.name!r}')


_REGISTRY = {}
PLANNED = ('pjm', 'miso', 'spp', 'caiso', 'nyiso')


def register(market):
    _REGISTRY[market.name] = market


def list_markets():
    """Names of the markets this version can clear."""
    return sorted(_REGISTRY)


def market(name):
    """A market by name: opensced.market('ercot')."""
    key = str(name).lower()
    if key in _REGISTRY:
        return _REGISTRY[key]
    if key in PLANNED:
        raise NotImplementedError(f'{key.upper()} is planned but not built yet. Available now: {", ".join(list_markets())}')
    raise KeyError(f'no market {name!r}. Available: {", ".join(list_markets())}')
