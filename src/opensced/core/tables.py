"""The input contract: the plain tables one clearing takes, whatever market they came from.

Everything the engine knows about an interval arrives through an `Inputs` object. Each table is a pandas DataFrame
with the columns listed in TABLES below. `opensced.schema()` prints this as a data dictionary, and
`Inputs.validate()` checks a set of tables against it.

Sign conventions
  MW            injection into the grid is positive. A battery charging, or a load, is negative.
  shift factor  MW of flow on a constraint per MW injected at a node.
  shadow price  >= 0. A node's price is lambda - sum(shift factor x shadow price).
"""
from dataclasses import dataclass, field, fields, replace

import numpy as np
import pandas as pd

SCHEMA_VERSION = '2'


@dataclass(frozen=True)
class Column:
    name: str
    dtype: str          # 'text', 'number', 'bool'
    unit: str
    required: bool
    default: object
    doc: str


@dataclass(frozen=True)
class Table:
    name: str
    row: str            # what one row is
    doc: str
    columns: tuple
    key: tuple = ()     # columns that must be unique together
    required: bool = False


def _c(name, dtype, unit, required, default, doc):
    return Column(name, dtype, unit, required, default, doc)


TABLES = {t.name: t for t in (
    Table('resources', 'resource', 'Everything that can inject, consume or carry reserves in this interval.', (
        _c('name', 'text', '', True, None, 'Unique id of the resource.'),
        _c('low', 'number', 'MW', True, None, 'Lowest output it can sustain (its low sustained limit). Negative for a battery that can charge.'),
        _c('high', 'number', 'MW', True, None, 'Highest output it can sustain (its high sustained limit).'),
        _c('ramp_low', 'number', 'MW', False, 'low', 'Lowest output it can reach within this interval, given where it is now and its ramp rate.'),
        _c('ramp_high', 'number', 'MW', False, 'high', 'Highest output it can reach within this interval.'),
        _c('output', 'number', 'MW', False, 0.0, 'Its output going into the interval. A resource that is not dispatchable is held here, and the constraints\' `flow` is measured with every resource at this output.'),
        _c('dispatchable', 'bool', '', False, True, 'True if the clearing may move it. False holds it at `output` (it may still carry reserves).'),
        _c('kind', 'text', '', False, 'generator', "'generator', 'storage' or 'load'. Informational, except that a 'load' carries reserves by cutting consumption."),
        _c('status', 'text', '', False, '', 'The market\'s status code for the resource. A rulebook\'s `statuses` say what each may do; adapters use it.'),
        _c('type', 'text', '', False, '', 'The market\'s resource type. Rulebook limits can select on it.'),
        _c('category', 'text', '', False, 'other', 'Fuel or technology category, for helpers that build proxy curves or mitigated offers.'),
        _c('ramp_up', 'number', 'MW/min', False, None, 'Normal ramp rate up. Used by helpers that compute ramp_high.'),
        _c('ramp_down', 'number', 'MW/min', False, None, 'Normal ramp rate down. Used by helpers that compute ramp_low.'),
        _c('output_schedule', 'number', 'MW', False, None, 'Scheduled output of a resource that submitted a schedule instead of an offer curve.'),
        _c('ruc_committed', 'bool', '', False, False, 'Committed by the reliability unit commitment process.'),
        _c('mitigated', 'bool', '', False, False, 'Its offer is capped in the second step of a two-step clearing: it failed the market\'s competitiveness test for this interval.'),
        _c('max_consumption', 'number', 'MW', False, None, 'Maximum power consumption of a load resource.'),
        _c('low_consumption', 'number', 'MW', False, None, 'Low power consumption of a load resource.'),
    ), key=('name',), required=True),
    Table('energy_offers', 'offer curve point', 'Each resource\'s energy offer curve. Price is linear between points and flat beyond the ends. A dispatchable resource with no points offers at $0.', (
        _c('resource', 'text', '', True, None, 'Resource name.'),
        _c('mw', 'number', 'MW', True, None, 'Output level. Negative MW is consumption: a battery\'s charging bid.'),
        _c('price', 'number', '$/MWh', True, None, 'Offer price at that output.'),
    )),
    Table('storage', 'battery', 'State of charge of each storage resource. Only needed when reserves are cleared.', (
        _c('resource', 'text', '', True, None, 'Resource name.'),
        _c('soc', 'number', 'MWh', True, None, 'Energy stored going into the interval.'),
        _c('soc_min', 'number', 'MWh', True, None, 'Lowest allowed state of charge.'),
        _c('soc_max', 'number', 'MWh', True, None, 'Highest allowed state of charge.'),
        _c('efficiency', 'number', 'share', False, None, 'Share of charging energy that ends up stored. Scales what charging and downward reserves would add to the state of charge. Default: rules.storage_charge_efficiency.'),
    ), key=('resource',)),
    Table('reserve_limits', 'resource and product', 'How much of each reserve product a resource is able to carry.', (
        _c('resource', 'text', '', True, None, 'Resource name.'),
        _c('product', 'text', '', True, None, 'Reserve product, as named in the rulebook.'),
        _c('mw', 'number', 'MW', True, None, 'The most it can be awarded of that product.'),
    ), key=('resource', 'product')),
    Table('reserve_offers', 'offer block and product', 'Reserve offers. A block is a quantity of MW that may serve any one of the products priced in it, so one MW is never sold twice. When this table is given, a resource carries only what it offered.', (
        _c('resource', 'text', '', True, None, 'Resource name.'),
        _c('block', 'text', '', True, None, 'Id of the block, unique within the resource.'),
        _c('mw', 'number', 'MW', True, None, 'Size of the block. Repeat it on each of the block\'s product rows.'),
        _c('product', 'text', '', True, None, 'Reserve product the block is offered for.'),
        _c('price', 'number', '$/MW per hour', True, None, 'Offer price for that product.'),
    ), key=('resource', 'block', 'product')),
    Table('reserve_demand', 'demand curve point', 'What the system pays for each MW of each reserve product: a falling curve of cumulative MW against price. Giving this table switches reserve co-optimization on.', (
        _c('product', 'text', '', True, None, 'The demand curve\'s name: a reserve product, or the name several products count towards.'),
        _c('mw', 'number', 'MW', True, None, 'Cumulative MW of the product.'),
        _c('price', 'number', '$/MW per hour', True, None, 'Value of the MW at that point. Linear between points.'),
    )),
    Table('constraints', 'network constraint', 'The transmission constraints to enforce: flow + sum(shift factor x (MW - output)) <= limit.', (
        _c('name', 'text', '', True, None, 'Unique id. Must match a row of shift_factors.'),
        _c('limit', 'number', 'MW', True, None, 'The most the element may carry.'),
        _c('flow', 'number', 'MW', True, None, 'Flow on the element with every resource at its `output`.'),
        _c('max_shadow_price', 'number', '$/MWh', True, None, 'Price at which the clearing gives up and lets the limit be exceeded.'),
        _c('kind', 'text', '', False, 'contingency', "'base', 'contingency' or 'irol'. Used by helpers that set max_shadow_price."),
        _c('kv', 'number', 'kV', False, None, 'Voltage of the limiting element. Used by helpers that set max_shadow_price.'),
        _c('competitive', 'bool', '', False, True, 'Whether the constraint is a competitive constraint, for offer mitigation.'),
    ), key=('name',)),
    Table('mitigated_offer_caps', 'curve point', 'The cost-based cap on each resource\'s offer, used in the second step of a two-step clearing for resources marked `mitigated`. Linear between points, flat beyond the ends.', (
        _c('resource', 'text', '', True, None, 'Resource name.'),
        _c('mw', 'number', 'MW', True, None, 'Output level.'),
        _c('price', 'number', '$/MWh', True, None, 'The mitigated offer cap at that output.'),
    )),
    Table('reserve_requirements', 'demand curve', 'How many MW of each reserve the system plans to hold. Shares in the rulebook (a limit of 60% of a requirement, MW reserved for one product) are taken of this. Default: the total MW of the product\'s demand curve.', (
        _c('product', 'text', '', True, None, 'The demand curve\'s name.'),
        _c('mw', 'number', 'MW', True, None, 'The requirement.'),
    ), key=('product',)),
    Table('limit_values', 'rulebook limit', 'This interval\'s own numbers for limits named in the rulebook, for values the market resets by month or by hour. A row named after a product overrides the MW reserved for that product.', (
        _c('limit', 'text', '', True, None, 'Name of the rulebook Limit, or of a product with reserved MW.'),
        _c('min_mw', 'number', 'MW', False, None, 'Floor for this interval.'),
        _c('max_mw', 'number', 'MW', False, None, 'Cap for this interval.'),
    ), key=('limit',)),
)}

