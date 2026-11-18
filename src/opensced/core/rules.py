"""Rulebooks: the numbers and switches a market's clearing used from one date until the next change.

    rules = ercot.rules.on('2026-08-12')        # the rulebook in force that day
    rules.shortage_price
    draft = rules.replace(name='draft/longer-ecrs', products={'ECRS': {'duration_hours': 2.0}})

A rulebook is never edited once released. A correction, or a proposed rule, is a new rulebook made with replace().
"""
from dataclasses import dataclass, field, replace

import pandas as pd


@dataclass(frozen=True)
class Product:
    """One reserve product.
    direction        'up' (held as room above the output) or 'down' (room below it)
    duration_hours   how long a battery must be able to sustain the award from its stored energy
    regulation       True if the award must also fit inside what the resource can ramp within the interval
    ramp_minutes     minutes of ramp that count towards a resource's limit for the product (used by adapters that are
                     given ramp rates instead of MW limits)
    demand           the demand curve its awards count towards. Default: its own name. Several products can serve
                     one demand curve: ERCOT's RRS is met by three kinds of response, each a product of its own
    reserved_mw      MW of that demand curve only this product may fill. The other products serving the same curve
                     share what is left"""
    name: str
    direction: str
    duration_hours: float = 0.0
    regulation: bool = False
    ramp_minutes: float | None = None
    demand: str | None = None
    reserved_mw: float = 0.0
    capability_columns: tuple = ()     # for adapters: the published columns holding a resource's capability for it
    offer_price_columns: tuple = ()    # for adapters: the published offer price columns (the cheapest is used)
    offer_kinds: tuple = ()            # for adapters: the kinds of offer that can carry it

    @property
    def serves(self):
        return self.demand or self.name

    def __post_init__(self):
        if self.direction not in ('up', 'down'):
            raise ValueError(f"product {self.name!r}: direction must be 'up' or 'down'")


@dataclass(frozen=True)
class Limit:
    """A cap on the total awards of some reserve products, optionally from some resources only.

    products    the reserve products whose awards are added up
    max_mw      the cap in MW, and / or
    max_share   the cap as a share of a requirement (`of`: the demand curve's name)
    min_mw, min_share   a floor instead of, or as well as, a cap. A floor that cannot be met makes the interval unsolved
    where       count only resources whose column matches, e.g. {'type': 'NCLR'}. Default: every resource
    source      the rule it comes from"""
    name: str
    products: tuple
    max_mw: float | None = None
    max_share: float | None = None
    min_mw: float | None = None
    min_share: float | None = None
    of: str | None = None
    where: tuple = ()
    source: str = ''

    def __post_init__(self):
        if all(v is None for v in (self.max_mw, self.max_share, self.min_mw, self.min_share)):
            raise ValueError(f'limit {self.name!r}: give max_mw or max_share (or min_mw, min_share)')
        if (self.max_share is not None or self.min_share is not None) and self.of is None:
            raise ValueError(f'limit {self.name!r}: max_share needs `of`, the demand curve it is a share of')


@dataclass(frozen=True)
class Status:
    """What a resource in a given status may do.
    dispatchable   the clearing may move it
    reserves       which reserves it may carry: {kind of offer: tuple of product names, or None for every product}.
                   An empty dict: none
    proxy_reserves False: it is awarded reserves only on offers it submitted, never on the market operator's proxy
                   offer for unoffered capacity"""
    name: str
    dispatchable: bool = False
    reserves: dict = field(default_factory=dict, hash=False)
    proxy_reserves: bool = True


FEATURES = ('network', 'reserves', 'storage')


