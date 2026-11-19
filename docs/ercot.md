# ERCOT

```python
import opensced
ercot = opensced.market('ercot')
day = ercot.read_day('my_data/2026-08-12')
print(day)                 # which files were found, how many runs
day.times                  # the SCED runs
```

## The files

`read_day(folder)` looks for one file per report, named after the report's endpoint on ERCOT's public API. Each may
be `.parquet`, `.csv` or `.csv.gz`, holds one operating day, and keeps ERCOT's own column names. Both of ERCOT's
naming styles work: the website's files ("Base Point") and the API's ("basePoint").

| File name | Report | ERCOT id | Used for |
|---|---|---|---|
| `60_sced_gen_res_data` | 60-Day SCED Disclosure, generation resources | NP3-965-ER | Required |
| `60d_sced_esr_data` | 60-Day SCED Disclosure, storage resources | NP3-965-ER | Required |
| `60d_sced_resource_as_offers` | 60-Day SCED Disclosure, reserve offers | NP3-965-ER | Reserve offers |
| `60_load_res_data_in_sced` | 60-Day SCED Disclosure, Load Resources | NP3-965-ER | Reserves from loads |
| `dam_sced_as_demand_curves` | Ancillary Service Demand Curves | NP4-212-CD | Reserve demand |
| `dam_as_plan` | DAM Ancillary Service Plan | NP4-33-CD | The hourly reserve requirements. Needed for the limit on Non-Spin from non-controllable loads |
| `shdw_prices_bnd_trns_const` | SCED Shadow Prices and Binding Transmission Constraints | NP6-86-CD | Constraints |
| `lmp_node_zone_hub` | LMPs by Resource Node, Load Zone and Hub | NP6-788-CD | Scoring |
| `sced_system_lambda` | SCED System Lambda | NP6-322-CD | Scoring |
| `rt_clear_price_cap_sced` | Real-Time Clearing Prices for Capacity by SCED Interval | NP6-332-CD | Scoring |

The 60-day disclosure is published about 60 days after the operating day, so a replay is possible for dates at least
that old. The demand curves are published per hour; every other report is per SCED run, about every five minutes.

If you already hold the tables as DataFrames, skip the folder:

```python
inputs = ercot.inputs(sced, when='2026-08-12 17:00:27', reserve_offers=offers, load_resources=loads,
                      reserve_demand=curves, constraints=binding, shift_factors=sf, resource_nodes=nodes)
```

## Your two inputs

**`shift_factors`**: a DataFrame, one row per constraint, one column per settlement point. The row labels must match
the ids this adapter gives constraints:

```text
<constraintName>|<fromStation>|<toStation>|<contingencyName>
```

`ercot.adapter.constraint_name(table)` builds them from the published report. A constraint with no row in your table
is left out of the clearing; `inputs.notes['constraints_without_shift_factors']` lists which.

**`resource_nodes`**: resource name to settlement point, as a dict, a Series, or a DataFrame with columns `resource`
and `node` (and `share` for a resource split over several points). `opensced.unmapped(inputs)` lists resources with
no node.

## How a SCED run becomes the input tables

| Table | From |
|---|---|
| `resources.dispatchable` | Telemetered status is one SCED can move: ON, ONRUC, ONOPTOUT, ONEMR, ONOS (on an Output Schedule) and OFFQS (off-line quick start). Everything else is held at its base point |
| `resources.low`, `high` | LSL and HSL |
| `resources.ramp_low`, `ramp_high` | LDL and HDL |
| `resources.output` | Base point |
| `energy_offers` | The SCED2 curve, the one SCED dispatched on after mitigation. No curve: ERCOT's proxy offer |
| `storage` | SOC, minSOC, maxSOC |
| `reserve_limits` | Disclosed capability x the rulebook's minutes of ramp, per product. RRS is three products: `RRS-PFR`, `RRS-FFR`, `RRS-UFR` |
| `reserve_offers` | On-line resources through ONRES and REGDN blocks, off-line ones through OFFNS. Block 6 of each row is ERCOT's proxy offer for unoffered capacity. An off-line unit may carry Non-Spin only, a quick-start unit ECRS and Non-Spin, a synchronous condenser RRS and ECRS |
| Load Resources, non-controllable | Carry reserves only, up to the consumption they can drop. Their self-arranged MW are offered at $0 |
| Load Resources, controllable | Dispatched as negative output between -HDL and -LDL on their bid-to-buy curve, and carry reserves. Held at their base point when offline or without a bid curve |
| `reserve_demand` | The hour's demand curves, from the latest posting made before the run |
| `demand` | The sum of the run's base points, less what controllable loads consume (they are resources, not demand) |
| `constraints` | Every constraint ERCOT reported for the run: reported flow, limit and maximum shadow price |

