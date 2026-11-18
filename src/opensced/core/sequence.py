"""Clearing a run of intervals one after another, each starting from where the last one ended.

Most of an interval's inputs come from outside: demand, offers, limits, the constraints. A few do not. They are the
result of the interval before:

    output   where each dispatchable resource starts: its dispatch in the interval before
    ramp     how far it can move from there: [output - ramp_down x minutes, output + ramp_up x minutes], inside its
             sustained limits (needs the resources columns ramp_up and ramp_down, MW per minute)
    soc      a battery's state of charge: what it held, less what it discharged, plus what it charged

`carry` says which of these the sequence works out itself; the rest are read from each interval's tables as given.
A resource that is not dispatchable keeps the output it was given, because that is a schedule and not a result.
A carried output is held inside the new interval's sustained limits: a wind farm whose limit fell cannot start above it.

Carrying output assumes every resource did exactly what it was told. Real fleets drift from their instructions, so a
chained run departs from a market's own record even with perfect inputs; that gap is the cost of the assumption.

When a resource's starting output changes, each constraint's `flow` is moved with it, so the tables still describe
the same network: flow is the flow with every resource at its `output`.
"""
import numpy as np
import pandas as pd

from opensced.core.features.network import resource_shift_factors
from opensced.core.model import clear
from opensced.core.result import DayResult
from opensced.core.rules import Rules

CARRY = ('output', 'ramp', 'soc')


def carry_forward(inputs, previous, rules, carry=CARRY, hours=None):
    """`inputs` for the next interval, updated with what `previous` (the Result of the interval before) left behind.

    hours: time between the two intervals. Default: rules.interval_hours. -> a new Inputs; `inputs` is not changed."""
    bad = set(carry) - set(CARRY)
    if bad:
        raise ValueError(f'carry: unknown {sorted(bad)}. Choose from {CARRY}')
    if previous is None or not previous.solved or not carry:
        return inputs
    hours = rules.interval_hours if hours is None else hours
    res = inputs.resources.copy().reset_index(drop=True)
    last = previous.dispatch
    was = previous._inputs.resources.set_index('name')
    was_disp = was['dispatchable'] if 'dispatchable' in was else pd.Series(True, index=was.index)
    now_disp = res['dispatchable'].fillna(False).to_numpy(bool) if 'dispatchable' in res else np.ones(len(res), bool)
    moved = now_disp & res['name'].isin(last.index).to_numpy() & res['name'].map(was_disp).fillna(False).to_numpy(bool)
    old = pd.to_numeric(res['output'], errors='coerce').fillna(0.0).to_numpy(float) if 'output' in res else np.zeros(len(res))
    low_, high_ = pd.to_numeric(res['low'], errors='coerce').to_numpy(float), pd.to_numeric(res['high'], errors='coerce').to_numpy(float)
    new = np.where(moved, np.clip(res['name'].map(last).to_numpy(float), low_, np.maximum(high_, low_)), old)   # inside this interval's limits
    out = inputs.copy(resources=res, notes=dict(inputs.notes))
    if 'output' in carry or 'ramp' in carry:
        c = inputs.constraints
        if c is not None and len(c) and inputs.shift_factors is not None:          # keep flow = flow at the new outputs
            sf = inputs.shift_factors if inputs.resource_nodes is None else resource_shift_factors(inputs.shift_factors, inputs.resource_nodes)
            M = sf.reindex(index=c['name'].to_numpy(), columns=res['name'].to_numpy()).fillna(0.0).to_numpy(float)
            out.constraints = c.assign(flow=pd.to_numeric(c['flow']).to_numpy(float) + M @ (new - old))
        res['output'] = new
    if 'ramp' in carry and 'ramp_up' in res and 'ramp_down' in res:
        up, down = (pd.to_numeric(res[k], errors='coerce').to_numpy(float) for k in ('ramp_up', 'ramp_down'))
        low, high = pd.to_numeric(res['low']).to_numpy(float), pd.to_numeric(res['high']).to_numpy(float)
        m = rules.dispatch_minutes
        ok = moved & np.isfinite(up) & np.isfinite(down)
        hi, lo = np.minimum(new + up * m, high), np.maximum(new - down * m, low)
        hi = np.maximum(hi, lo)
        res['ramp_high'] = np.where(ok, hi, pd.to_numeric(res['ramp_high'], errors='coerce') if 'ramp_high' in res else high)
        res['ramp_low'] = np.where(ok, lo, pd.to_numeric(res['ramp_low'], errors='coerce') if 'ramp_low' in res else low)
    if 'soc' in carry and inputs.storage is not None and previous._inputs.storage is not None and len(inputs.storage):
        st = inputs.storage.copy()
        held = previous._inputs.storage.set_index('resource')['soc']
        eff = previous._inputs.storage.set_index('resource')['efficiency'] if 'efficiency' in previous._inputs.storage else pd.Series(1.0, index=held.index)
        d = st['resource'].map(last).to_numpy(float)
        before = st['resource'].map(held).to_numpy(float)
        e = st['resource'].map(eff).fillna(1.0).to_numpy(float)
        after = before - np.where(d >= 0, d, d * e) * hours                # charging stores efficiency x energy
        ok = np.isfinite(after) & st['resource'].map(was_disp).fillna(False).to_numpy(bool)
        after = np.clip(after, st['soc_min'].to_numpy(float), st['soc_max'].to_numpy(float))
        st['soc'] = np.where(ok, after, st['soc'].to_numpy(float))
        out.storage = st
    out.notes['carried'] = tuple(carry)
    return out


def clear_sequence(intervals, rules=None, carry=CARRY, progress=False):
    """Clear intervals in order, carrying state from each into the next.

        intervals   Inputs in time order (or callables returning Inputs, to build each one only when it is needed)
        rules       one rulebook, or a function time -> rulebook
        carry       which of 'output', 'ramp', 'soc' to carry forward. () clears every interval as given
    The time between intervals is taken from their `time` when both have one. An interval that does not solve breaks
    the chain: the next one starts from its own tables. -> opensced.DayResult"""
    out, previous = {}, None
    items = list(intervals)
    for k, item in enumerate(items):
        x = item() if callable(item) else item
        r = rules(x.time) if callable(rules) else (rules or Rules())
        hours = None
        if previous is not None and x.time is not None and previous.time is not None:
            hours = (pd.Timestamp(x.time) - pd.Timestamp(previous.time)).total_seconds() / 3600
        res = clear(carry_forward(x, previous, r, carry, hours), r)
        out[x.time if x.time is not None else k] = res
        previous = res if res.solved else None
        if progress and (k + 1 == len(items) or (k + 1) % 24 == 0):
            print(f'  cleared {k + 1:,} of {len(items):,} intervals', flush=True)
    return DayResult(out)
