"""Compare cleared prices with published ones."""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Score:
    """How close a set of clearings came to published prices.

    table      one row per measure
    by_node    mean absolute error per node, worst first
    by_time    mean absolute node error per interval"""
    table: pd.DataFrame
    by_node: pd.Series | None = None
    by_time: pd.Series | None = None

    def summary(self):
        return self.table.to_string(float_format=lambda v: f'{v:,.2f}')

    def __repr__(self):
        return self.summary()


def _stats(err, what):
    e = np.abs(np.asarray(err, float))
    e = e[np.isfinite(e)]
    if not len(e):
        return None
    return {'compared': what, 'values': len(e), 'mean_abs_error': e.mean(), 'median_abs_error': np.median(e),
            'p95_abs_error': np.percentile(e, 95), 'max_abs_error': e.max(),
            'pct_within_1': 100 * (e < 1).mean(), 'pct_within_5': 100 * (e < 5).mean()}


def score(result, system_lambda=None, node_prices=None, reserve_prices=None):
    """Score a DayResult (or a single Result) against published prices.

    system_lambda   Series time -> $/MWh (or one number for a single Result)
    node_prices     DataFrame time x node (or a Series node -> price for a single Result)
    reserve_prices  DataFrame time x product

    Only times and nodes present on both sides are compared. Errors are in $/MWh."""
    from opensced.core.result import Result
    if isinstance(result, Result):
        t = result.time if result.time is not None else 0
        lam = pd.Series({t: result.system_lambda})
        nodes = pd.DataFrame({t: result.node_prices()}).T if node_prices is not None else None
        res = pd.DataFrame({t: result.reserve_prices}).T if reserve_prices is not None and result.reserve_prices is not None else None
        system_lambda = None if system_lambda is None else pd.Series({t: float(system_lambda)})
        node_prices = None if node_prices is None else pd.DataFrame({t: node_prices}).T
        reserve_prices = None if reserve_prices is None else pd.DataFrame({t: reserve_prices}).T
    else:
        lam, nodes = result.system_lambda, (result.node_prices if node_prices is not None else None)
        res = result.reserve_prices if reserve_prices is not None else None
    rows, by_node, by_time = [], None, None
    if system_lambda is not None:
        a, b = lam.align(pd.Series(system_lambda), join='inner')
        rows.append(_stats(a - b, 'system lambda'))
    if node_prices is not None:
        a, b = nodes.align(node_prices, join='inner')
        e = (a - b).abs()
        rows.append(_stats(e.to_numpy(), 'node prices'))
        by_node, by_time = e.mean().sort_values(ascending=False).rename('mean_abs_error'), e.mean(axis=1).rename('mean_abs_error')
        if system_lambda is not None:                                    # what ignoring congestion would cost
            pub = pd.Series(system_lambda).reindex(b.index)
            rows.append(_stats(b.sub(pub, axis=0).to_numpy(), 'node prices, if published lambda were used alone'))
    if reserve_prices is not None and res is not None:
        a, b = res.align(reserve_prices, join='inner')
        for c in a.columns:
            rows.append(_stats(a[c] - b[c], f'reserve price {c}'))
    rows = [r for r in rows if r]
    if not rows:
        raise ValueError('nothing to compare: pass system_lambda, node_prices or reserve_prices with matching times and nodes')
    return Score(pd.DataFrame(rows).set_index('compared'), by_node, by_time)