@dataclass(frozen=True)
class Rules:
    """A rulebook. Every field has a default, so Rules() is a plain energy-and-network clearing.

    name, effective, source   what it is, the date it took effect, and the rule change it came from
    shortage_price            $/MWh when supply cannot meet demand
    surplus_price             $/MWh when supply cannot be backed down far enough (negative)
    default_max_shadow_price  $/MWh for a constraint that comes without its own
    block_mw                  offer curves are cut into steps of at most this many MW
    block_refine              times the interval is solved again with every curve cut finer around where its resource
                              landed. Each pass cuts block_refine_factor times finer. 0: steps of block_mw only
    offer_curves              'steps': curves cut into steps (block_mw, block_refine). 'exact': each sloped stretch is
                              costed as the area under it, a quadratic program (needs the highspy package)
    interval_hours            length of one dispatch interval
    regulation_share          share of a regulation award that must fit within the interval's ramp range
    products                  the reserve products, in order
    limits                    caps on the total awards of groups of reserve products (see Limit)
    price_cap                 $/MWh. The system lambda and reserve prices are capped here after the solve, and node
                              prices above it are pulled down by what the lambda was cut. None: no cap
    shift_factor_cutoff       shift factors smaller than this are ignored in the dispatch
    voll, offer_cap, offer_floor, shortage_adder
                              the value of lost load, the system-wide offer cap and the offer floor. With
                              shortage_price=None the shortage price is voll + offer_cap + shortage_adder, and with
                              price_cap=None prices are capped at voll (when voll is given)
    no_offer_price            $/MWh for a dispatchable resource with no offer curve
    curve_extension           'flat': a curve's end prices hold beyond its ends. 'floor': the range below its lowest
                              point is priced at offer_floor
    zero_split                cut every curve at 0 MW, so charging and discharging are separate blocks
    reserve_offer_floor       reserve offer prices below this are raised to it
    no_reserve_offer_price    $/MW per hour for reserves when no reserve_offers table is given
    self_arranged_price       $/MW per hour at which adapters offer self-arranged reserves
    demand_curve_pricing      'mean': a stretch between two demand curve points is worth their average. 'left': the
                              price at its start
    storage_signed_energy     a battery's output counts with its sign against its stored energy: charging during the
                              interval adds exactly that energy to what its reserve awards may draw on
    storage_charge_efficiency share of charging energy stored, for a battery whose `efficiency` is not given
    storage_charge_offset     an older reading, off by default: a charging battery may count every MW it could
                              stop charging as reserve that needs no stored energy
    storage_passes            how many times an interval may be solved again to stop batteries charging and
                              discharging at once (see core/features/storage.py). 0 turns the check off
    tolerance_mw              MW differences smaller than this are treated as zero
    dispatch_minutes          minutes of ramp in the dispatch range (used by the helpers that compute ramp_low/high)
    proxy_*, irr_proxy_price, ruc_*, clr_no_bid_price, shadow_price_caps
                              numbers the market's helpers use to build proxy offers, proxy curves and constraint caps
    statuses                  what each resource status may do (see Status)
    two_step                  clear twice: once on the competitive constraints for reference prices, then on every
                              constraint with mitigated offers (see opensced.core.features.mitigation). Skipped
                              when inputs.mitigated says the offers are already the step-2 curves
    mitigated_offer_floors    $/MWh by resource category; 'other' is the fallback
    mitigation_adder_share    share of a resource's mitigated offer cap at its low limit added to its reference price
    generic_heat_rates        MMBtu/MWh used by helpers that build a generic mitigated offer cap from a fuel price
    solver, solver_options    passed to scipy.optimize.linprog
    features                  which parts of the clearing are on: 'network', 'reserves', 'storage'
    notes                     per-entry provenance: which numbers were read from the rules and which were measured"""
    name: str = 'custom'
    effective: str | None = None
    source: str = ''
    shortage_price: float | None = 5000.0
    surplus_price: float = -250.0
    voll: float | None = None
    offer_cap: float | None = None
    offer_floor: float = -250.0
    shortage_adder: float = 0.0
    default_max_shadow_price: float = 5251.0
    block_mw: float = 5.0
    block_refine: int = 0
    offer_curves: str = 'steps'
    block_refine_factor: float = 10.0
    interval_hours: float = 5 / 60
    regulation_share: float = 1.0
    products: tuple = ()
    limits: tuple = ()
    price_cap: float | None = None
    shift_factor_cutoff: float = 0.0
    no_offer_price: float = 0.0
    curve_extension: str = 'flat'
    zero_split: bool = True
    reserve_offer_floor: float = 0.0
    no_reserve_offer_price: float = 0.0
    self_arranged_price: float = 0.0
    demand_curve_pricing: str = 'mean'
    storage_signed_energy: bool = True
    storage_charge_efficiency: float = 1.0
    storage_charge_offset: bool = False
    storage_passes: int = 4
    tolerance_mw: float = 1e-6
    dispatch_minutes: float = 5.0
    proxy_price_step: float = 0.01
    proxy_mw_step: float = 1.0
    irr_proxy_price: float = 1500.0
    ruc_offer_floor: float = 250.0
    ruc_reserve_offer_price: float = 250.0
    proxy_reserve_cap: float = 2000.0
    proxy_reserve_plan_share: float = 0.95
    clr_no_bid_price: float | None = None
    shadow_price_caps: dict = field(default_factory=dict, hash=False)
    statuses: tuple = ()
    two_step: bool = False
    mitigated_offer_floors: dict = field(default_factory=dict, hash=False)
    mitigation_adder_share: float = 0.0
    generic_heat_rates: dict = field(default_factory=dict, hash=False)
    solver: str = 'highs'
    solver_options: dict = field(default_factory=dict, hash=False)
    features: tuple = FEATURES
    notes: dict = field(default_factory=dict, compare=False)

    def __post_init__(self):
        bad = set(self.features) - set(FEATURES)
        if bad:
            raise ValueError(f'unknown feature(s) {sorted(bad)}. Choose from {FEATURES}')
        if self.block_mw <= 0:
            raise ValueError('block_mw must be positive')

    @property
    def shortage(self):
        """the shortage price in force: shortage_price, or voll + offer_cap + shortage_adder when it is None."""
        if self.shortage_price is not None:
            return self.shortage_price
        if self.voll is None or self.offer_cap is None:
            raise ValueError(f'rulebook {self.name!r}: give shortage_price, or voll and offer_cap to compute it')
        return self.voll + self.offer_cap + self.shortage_adder

    @property
    def cap(self):
        """the cap applied to prices after the solve: price_cap, or voll, or None."""
        return self.price_cap if self.price_cap is not None else self.voll

    def status(self, name):
        for s in self.statuses:
            if s.name == name:
                return s
        return None

    @property
    def product_names(self):
        return tuple(p.name for p in self.products)

    @property
    def demand_names(self):
        """the demand curves, in order: one per product unless several products serve the same curve."""
        return tuple(dict.fromkeys(p.serves for p in self.products))

    def serving(self, demand):
        """names of the products whose awards count towards a demand curve."""
        return tuple(p.name for p in self.products if p.serves == demand)

    def product(self, name):
        for p in self.products:
            if p.name == name:
                return p
        raise KeyError(f'no product {name!r} in rulebook {self.name!r}. It has: {", ".join(self.product_names)}')

    def has(self, feature):
        return feature in self.features

    def replace(self, products=None, **changes):
        """A new rulebook with some entries changed. products: {product name: {field: value}} changes those products
        and keeps the rest, e.g. rules.replace(name='draft/x', products={'ECRS': {'duration_hours': 2.0}})."""
        if products is not None:
            unknown = set(products) - set(self.product_names)
            if unknown:
                raise KeyError(f'no product {sorted(unknown)[0]!r} in rulebook {self.name!r}')
            changes['products'] = tuple(replace(p, **products[p.name]) if p.name in products else p for p in self.products)
        if 'name' not in changes:
            changes['name'] = f'{self.name} (modified)'
        return replace(self, **changes)

    def diff(self, other):
        """What differs from another rulebook: {entry: (this, other)}."""
        out = {}
        from dataclasses import fields as _fields
        for k in (f.name for f in _fields(self) if f.name not in ('name', 'effective', 'source', 'notes', 'products')):
            if getattr(self, k) != getattr(other, k):
                out[k] = (getattr(self, k), getattr(other, k))
        mine, theirs = {p.name: p for p in self.products}, {p.name: p for p in other.products}
        for n in dict.fromkeys(list(mine) + list(theirs)):
            if mine.get(n) != theirs.get(n):
                out[f'products.{n}'] = (mine.get(n), theirs.get(n))
        return out

    def __repr__(self):
        lines = [f'Rules {self.name!r}' + (f', in force from {self.effective}' if self.effective else ''),
                 *([f'  source                    {self.source}'] if self.source else []),
                 f'  shortage_price            ${self.shortage:,.2f}' + ('' if self.shortage_price is not None else f' (voll {self.voll:,.0f} + offer_cap {self.offer_cap:,.0f} + {self.shortage_adder:,.2f})'),
                 f'  surplus_price             ${self.surplus_price:,.2f}',
                 f'  default_max_shadow_price  ${self.default_max_shadow_price:,.2f}',
                 f'  block_mw                  {self.block_mw:g} MW',
                 f'  interval_hours            {self.interval_hours:.4g} ({self.interval_hours * 60:g} minutes)',
                 f'  regulation_share          {self.regulation_share:.4g}',
                 f'  price_cap                 ' + ('none' if self.cap is None else f'${self.cap:,.2f}'),
                 f'  shift_factor_cutoff       {self.shift_factor_cutoff:g}',
                 f'  features                  {", ".join(self.features)}']
        for p in self.products:
            lines.append(f'  product {p.name:<9} {p.direction:<4} duration {p.duration_hours:g} h'
                         + (', regulation' if p.regulation else '') + (f', {p.ramp_minutes:g} min of ramp' if p.ramp_minutes else '')
                         + (f', counts towards {p.demand}' if p.demand else '') + (f', {p.reserved_mw:,.0f} MW reserved for it' if p.reserved_mw else ''))
        for l in self.limits:
            hi = ' and '.join(([f'{l.max_mw:,.0f} MW'] if l.max_mw is not None else []) + ([f'{l.max_share:.0%} of {l.of}'] if l.max_share is not None else []))
            lo = ' and '.join(([f'{l.min_mw:,.0f} MW'] if l.min_mw is not None else []) + ([f'{l.min_share:.0%} of {l.of}'] if l.min_share is not None else []))
            lines.append(f'  limit {l.name}: {" + ".join(l.products)}' + (f' at most {hi}' if hi else '') + (f' at least {lo}' if lo else '') + (f' (where {dict(l.where)})' if l.where else ''))
        return '\n'.join(lines)