OTHER = {
    'demand': 'One number, MW: what the dispatched resources must add up to in this interval.',
    'shift_factors': 'DataFrame. Index: constraint name. Columns: node name, or resource name when resource_nodes is not '
                     'given. Value: MW of flow on the constraint per MW injected there. Anything missing is taken as 0.',
    'resource_nodes': 'Where each resource injects. A Series or dict resource -> node, or a DataFrame with columns '
                      'resource, node and optionally share for a resource split over several nodes.',
    'mitigated': 'True if energy_offers already hold the mitigated curves, so a two-step rulebook clears once. Default False.',
    'time': 'Optional timestamp of the interval. A market uses it to pick the rulebook in force.',
}


@dataclass
class Inputs:
    """One interval's inputs. Only `resources` and `demand` are required.

        inputs = Inputs(resources=res, energy_offers=offers, demand=41_250)
        inputs.validate()          # raises with the table and row at fault
        print(inputs)              # a one-screen summary

    Every field is described by `opensced.schema()`."""
    resources: pd.DataFrame
    demand: float
    energy_offers: pd.DataFrame | None = None
    storage: pd.DataFrame | None = None
    reserve_limits: pd.DataFrame | None = None
    reserve_offers: pd.DataFrame | None = None
    reserve_demand: pd.DataFrame | None = None
    reserve_requirements: pd.DataFrame | None = None
    limit_values: pd.DataFrame | None = None
    mitigated_offer_caps: pd.DataFrame | None = None
    constraints: pd.DataFrame | None = None
    shift_factors: pd.DataFrame | None = None
    resource_nodes: object = None
    time: object = None
    mitigated: bool = False             # True: energy_offers already hold the mitigated (step-2) curves
    notes: dict = field(default_factory=dict)      # anything an adapter wants to pass along (published prices, ...)

    def copy(self, **changes):
        """A copy with some tables replaced: inputs.copy(demand=42_000)."""
        return replace(self, **changes)

    def validate(self, rules=None):
        """Check every table. Pass the rulebook to also catch misspelled reserve products."""
        if rules is None:
            validate(self)
        else:
            validate(self, rules.product_names or None, rules.demand_names or None)
        return self

    def __repr__(self):
        r = self.resources
        n = len(r)
        disp = int(r['dispatchable'].sum()) if 'dispatchable' in r else n
        lines = [f'Inputs{f" for {self.time}" if self.time is not None else ""}',
                 f'  demand           {float(self.demand):,.1f} MW',
                 f'  resources        {n:,} ({disp:,} dispatchable)']
        for f in fields(self):
            if f.name in ('resources', 'demand', 'time', 'notes', 'resource_nodes', 'shift_factors', 'mitigated'):
                continue
            v = getattr(self, f.name)
            lines.append(f'  {f.name:<16} ' + ('not given' if v is None else f'{len(v):,} rows'))
        s = self.shift_factors
        lines.append('  shift_factors    ' + ('not given' if s is None else f'{s.shape[0]:,} constraints x {s.shape[1]:,} columns'))
        lines.append('  resource_nodes   ' + ('not given' if self.resource_nodes is None else f'{len(self.resource_nodes):,} entries'))
        return '\n'.join(lines)