Extra columns `type` (ERCOT's resource type, such as `PVGR` or `WIND`; `NCLR` and `CLR` for Load Resources) and
`status` ride along on `resources` for filtering.

## A day as one chain

```python
out = ercot.clear_day(day, shift_factors=sf, resource_nodes=nodes, carry=('output', 'ramp', 'soc'))
```

Without `carry`, every run starts from ERCOT's own telemetry for that run: a replay. With it, a run starts from the
engine's dispatch in the run before. Dispatch ranges are rebuilt from the disclosure's ramp rates (`ramp_up`,
`ramp_down`) by ERCOT's formula in 6.5.7.2, and state of charge is moved by what each battery was dispatched.
Everything else (offers, limits, demand, constraints) is still read per run. This is the mode a forecast needs,
because tomorrow's telemetry does not exist yet.

## Offer mitigation: one step or two

ERCOT clears in two steps (Protocols 6.5.7.3(14)). Step 1 enforces only the competitive constraints and gives each
resource a reference price. Step 2 enforces everything, after raising every offer to a floor and capping the offers
of resources that failed the competitiveness test.

```python
inputs = day.inputs(run)                    # ERCOT's step-2 curves, already mitigated: the clearing runs once
inputs = day.inputs(run, curve='SCED1',     # the curves before mitigation: the clearing runs both steps
                    mitigated=names, mitigated_offer_caps=caps, categories={'SOME_COGEN_CC1': 'qf'})
result = ercot.clear(inputs)
result.reference_prices                     # step-1 price at each resource
result.step1                                # the step-1 clearing
```

| Input | Where it comes from |
|---|---|
| Curves before mitigation | The SCED1 columns of the disclosure |
| Which constraints are competitive | The `CCTStatus` column of the constraints report |
| Floor by category | The rulebook. The category comes from the resource type; a Qualifying Facility is not marked in the files, so pass `categories` for those |
| Which resources are capped | `mitigated`. ERCOT's competitiveness test is not run here |
| Their caps | `mitigated_offer_caps`. `ercot.helpers.generic_offer_caps(resources, fuel_index_price, rules)` gives ERCOT's generic cap, 10.5 or 14.5 times the gas index price. Cost-based caps above that are confidential |

Checked on all 288 runs of August 12, 2026 against ERCOT's own step-2 curves, with each unit's category and the set
of capped units read from ERCOT's result: floors match within a cent on 99.2% of the 16,101 curve segments ERCOT
raised, and 99.99% of the 701,306 segments ERCOT left alone are left alone. Caps match within a cent on 21% of the
2,990 capped segments and within $1 on 44%: those at the generic cap match exactly, those at the reference price are
within about $0.20, and those set by confidential costs cannot be reproduced. Clearing on the engine's own mitigated
curves gives a system lambda error of $0.16 and a node price error of $0.26, against $0.11 and $0.15 on ERCOT's.

## What is simplified

- **Demand** is what SCED dispatched, not ERCOT's own demand target, which is not published.
- **Controllable loads have no node.** Unless your `resource_nodes` names them, they do not affect any constraint.
  `ercot.inputs(..., controllable_loads=False)` treats them as fixed demand instead.
- **The constraint list is ERCOT's.** The engine is told which constraints were active. It does not find them from a
  full network model.
- **Before February 3, 2026** ERCOT wrote unpriced reserve offer cells as 0, so a real $0 offer and a blank look the
  same. About one zero cell in eleven is a real offer. The adapter reads a 0 as "not offered" and then puts the real
  ones back from two more files, if you give them:
  - `2day_agg_sced_as_offers` (NP3-906-EX) is the exact sum of every resource's offers, so its MW at $0 is the total to
    restore for each product.
  - `reference_sced_resource_as_offers` is the reserve offer disclosure of any day on or after February 3, 2026. It
    says which resources offer which product at $0. With it the restored MW go to the right resources for about
    four fifths of the total (measured on later days with their blanks hidden). Without it only the total is right.

  `inputs.notes['zero_offers_restored']` shows, per product, how much was placed on which evidence.
- **December 2025** files have two more gaps. The reserve offer disclosure has an empty `offerType` column; the
  adapter reads the type from the proxy block instead (no row wrong on three later days that have the column). Early
  downloads of the generation file lack `ASCapRRSPFR` and `ASCapRRSFFR`; the adapter stops with an error, and ERCOT's
  API has them.
- **Demand curves must be ERCOT's, every point.** A curve cut down to a hundred points keeps its total MW but moves
  prices along it by tens of dollars. A file that lacks a product for the run's hour is an error.