class Rulebooks:
    """A market's rulebooks in date order.

        books.on('2026-08-12')     the rulebook in force that day
        books.get('ercot/2025-12-05')
        books.versions()           a table of every rulebook"""

    def __init__(self, books):
        self._books = sorted(books, key=lambda r: pd.Timestamp(r.effective))
        if len({r.name for r in self._books}) != len(self._books):
            raise ValueError('rulebook names must be unique')

    def on(self, date):
        t = pd.Timestamp(date)
        if t.tzinfo is not None:
            t = t.tz_localize(None)
        live = [r for r in self._books if pd.Timestamp(r.effective) <= t]
        if not live:
            first = self._books[0]
            raise LookupError(f'no rulebook for {t.date()}: the earliest is {first.name!r}, in force from {first.effective}. '
                              f'Dates before it cleared under rules this package does not model yet')
        return live[-1]

    def get(self, name):
        for r in self._books:
            if r.name == name:
                return r
        raise KeyError(f'no rulebook {name!r}. Available: {", ".join(r.name for r in self._books)}')

    @property
    def latest(self):
        return self._books[-1]

    def versions(self):
        return pd.DataFrame([{'name': r.name, 'effective': r.effective, 'source': r.source} for r in self._books])

    def __iter__(self):
        return iter(self._books)

    def __len__(self):
        return len(self._books)

    def __repr__(self):
        return 'Rulebooks:\n' + '\n'.join(f'  {r.effective}  {r.name}  {r.source}' for r in self._books)