def _fail(table, msg):
    raise ValueError(f'{table}: {msg}')


def _check_table(df, spec):
    if not isinstance(df, pd.DataFrame):
        _fail(spec.name, f'expected a pandas DataFrame, got {type(df).__name__}')
    miss = [c.name for c in spec.columns if c.required and c.name not in df.columns]
    if miss:
        have = ', '.join(map(str, df.columns)) or 'none'
        _fail(spec.name, f'missing column(s) {miss}. It has: {have}. See opensced.schema("{spec.name}")')
    for c in spec.columns:
        if c.name not in df.columns:
            continue
        col = df[c.name]
        if c.dtype == 'number':
            v = pd.to_numeric(col, errors='coerce')
            bad = v.isna() if c.required else (v.isna() & col.notna())
            if bad.any():
                _fail(spec.name, f'column {c.name!r} must be a number; row {bad.idxmax()!r} has {col[bad.idxmax()]!r}')
            if c.required and not np.isfinite(v.to_numpy(float)).all():
                _fail(spec.name, f'column {c.name!r} must be finite')
        elif c.required and col.isna().any():
            _fail(spec.name, f'column {c.name!r} has an empty value at row {col.isna().idxmax()!r}')
    if spec.key and df.duplicated(list(spec.key)).any():
        d = df.loc[df.duplicated(list(spec.key)), list(spec.key)].iloc[0].tolist()
        _fail(spec.name, f'{" + ".join(spec.key)} must be unique; {d} appears more than once')


