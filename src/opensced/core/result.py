"""What a clearing returns."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Result:
    """One interval's clearing.

    system_lambda    $/MWh, the energy price every node shares before congestion
    shadow_prices    $/MWh per constraint, >= 0 (0 when the constraint does not bind)
    dispatch         MW per resource
    reserve_awards   MW, resources x products (only resources awarded something); None if reserves were not cleared
    reserve_prices   $/MW per hour per demand curve; None if reserves were not cleared
    reserve_bought   MW bought on each demand curve (the sum of the awards of the products serving it)
    violations       MW by which each constraint is exceeded (priced at its max_shadow_price)
    shortfall        MW of demand left unserved (lambda is then the shortage price); surplus is the reverse
    solved           False if the program had no solution; `status` says why
    uncapped         the system lambda and reserve prices before the rulebook's price cap was applied
    reference_prices each resource's price in step 1 of a two-step clearing; step1 is that step's Result

    node_prices()    price at every node
    summary()        a few lines to print"""
    solved: bool
    status: str
    system_lambda: float
    shadow_prices: pd.Series
    rules: object = None
    time: object = None
    dispatch: pd.Series | None = None
    reserve_awards: pd.DataFrame | None = None
    reserve_prices: pd.Series | None = None
    reserve_bought: pd.Series | None = None
    violations: pd.Series | None = None
    shortfall: float = 0.0
    surplus: float = 0.0
    cost: float = float('nan')
    uncapped: dict = field(default_factory=dict, repr=False)
    reference_prices: pd.Series | None = None
    step1: object = field(default=None, repr=False)
    _inputs: object = field(default=None, repr=False)

    def node_prices(self, shift_factors=None):
        """Price at every node: lambda - sum(shift factor x shadow price).

        shift_factors: constraint x node. Defaults to the shift factors the interval was cleared with, so the nodes
        are the columns of inputs.shift_factors. Pass a wider table to price nodes that hold no resource (hubs, load
        zones)."""
        sf = shift_factors if shift_factors is not None else getattr(self._inputs, 'shift_factors', None)
        if sf is None:
            raise ValueError('node_prices needs shift factors: none were given to the clearing. '
                             'With no network every node clears at result.system_lambda')
        mu = self.shadow_prices
        S = sf.reindex(mu.index).fillna(0.0)
        lam = self.uncapped.get('system_lambda', self.system_lambda)
        p = lam - S.to_numpy(float).T @ mu.to_numpy(float)
        cap = getattr(self.rules, 'cap', None)
        if cap is not None:                                              # a price above the cap comes down by what the
            p = np.where(p > cap, np.maximum(cap, p - max(lam - cap, 0.0)), p)   # lambda was cut, but not below the cap
        return pd.Series(p, index=S.columns, name='price')

    def resource_prices(self):
        """Price each resource is paid: the price at its node (lambda where it has no shift factors)."""
        from opensced.core.features.network import resource_shift_factors
        i = self._inputs
        names = i.resources['name'].to_numpy()
        if i.shift_factors is None or not len(self.shadow_prices):
            return pd.Series(self.system_lambda, index=pd.Index(names, name='resource'), name='price')
        sf = i.shift_factors if i.resource_nodes is None else resource_shift_factors(i.shift_factors, i.resource_nodes)
        return self.node_prices(sf).reindex(names).fillna(self.system_lambda).rename_axis('resource')

    @property
    def binding(self):
        """The constraints with a shadow price above zero."""
        return self.shadow_prices[self.shadow_prices > 1e-6].sort_values(ascending=False)

    def summary(self):
        if not self.solved:
            return f'Clearing{self._when()}: not solved ({self.status})'
        out = [f'Clearing{self._when()}' + (f'  [rules: {self.rules.name}]' if self.rules is not None else ''),
               f'  system lambda     ${self.system_lambda:,.2f} /MWh',
               f'  dispatched        {self.dispatch.sum():,.1f} MW across {int((self.dispatch.abs() > 1e-6).sum()):,} resources']
        if self.shortfall > 1e-6:
            out.append(f'  SHORTFALL         {self.shortfall:,.1f} MW unserved: lambda is the shortage price')
        if self.surplus > 1e-6:
            out.append(f'  SURPLUS           {self.surplus:,.1f} MW that could not be backed down')
        if len(self.shadow_prices):
            b = self.binding
            out.append(f'  constraints       {len(b):,} of {len(self.shadow_prices):,} binding'
                       + (f'; highest ${b.iloc[0]:,.2f} on {b.index[0]}' if len(b) else ''))
            sf = getattr(self._inputs, 'shift_factors', None)
            if sf is not None and len(b):
                p = self.node_prices()
                out.append(f'  node prices       ${p.min():,.2f} to ${p.max():,.2f} over {len(p):,} nodes')
        if self.reserve_prices is not None:
            for name, price in self.reserve_prices.items():
                out.append(f'  {name:<17} {self.reserve_bought[name]:,.0f} MW at ${price:,.2f}')
        return '\n'.join(out)

    def _when(self):
        return f' {self.time}' if self.time is not None else ''

    def __repr__(self):
        return self.summary()


@dataclass
class DayResult:
    """Many intervals cleared one after another. Each attribute is a table with one row per interval.

    system_lambda    Series: time -> $/MWh
    node_prices      DataFrame: time x node
    shadow_prices    DataFrame: time x constraint (NaN where the constraint was not in that interval)
    reserve_prices   DataFrame: time x product
    reserve_awards   DataFrame: time x product, total MW
    dispatch         DataFrame: time x resource
    results          the individual Result objects, by time"""
    results: dict

    def _series(self, f):
        return {t: f(r) for t, r in self.results.items() if r.solved}

    @property
    def system_lambda(self):
        return pd.Series({t: r.system_lambda for t, r in self.results.items()}, name='system_lambda').rename_axis('time')

    @property
    def node_prices(self):
        return pd.DataFrame(self._series(lambda r: r.node_prices())).T.rename_axis('time')

    @property
    def shadow_prices(self):
        return pd.DataFrame(self._series(lambda r: r.shadow_prices)).T.rename_axis('time')

    @property
    def reserve_prices(self):
        return pd.DataFrame(self._series(lambda r: r.reserve_prices)).T.rename_axis('time')

    @property
    def reserve_awards(self):
        return pd.DataFrame(self._series(lambda r: r.reserve_awards.sum())).T.rename_axis('time')

    @property
    def dispatch(self):
        return pd.DataFrame(self._series(lambda r: r.dispatch)).T.rename_axis('time')

    @property
    def unsolved(self):
        return [t for t, r in self.results.items() if not r.solved]

    def __len__(self):
        return len(self.results)

    def __repr__(self):
        lam = self.system_lambda
        return (f'DayResult: {len(self):,} intervals, {len(self) - len(self.unsolved):,} solved\n'
                f'  system lambda     mean ${np.nanmean(lam):,.2f}, min ${np.nanmin(lam):,.2f}, max ${np.nanmax(lam):,.2f}')
