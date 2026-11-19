# Rule versions

A **rulebook** is the set of numbers and switches a market's clearing used from one date until the next change.
Each market keeps its rulebooks in date order.

```python
import opensced
ercot = opensced.market('ercot')

ercot.rules.versions()                  # name, effective date, source
rules = ercot.rules.on('2026-08-12')    # the rulebook in force on a date
ercot.rules.get('ercot/2025-12-05')     # by name
print(rules)                            # every entry
rules.notes                             # where each number comes from
```

## What a rulebook holds

| Entry | Meaning |
|---|---|
| `shortage_price` | $/MWh when supply cannot meet demand |
| `surplus_price` | $/MWh when supply cannot be backed down far enough |
| `default_max_shadow_price` | $/MWh for a constraint published without its own cap |
| `block_mw` | Step used to cut sloped offer curves |
| `interval_hours` | Length of a dispatch interval |
| `regulation_share` | Share of a regulation award that must fit inside the interval's ramp range |
| `voll`, `offer_cap`, `offer_floor`, `shortage_adder` | The named prices. The shortage price and the price cap are computed from them unless given |
| `statuses` | What each resource status may do: be dispatched, and which reserves it may carry |
| `two_step`, `mitigated_offer_floors`, `mitigation_adder_share` | The two-step clearing and the floors and adder its mitigation uses |
| `limits` | Caps on the total awards of a group of products, in MW, as a share of a requirement, or as a requirement less a number of MW, from all or some resources |
| `price_cap` | Lambda and reserve prices are capped here after the solve |
| `shift_factor_cutoff` | Shift factors smaller than this are ignored in the dispatch |
| `products` | The reserve products: direction, hours a battery must sustain them, minutes of ramp counted, the demand curve they count towards, and any MW of that curve reserved for them |
| `features` | Which parts of the clearing are on: `network`, `reserves`, `storage` |

`print(rules)` lists every entry, and `help(opensced.Rules)` explains each. [ercot_sced_inputs.md](ercot_sced_inputs.md)
lists every input ERCOT's rules name and where it is set.

## Three uses

**Backtest under the rules of the time.** `market.clear(inputs)` and `market.clear_day(...)` pick the rulebook in
force at each interval's time.

**Run a date under another rulebook.**

```python
ercot.clear(inputs, rules=ercot.rules.get('ercot/2025-12-05'))
```

**Test a proposed rule.** A rulebook is never edited. `replace()` returns a new one.

```python
draft = rules.replace(name='draft/ecrs-2h', products={'ECRS': {'duration_hours': 2.0}})
rules.diff(draft)                       # what changed
base, what_if = ercot.clear(inputs), ercot.clear(inputs, rules=draft)
what_if.node_prices() - base.node_prices()
```

## How a rulebook gets added

1. It names its source: the rule change, the document section and the effective date.
2. Each number says in `notes` whether it was read from the rules or measured from disclosed data.
3. It comes with a replay of real dates under it, which becomes a permanent test.
4. Released rulebooks are not changed. A correction is a new entry.

## ERCOT's rulebooks

| Name | In force from | What it is |
|---|---|---|
| `ercot/2025-12-05` | December 5, 2025 | Real-time co-optimization of energy and five ancillary services. 1,365 MW of RRS reserved for primary frequency response |
| `ercot/2026-01-01` | January 1, 2026 | The RRS reserved for primary frequency response rises to 1,377 MW |

```python
ercot.rules.get('ercot/2025-12-05').diff(ercot.rules.latest)     # {'products.RRS-PFR': (..., ...)}
```

The 1,365 and 1,377 MW figures are measured, not read from a document: the RRS-PFR awarded to generation and
storage resources sits at exactly that many MW in nearly every SCED run, whatever the hour's RRS requirement, and
the value steps up between the disclosures for December 31, 2025 and January 1, 2026.

## Several products on one demand curve

ERCOT buys one quantity of RRS but three kinds of resource can supply it, each with its own capability and offer
price. The rulebook holds them as three products that count towards one demand curve:

| Product | Who provides it | `demand` | `reserved_mw` |
|---|---|---|---|
| `RRS-PFR` | Generators, batteries and controllable loads on governor response | `RRS` | 1,377 |
| `RRS-FFR` | Batteries and loads that trip at 59.85 Hz | `RRS` | |
| `RRS-UFR` | Load Resources on under-frequency relays | `RRS` | |

`reserve_limits` and `reserve_offers` name the three products. `reserve_demand` names the curve, `RRS`.
`result.reserve_awards` has a column per product, and `result.reserve_prices` one price for `RRS`. `reserved_mw`
means the other two together may fill at most the curve's total less 1,377 MW.

Dates before December 5, 2025 cleared energy only, with a scarcity price adder. That is a different set of features,
not a change of numbers, and is not built yet.