def validate(inputs, products=None, demand_products=None):
    """Raise ValueError on the first problem that would otherwise give a wrong price instead of an error.
    products: the rulebook's reserve product names, to catch a misspelled product; demand_products: the names its
    demand curves go by (the same, unless several products serve one curve)."""
    _check_table(inputs.resources, TABLES['resources'])
    r = inputs.resources
    lo, hi = pd.to_numeric(r['low']).to_numpy(float), pd.to_numeric(r['high']).to_numpy(float)
    if (lo > hi + 1e-9).any():
        _fail('resources', f'low > high for {r["name"][lo > hi + 1e-9].iloc[0]!r}')
    if 'kind' in r and not r['kind'].isin(['generator', 'storage', 'load']).all():
        _fail('resources', f"kind must be 'generator', 'storage' or 'load'; found {r['kind'][~r['kind'].isin(['generator', 'storage', 'load'])].iloc[0]!r}")
    try:
        d = float(inputs.demand)
    except (TypeError, ValueError):
        _fail('demand', f'expected one number in MW, got {type(inputs.demand).__name__}')
    if not np.isfinite(d):
        _fail('demand', 'must be a finite number of MW')
    names = set(r['name'])
    for t in ('energy_offers', 'storage', 'reserve_limits', 'reserve_offers', 'reserve_demand', 'reserve_requirements', 'limit_values', 'mitigated_offer_caps', 'constraints'):
        df = getattr(inputs, t)
        if df is None:
            continue
        _check_table(df, TABLES[t])
        if 'resource' in df.columns and len(df):
            unknown = set(df['resource']) - names
            if unknown:
                _fail(t, f'{len(unknown):,} resource(s) are not in the resources table, e.g. {sorted(map(str, unknown))[0]!r}')
        known = (demand_products or products) if t in ('reserve_demand', 'reserve_requirements') else products
        if known is not None and 'product' in df.columns and len(df):
            unknown = set(df['product']) - set(known)
            if unknown:
                _fail(t, f'unknown product {sorted(map(str, unknown))[0]!r}. This rulebook has: {", ".join(known)}')
    if inputs.storage is not None and len(inputs.storage):
        s = inputs.storage
        if (s['soc_min'] > s['soc_max']).any():
            _fail('storage', f'soc_min > soc_max for {s["resource"][s["soc_min"] > s["soc_max"]].iloc[0]!r}')
    if inputs.reserve_demand is None and (inputs.reserve_offers is not None or inputs.reserve_limits is not None):
        pass                                                   # allowed: reserves are simply not cleared
    if inputs.reserve_demand is not None and inputs.reserve_limits is None:
        _fail('reserve_limits', 'reserve_demand was given, so reserve_limits is needed: it says which resources can carry each product')
    c, s = inputs.constraints, inputs.shift_factors
    if c is not None and len(c):
        if s is None:
            _fail('shift_factors', 'constraints were given without shift_factors')
        if not isinstance(s, pd.DataFrame):
            _fail('shift_factors', 'expected a DataFrame: index = constraint name, columns = node (or resource)')
        miss = [n for n in c['name'] if n not in s.index]
        if miss:
            _fail('shift_factors', f'no row for {len(miss):,} constraint(s), e.g. {miss[0]!r}. Drop them from constraints or add their shift factors')
        cols = set(s.columns)
        where = names if inputs.resource_nodes is None else set(_node_series(inputs.resource_nodes))
        if not (cols & where):
            what = 'resource names' if inputs.resource_nodes is None else 'the nodes in resource_nodes'
            _fail('shift_factors', f'none of its {len(cols):,} columns match {what}, so no resource would affect any constraint')


def _node_series(resource_nodes):
    """the nodes named by a resource_nodes input, whatever form it took."""
    if isinstance(resource_nodes, pd.DataFrame):
        return resource_nodes['node'].astype(str)
    return pd.Series(resource_nodes).astype(str)


def schema(table=None):
    """The data dictionary as text. schema() lists every table, schema('resources') one of them."""
    out = []
    for t in TABLES.values():
        if table not in (None, t.name):
            continue
        out.append(f'{t.name}  (one row per {t.row}{"; required" if t.required else "; optional"})')
        out.append(f'    {t.doc}')
        for c in t.columns:
            need = 'required' if c.required else f'optional, default {c.default}'
            unit = f' [{c.unit}]' if c.unit else ''
            out.append(f'    {c.name:<17}{c.dtype:<7}{unit:<16} {need}. {c.doc}')
        out.append('')
    for k, v in OTHER.items():
        if table in (None, k):
            out += [k, f'    {v}', '']
    if not out:
        raise ValueError(f'no table called {table!r}. Tables: {", ".join(list(TABLES) + list(OTHER))}')
    return '\n'.join(out).rstrip()
