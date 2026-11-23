# ERCOT SCED inputs: the full inventory, and where each one is set in opensced

## Status after the first round of changes

The inventory below is as first written. Since then the package was changed so that these are user inputs.

**Now settable**

| What | Where |
|---|---|
| Value of lost load, offer cap, offer floor, shortage adder | `Rules.voll`, `offer_cap`, `offer_floor`, `shortage_adder`. The shortage price and the price cap are computed from them unless given |
| What each resource status may do | `Rules.statuses` (was fixed in the adapter) |
| Where each product sits in ERCOT's files | `Product.capability_columns`, `offer_price_columns`, `offer_kinds`. A new product needs no code change |
| Proxy curve numbers | `Rules.proxy_price_step`, `proxy_mw_step`, `irr_proxy_price`, `proxy_reserve_cap`, `proxy_reserve_plan_share` |
| Price of a resource with no curve; curve behaviour below its lowest point; the cut at 0 MW | `Rules.no_offer_price`, `curve_extension`, `zero_split` |
| Reserve offer floor; price with no offers; self-arranged price | `Rules.reserve_offer_floor`, `no_reserve_offer_price`, `self_arranged_price` |
| How demand curve segments are priced | `Rules.demand_curve_pricing` |
| Whether charging less counts towards an up award | `Rules.storage_charge_offset` |
| Tolerance, solver and its options | `Rules.tolerance_mw`, `solver`, `solver_options` |
| Constraint caps by kind and voltage | `Rules.shadow_price_caps` with `ercot.helpers.max_shadow_prices` |
| RUC reserve offer price | `Rules.ruc_reserve_offer_price`, used by `ercot.helpers.proxy_reserve_offers` |
| Reserve requirement separate from the demand curve | `Inputs.reserve_requirements` |
| Floors as well as caps on groups of products | `Limit.min_mw`, `Limit.min_share` |
| A limit's value for one interval (the monthly PFR minimum) | `Inputs.limit_values` |
| The demand target | `ercot.inputs(..., demand=...)`, `ercot.helpers.demand` |
| Which loads are controllable; how load headroom is measured | `ercot.inputs(..., controllable_loads=[...], load_room=...)` |
| Storage types, zero-price reading, curve length, missing shift factors | `ercot.inputs(..., storage_types, zero_price_is_blank, curve_points, missing_shift_factors)` |
| Dispatch limits from ramp rates | `ercot.helpers.dispatch_limits`, `Rules.dispatch_minutes`, columns `ramp_up`, `ramp_down` |
| Proxy energy curves (wind and solar, output schedules, short curves) | `ercot.helpers.proxy_energy_curves`, columns `output_schedule`, `category` |
| Proxy reserve offers | `ercot.helpers.proxy_reserve_offers`, columns `ruc_committed`, `max_consumption` |
| Two-step clearing and offer mitigation | `Rules.two_step`, `mitigated_offer_floors`, `mitigation_adder_share`; `Inputs.mitigated`, `Inputs.mitigated_offer_caps`; columns `resources.mitigated`, `resources.category`, `constraints.competitive`; `ercot.inputs(..., curve='SCED1', mitigated=..., categories=...)` |
| Generic mitigated offer cap | `ercot.helpers.generic_offer_caps`, `Rules.generic_heat_rates` |

**Declared but not used by the clearing yet** (the input exists; nothing reads it)

`Rules.clr_no_bid_price`, `Rules.ruc_offer_floor`, `resources.low_consumption`.

**Still without an input**

| What | Why it is not there yet |
|---|---|
| The competitiveness test (which resources are capped in a run) | Needs ownership by decision-making entity. The resulting set is an input |
| The pricing run: deployments, relaxed limits, price adders | `opensced.markets.ercot.pricing.pricing_run()`; ERS restoration and the DC Tie adjustment are not modelled |
| A load may not hold Non-Spin with RRS or ECRS | Needs a yes/no choice per load |
| Building the demand curves from the requirement (4.4.12) | The fitted curve parameters are posted outside the documents read, and two formulas were lost in conversion |
| Caps for irresolvable and stability-limit constraints | Formulas lost in conversion; the published cap per constraint is an input already |
| Cost-based mitigated offer cap from verifiable heat rates and fuel adders | Confidential. The generic cap is computed; a known cost-based cap can be passed in |
| Proxy curves for storage, controllable loads and RUC-committed units | Paragraphs (4)(d), (6), (8), (9) not coded |
| Battery charge and discharge power limits; decision-making entity; pending-rule inputs | Not coded |
| The formula for the demand target | Not in the documents |


Written November 16, 2026. Read-only audit; no code was changed.

The goal: every input and parameter that ERCOT's real-time clearing (SCED under Real-Time Co-optimization, RTC+B)
uses, taken from ERCOT's rule documents, and for each one the place a user of `opensced` sets it.

## How to read this

**Documents** (`L` is the line number in a plain-text copy of each document):

| Short | File | Version |
|---|---|---|
| S2 | `protocols_02-110626.txt` | Section 2, definitions, November 6, 2026 |
| S3 | `protocols_03-110626.txt` | Section 3, November 6, 2026 |
| S4 | `protocols_04-080126.txt` | Section 4, August 1, 2026 |
| S6 | `protocols_06-110626.txt` | Section 6, November 6, 2026 |
| S8 | `protocols_08-110626.txt` | Section 8, November 6, 2026 |
| AttP | `protocols_22P-120525.txt` | Section 22 Attachment P, December 5, 2025 |
| ASM | `as_methodology_2026/ERCOT Methodologies for Determining Minimum AS Requirements 010126.txt` | effective January 1, 2026 |

**Package places.** `Inputs.<table>.<column>` is a column of an input table (`core/tables.py`). `Rules.<field>`,
`Product.<field>` and `Limit` are rulebook entries (`core/rules.py`), replaced with `rules.replace(...)`.
`adapter.X` is a module-level constant in `markets/ercot/adapter.py`.

**Gap values**

- NONE: the user can set it.
- DERIVED: the user sets the result (for example HDL), but the package has no helper that computes it from the
  underlying inputs. The underlying inputs are listed.
- HARD-CODED: fixed in code. The file and constant are named.
- ABSENT: the model has no place for it.
- NOT NEEDED FOR CLEARING: used for monitoring, deployment, validation or settlement only.

**Other marks.** "pending" = grey-box text, a rule change not yet in effect. "inferred" = my judgement, not stated in
the text. A value in quotes is copied exactly from the rule.

Two views of the package matter and the table keeps them apart:
the **core** (`Inputs` + `Rules`), where a user can set almost any result by hand, and the **ERCOT adapter**, which
builds `Inputs` from ERCOT's files and fixes several rules in constants.

**Counts** (224 rows): NONE 70, ABSENT 50, DERIVED 49, HARD-CODED 28, NOT NEEDED FOR CLEARING 27. Four rows repeat an
item already counted in another group; they say so ("counted under ...").

---

## 1. The inventory

### 1.1 Resource telemetry and limits

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Resource identity (name; combined-cycle configuration is its own Resource) | S6 6.5.5.2(2)(n) L679; (11) L728 | per resource | none | QSE telemetry / registration | `Inputs.resources.name` | NONE |
| Net real power (POWERTELEM), generation | S6 6.5.5.2(2)(a) L664 | per resource, per run | none | QSE telemetry | `Inputs.resources.output` (the ERCOT adapter fills it with the Base Point, not the telemetered output) | NONE |
| Net real power, ESR (output or consumption) | S6 6.5.5.2(7)(a) L705 | per resource, per run | none | QSE telemetry | `Inputs.resources.output` | NONE |
| High Sustained Limit (HSL), generation | S6 6.5.5.2(2)(i) L672; S2 L579-580 | per resource, per run | none | QSE telemetry | `Inputs.resources.high` | NONE |
| Low Sustained Limit (LSL), generation | S6 6.5.5.2(2)(m) L678; S2 L717-718 | per resource, per run | none | QSE telemetry | `Inputs.resources.low` | NONE |
| HSL and LSL, ESR (either may be negative or positive) | S6 6.5.5.2(7)(i) L713, (l) L716; S2 L577-578, L715-716 | per resource, per run | none | QSE telemetry | `Inputs.resources.high`, `.low` | NONE |
| HSL of an IRR = current net output capability | S6 6.5.5.2(3) L686 | per resource, per run | none | QSE telemetry | `Inputs.resources.high` | NONE |
| HSLTELEM for an IRR that offers reserves = the five-minute intra-hour forecast | S6 6.5.7.2(2) table L921 | per resource, per run | none | ERCOT calculation | folded into `Inputs.resources.ramp_high` | DERIVED: IRR 5-minute forecast, a flag that the IRR (or its group) telemeters reserve capability |
| 5-minute blended Normal Ramp Rate up (NORMRAMPUP) | S6 6.5.5.2(2)(r) L683, (7)(o) L719, (6)(n) L703; S2 L892-893 | per resource, per run | none | QSE telemetry | folded into `Inputs.resources.ramp_high` (`ramp_low` for a CLR) | DERIVED: ramp rate up in MW/min, net real power, HSL, status |
| 5-minute blended Normal Ramp Rate down (NORMRAMPDN) | same | per resource, per run | none | QSE telemetry | folded into `Inputs.resources.ramp_low` (`ramp_high` for a CLR) | DERIVED: ramp rate down in MW/min, net real power, LSL, status |
| Minutes of ramp in HDL and LDL | S6 6.5.7.2(2)-(7) L907-988; 6.5.7.1.12(1)(c) L838 | system constant | "(NORMRAMPUP * 5)" | Protocol constant | none (the user supplies HDL and LDL) | DERIVED: the constant 5 sits in the helper that does not exist |
| High Dispatch Limit (HDL), generation | S6 6.5.7.2(2) L905-909 | per resource, per run | "HDL = Min (POWERTELEM + (NORMRAMPUP * 5), HSLTELEM)"; SHUTDOWN: "HDL = POWERTELEM – (NORMRAMPDN * 5)" | ERCOT calculation | `Inputs.resources.ramp_high` | DERIVED: POWERTELEM, NORMRAMPUP, NORMRAMPDN, HSLTELEM, status |
| Low Dispatch Limit (LDL), generation | S6 6.5.7.2(3) L923-927 | per resource, per run | "LDL = Max (POWERTELEM - (NORMRAMPDN * 5), LSLTELEM)"; STARTUP: "LDL = POWERTELEM + (NORMRAMPUP * 5)" | ERCOT calculation | `Inputs.resources.ramp_low` | DERIVED: same inputs |
| HDL and LDL, ESR | S6 6.5.7.2(4)-(5) L940-964 | per resource, per run | ONHOLD: "HDL = 0", "LDL = 0"; ONTEST: "Max (Min (POWERTELEM, HSLTELEM), LSLTELEM)"; else the generation formulas | ERCOT calculation | `Inputs.resources.ramp_high`, `.ramp_low` | DERIVED: same inputs |
| HDL and LDL, Controllable Load Resource | S6 6.5.7.2(6)-(7) L975-988 | per resource, per run | "HDL = Min (POWERTELEM + (NORMRAMPDN * 5), HSLTELEM)"; "LDL = Max (POWERTELEM - (NORMRAMPUP * 5), LSLTELEM)" | ERCOT calculation | `Inputs.resources.ramp_low`, `.ramp_high` with the sign flipped (consumption is negative MW) | DERIVED: same inputs, plus the sign flip |
| Operator override of HDL or LDL | S6 6.5.7.1.10(3)(g) L818, (6) L823; 6.5.7.1.13(8)-(10) L898-900 | per resource, per run | none | operator | `Inputs.resources.ramp_high`, `.ramp_low` | NONE |
| Emergency Ramp Rate | S6 6.5.7.1.12(1)(b) L837; S2 L387-388 | per resource, per run | none | QSE telemetry | folded into `Inputs.reserve_limits.mw` for ECRS | DERIVED: emergency ramp rate in MW/min (see 1.5, ECRS limit) |
| Telemetered Resource Status | S6 6.5.7.3(1) L1001; S3 3.9.1(5)(b) L3377-3416 | per resource, per run | status codes, see 1.5 | QSE telemetry | core: `Inputs.resources.dispatchable` and the rows of `Inputs.reserve_limits`. Adapter: fixed mapping | HARD-CODED: `adapter.DISPATCHABLE`, `adapter.HELD_WITH_RESERVES`, `adapter.ELIGIBLE` |
| Resource kind (Generation Resource, ESR, Load Resource) | S6 6.5.7.2 L905, L940, L975 | per resource | none | registration | `Inputs.resources.kind`. Adapter: fixed list of ESR types | HARD-CODED in the adapter only: `adapter.STORAGE_TYPES = ('ESR', 'PWRSTR')` |
| RRS physical capability, by sub-type (MW) | S6 6.5.5.2(2)(p) L681, (6)(l) L701, (7)(m) L717 | per resource, per run | none | QSE telemetry | `Inputs.reserve_limits.mw` for `RRS-PFR`, `RRS-FFR`, `RRS-UFR` | NONE |
| Blended ramp rate per reserve product other than RRS (MW/min) | S6 6.5.5.2(2)(q) L682, (6)(m) L702, (7)(n) L718 | per resource, per run | none | QSE telemetry | folded into `Inputs.reserve_limits.mw`; the adapter multiplies by `Product.ramp_minutes` | DERIVED at the core: ramp rate per product in MW/min times `Product.ramp_minutes` (only the ERCOT adapter does the multiplication) |
| Frequency Responsive Capacity (FRC) high and low limits, current FRC | S6 6.5.5.2(2)(o) L680; S2 L534-535 | per resource, per run | none | QSE telemetry | none | NOT NEEDED FOR CLEARING: feeds the capacity monitor and PRC (S6 6.5.7.5(1)(p) L1487); the SCED input is the telemetered RRS capability (inferred) |
| Non-Frequency Responsive Capacity (NFRC) inside HSL | S6 6.5.5.2(2)(j) L675 | per resource, per run | none | QSE telemetry | none | NOT NEEDED FOR CLEARING: capacity monitor (inferred) |
| Power augmentation capacity that is not On-Line (inside HSL) | S6 6.5.5.2(2)(t) L685; 6.5.7.5(1)(f)(iii) L1436 | per resource, per run | none | QSE telemetry | folded into `Inputs.reserve_limits.mw` (Non-Spin) and `Inputs.resources.ramp_high` | DERIVED: off-line augmentation MW (how SCED limits energy on it is not written; inferred) |
| High and Low Emergency Limits (HEL, LEL) | S6 6.5.5.2(2)(k)-(l) L676-677, (7)(j)-(k) L714-715 | per resource | none | QSE telemetry | none | NOT NEEDED FOR CLEARING: used "under Section 6.5.9.2, Failure of the SCED Process" |
| Gross power, reactive power, auxiliary load, breaker and switch status, AVR/PSS | S6 6.5.5.2(2)(b)-(h) L665-671 | per resource | none | QSE telemetry | none | NOT NEEDED FOR CLEARING: feeds the State Estimator and network model; reaches SCED as constraint flows |
| Raise Block Status, Lower Block Status | S6 6.5.5.2(9) L721-726 | per resource | none | QSE telemetry | none | NOT NEEDED FOR CLEARING: stops regulation deployment by LFC, not the award (L724) |
| Number of generators online in an Aggregate Generation Resource | S6 6.5.5.2(5) L688 | per resource | none | QSE telemetry | none | NOT NEEDED FOR CLEARING |
| Telemetry accuracy and staleness | S6 6.5.5.2(10) L727; 6.5.7.1.13(1)(a) L848 | system constant | "within three percent"; "stale for more than 20 seconds" | Protocol constant | none | NOT NEEDED FOR CLEARING |
| Current Operating Plan (COP) status, limits, capabilities | S3 3.9.1(5) L3375-3429; S6 6.5.7.3(1) L1001 | per resource, per hour | none | QSE | none | NOT NEEDED FOR CLEARING: SCED uses the telemetered status "instead of the Resource Status provided by the COP" |

### 1.2 Energy offers and bids

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Energy Offer Curve (generation) | S4 4.4.9.3.1(1)(c) L727; S6 6.5.7.3(1) L1001 | per resource, per run (latest valid) | "no more than ten price/quantity pairs" | QSE offer | `Inputs.energy_offers` (resource, mw, price) | NONE |
| Energy Bid/Offer Curve (ESR; negative MW is charging) | S4 4.4.9.7.1(1)(c) L970 | per resource, per run | "no more than ten price/quantity pairs" | QSE offer | `Inputs.energy_offers` with negative MW | NONE |
| RTM Energy Bid (CLR); pending NPRR1188 renames it Energy Bid Curve | S6 6.4.3.1.1(1)(c) L510; pending S4 4.4.9.8 L980-995 | per resource, per run | "no more than ten price/quantity pairs"; price "not to exceed the effective Value of Lost Load (VOLL)" (L501) | QSE bid | `Inputs.energy_offers` with negative MW | NONE |
| Energy offer floor | S4 4.4.9.3.1(2) L733; 4.4.9.7.1(2) L973 | system constant | "-$250.00 per MWh" | Protocol constant | core: none. Adapter: first price of the proxy | HARD-CODED: `adapter.PROXY[0] = -250.0` |
| Real-Time System-Wide Offer Cap (RTSWCAP), as the offer cap and as a proxy-curve price | S4 4.4.9.3.1(2) L733; 4.4.11 table L1257-1259 | system constant (changes by Board approval) | "HCAP – RTM (RTSWCAP)" "2,000" $/MWh | Protocol constant | only inside the sum `Rules.shortage_price` | ABSENT |
| Resource-specific bid/offer floors and caps entered by ERCOT (ESR, CLR) | S4 4.4.9.7.1(2) L973; S6 6.4.3.1.1(2) L513 | per resource | none | operator | the user edits `Inputs.energy_offers` | NONE |
| How a sloped curve is cut for the solver | not in the rules | modelling choice | none | package | `Rules.block_mw` | NONE |
| Price beyond the ends of a submitted curve (core behaviour) | not in the rules as coded; ERCOT's rule is the proxy extension below | fixed behaviour | none | package | flat at the end prices | HARD-CODED: `core/features/balance.py` `blocks()` (`np.interp`) |
| Price of a dispatchable resource with no curve (core behaviour) | not in the rules as coded | fixed behaviour | none | package | $0 across its range | HARD-CODED: `core/features/balance.py` `blocks()` default `(0.0, 0.0)` |
| Output Schedule MW | S6 6.4.2(3) L477; 6.4.2.2(1)(c) L488; 6.4.2.1(2)(a)-(b) L481-482; 4.4.9.3(7) S4 L722 | per resource, per 5 minutes | QF and IRR: "equal to the telemetered output"; no schedule: "set the Output Schedule equal to the then current telemetered output" | QSE schedule / ERCOT | none | ABSENT (today the user must hand-build the proxy curve in `Inputs.energy_offers`) |
| Proxy curve, non-IRR on an Output Schedule | S6 6.5.7.3(4)(a) L1010-1022 | per resource, per run | HSL "RTSWCAP"; "Output Schedule MW plus 1 MW" "RTSWCAP minus $0.01"; Output Schedule MW "-$249.99"; LSL "-$250.00" | ERCOT calculation | `Inputs.energy_offers` (the adapter reads ERCOT's finished SCED2 curve) | DERIVED: Output Schedule MW, HSL, LSL, RTSWCAP, offer floor, the 1 MW and $0.01 steps |
| Proxy extension of a partial curve, non-IRR and IRR | S6 6.5.7.3(4)(b) L1023-1034; (4)(c)(ii) L1045-1055 | per resource, per run | above: "Price associated with highest MW"; below: "1 MW below lowest MW" "-$249.99", LSL "-$250.00" | ERCOT calculation | `Inputs.energy_offers` | DERIVED: submitted curve, HSL, LSL, offer floor (the core's flat extension gives a different lower side) |
| Proxy curve, IRR with no curve | S6 6.5.7.3(4)(c)(i) L1036-1044 | per resource, per run | HSL "$1,500"; "HSL minus 1 MW" "-$249.99"; LSL "-$250.00" | ERCOT calculation | adapter fallback when a file has no curve, applied to every resource type | HARD-CODED: `adapter.PROXY = (-250.0, -249.99, 1500.0)` and the `hi - 1` step in `adapter._sced_tables` |
| RUC-committed flag | S3 3.9.1(5)(b)(i)(A) L3379 (ONRUC); S6 6.5.7.3(4)(d) L1056 | per resource, per hour | none | ERCOT (RUC) / QSE telemetry | the adapter keeps a `status` column; nothing uses it | ABSENT |
| RUC energy offer floor | S6 6.5.7.3(4)(d)(i)-(ii) L1057-1072; combined-cycle cases (iii)-(iv) L1082-1105 | system constant | no curve: "$250" from "Zero" to HSL; with a curve: "Greater of $250 or" the submitted price | Protocol constant | `Inputs.energy_offers` | ABSENT as a parameter (DERIVED as a curve: RUC flag, HSL, submitted curve, $250) |
| RUC curve during an Advance Action Notice (pending NPRR930) and for switchable units (pending NPRR1019; current rule S6 6.4.4.1 L528) | S6 L1073-1080, L1107-1147, L528 | system constant | "$4,500 or the effective Value of Lost Load (VOLL), whichever is less" | Protocol constant | none | ABSENT (pending, except 6.4.4.1) |
| RMR unit's administratively set curve | S6 6.4.4(2) L524 | per resource | "must price all energy at the effective VOLL" | ERCOT | `Inputs.energy_offers` | DERIVED: RMR flag, VOLL |
| Proxy curve, ESR with a partial curve | S6 6.5.7.3(6)(a) L1198-1236 | per resource, per run | above the top point: "RTSWCAP" for MW at or above zero; below the bottom point: "-$250.00" for MW at or below zero; the end price on the other side of zero | ERCOT calculation | `Inputs.energy_offers` | DERIVED: submitted curve, HSL, LSL, RTSWCAP, offer floor |
| Proxy curve, ESR with no curve or on an Output Schedule | S6 6.5.7.3(6)(b)-(c) L1237-1238; 6.4.4(4) L526; S4 4.4.9.7(7) L965 | per resource, per run | "-$250/MWh for the MW portion of the curve less than zero MW" and "RTSWCAP for the MW portion of the curve greater than zero MW"; with a schedule the split is at the schedule MW | ERCOT calculation | adapter fallback uses the IRR proxy for ESRs too | HARD-CODED: `adapter.PROXY` ($1,500 top, not RTSWCAP) |
| Proxy bid, CLR with a partial bid | S6 6.5.7.3(8) L1240-1248; pending NPRR1188 L1250-1258 | per resource, per run | "LPC to MPC minus maximum MW of RTM Energy Bid" at the "Price associated with the lowest MW"; MPC at the "Right-most point (lowest price)" | ERCOT calculation | `Inputs.energy_offers` | DERIVED: bid curve, LPC, MPC |
| Proxy bid, CLR with no bid | S6 6.5.7.3(9) L1259-1263; 6.4.3.1(3) L503 | per resource, per run | "LPC to MPC" at "Effective Value of Lost Load (VOLL)" | ERCOT calculation | the adapter holds such a CLR at its Base Point | HARD-CODED: `adapter._load_tables`, `disp = c & online & has_bid & ...` |
| Bid curves must be non-increasing | S6 6.5.7.3(9) L1265 | rule | none | ERCOT validation | not checked | NOT NEEDED FOR CLEARING: an input validation |
| Fuel percentages on the curve (FIP %, FOP %) | S4 4.4.9.3.1(1)(g) L731 | per resource, per hour | none | QSE offer | none | ABSENT (an input to the Mitigated Offer Cap, see 1.11) |
| Energy offers are inclusive with reserve offers in real time | S4 4.4.9.3.1(1)(f) L730; 4.4.9.7.1(3) L974 | rule | "always considered to be inclusive" | Protocol constant | fixed behaviour of the headroom rows | NONE (matches; not a switch) |
| Proxy flag on postings | S6 6.5.7.3(11) L1271, (13) L1275 | per resource | none | ERCOT | none | NOT NEEDED FOR CLEARING: a posting mark |

### 1.3 Ancillary service offers

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Resource-specific reserve offer: MW, product, price | S4 4.4.7.2.1(1) L445-455; S6 6.4.9.1(2) L558 | per resource, per run (latest) | none | QSE offer | `Inputs.reserve_offers` (resource, block, mw, product, price) | NONE |
| Linked offers: one capacity offered for several products | S4 4.4.7.2.1(1)(c) L448; S6 6.5.7.3(5)(a) L1150 | per offer | none | QSE offer / ERCOT | `Inputs.reserve_offers.block` | NONE |
| Reserve offer price floor | S4 4.4.7.2.1(3) L457 | system constant | "No Ancillary Service Offer price may be less than $0 per MW" | Protocol constant | prices below 0 are raised to 0 | HARD-CODED: `core/features/reserves.py` `offer_variables()`, `max(price, 0.0)` |
| FFR offer floor in prioritised hours (pending NPRR1128) | S4 4.4.7.2.1(3) L459 | system constant | "may not be less than -$0.01 per MW" | Protocol constant | blocked by the floor above | ABSENT (pending) |
| Reserve offer price cap | S4 4.4.7.2.1(3) L457; 4.4.7.2(5)(a) L429 | system constant | not above "the RTSWCAP" after 1430 Day-Ahead | Protocol constant | not checked | NOT NEEDED FOR CLEARING: ERCOT cancels such offers before SCED |
| Minimum offer size | S4 4.4.7.2.1(4) L460 | system constant | "one-tenth (0.1) MW" | Protocol constant | not checked | NOT NEEDED FOR CLEARING: an input validation |
| Fixed and variable block indicators | S4 4.4.7.2.1(1)(g) L453-454 | per offer | "will be ignored for awarding of Ancillary Services in the Real-Time Market" | QSE offer | awards are continuous | NOT NEEDED FOR CLEARING |
| Offer kind: On-Line, Off-Line, Reg-Down (disclosure types ONRES, OFFNS, REGDN) | S6 6.5.7.3(5)(d) L1191; S4 4.4.7.2(8) L434 | per offer | none | QSE offer | core: the products listed on a block. Adapter: fixed map | HARD-CODED: `adapter.OFFER_TYPES`, `adapter.OFFER_PRICE` |
| Unpriced cells written as 0 in files before February 3, 2026 | not a rule: a file-format fact | per file | none | ERCOT file | adapter | HARD-CODED: `adapter.ZERO_FILL_END = 2026-02-03` |
| Proxy reserve offer: MW | S6 6.5.7.3(5)(a) L1150 | per resource, per run | generation: "equal to the Resource's telemetered HSL"; ESR: "the difference between the Resource's telemetered HSL and LSL"; load: "telemetered Maximum Power Consumption (MPC)" | ERCOT calculation | `Inputs.reserve_offers` (the adapter reads ERCOT's sixth offer block) | DERIVED: HSL, LSL, MPC, the products the resource is qualified for |
| Proxy reserve offer: price | S6 6.5.7.3(5)(b) L1151-1166; DRRS pending NPRR1309 L1167-1170 | per resource, per product, per run | Reg-Up and RRS: maximum of the floor and the resource's highest Reg-Up or RRS, ECRS and Non-Spin prices; ECRS: floor, ECRS, Non-Spin; Non-Spin and Reg-Down: floor and own highest | ERCOT calculation | `Inputs.reserve_offers.price` | DERIVED: the floor below, the resource's submitted offers |
| Proxy reserve offer price floor | S6 6.5.7.3(5)(c) L1171-1186; DRRS pending L1187-1190 | per product, per run | "the lesser of" "$2,000 per MW per hour" or the ASDC point at "95% of the Ancillary Service Plan", "minus $0.01 per MW per hour" | ERCOT calculation | none | DERIVED: `Inputs.reserve_demand`, the Ancillary Service Plan MW, the constants $2,000, 95%, $0.01 |
| Separate floors for On-Line and Off-Line, and per sub-type | S6 6.5.7.3(5)(d) L1191 | per product and kind | "shall be designed to allow"; no values | ERCOT | none | DERIVED: same helper |
| RUC-committed resource: reserve offer price | S6 6.5.7.3(5)(e) L1192-1196 | per resource, per run | no offer: "$250 per MWh for the full operating range"; with an offer: maximum of own highest price or "$250 per MWh" | ERCOT calculation | `Inputs.reserve_offers` | DERIVED: RUC flag, HSL, submitted offers, $250 |
| Reserves without an offers table (core behaviour) | not in the rules | fixed behaviour | none | package | every resource with a limit carries the product at $0 | HARD-CODED: `core/features/reserves.py` (award variables cost 0 when `reserve_offers` is None) |
| A load that is not a CLR: no Non-Spin together with RRS or ECRS in real time | S4 4.4.7.2.1(6) L462 | per resource, per run | "will not be awarded Non-Spin and RRS or Non-Spin and ECRS on the same Load Resource simultaneously in Real-Time" | Protocol constant | none (needs a yes/no variable) | ABSENT |

### 1.4 Ancillary service requirements and demand curves

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Ancillary Service Demand Curve (ASDC) per product: Reg-Up, Reg-Down, RRS, ECRS, Non-Spin | S4 4.4.12(1) L1282; S6 6.5.7.3(1) L1001; update S6 6.4.9.1.2(1) L569 | per product, per hour (re-posted when the plan changes) | none | ERCOT posting | `Inputs.reserve_demand` (product, mw, price) | NONE |
| Curve between posted points | S4 4.4.12(8) L1462 | rule | "a linear approximation" | Protocol constant | each segment priced at the mean of its end points | HARD-CODED: `core/features/reserves.py` `segments()` (inferred to match) |
| Ancillary Service Plan MW per product per hour | S2 L81-82; S4 4.4.12(7)(a) L1346-1354; S6 6.5.7.3(5)(c) L1174 | per product, per hour | none | ERCOT posting | none. The total width of the demand curve stands in for it in `Limit.max_share` and `Product.reserved_mw` | HARD-CODED: `core/features/reserves.py` `demand_variables()`, `S['curve_mw']` (curve width used as the requirement; inferred not always equal, since Non-Spin takes the surplus segments, S4 L1421) |
| VOLL used to build the ASDCs | S4 4.4.11(1)(a) L1237; 4.4.12(2) L1285 | system value, switchable | "set to the HCAP for DAM"; "HCAP – DAM (DASWCAP)" "5,000" | Protocol constant | inside the posted curve; also `Rules.price_cap` | NONE |
| Reg-Down curve shape | S4 4.4.12(4) L1287 | per hour | "a constant value equal to VOLL for the full range of the Ancillary Service Plan for Reg-Down" | ERCOT calculation | `Inputs.reserve_demand` | DERIVED: VOLL, Reg-Down plan MW |
| Aggregate curve (AORDC) fit: data window, reserve cut-off, μ, σ, μ*, σ* | S4 4.4.12(6) L1291-1321 | system constants, fitted | "June 1, 2014 through August 31, 2025"; "less than 10,000 MW"; "1 MW increments"; "reserve level >= 3,000 MW and price >$0.01/MWh"; formula garbled at L1310 | ERCOT calculation | `Inputs.reserve_demand` | DERIVED: μ*, σ* (posted elsewhere), VOLL |
| Minimum Contingency Level (MCL) | S4 4.4.12(7)(a) L1343-1345 | system constant | "This value is set at 3,000 MW" | Protocol constant | inside the posted curve | DERIVED (curve builder) |
| RUPCT | S4 L1386-1388 | system constant | "90" % | Protocol constant | inside the posted curve | DERIVED (curve builder) |
| RRSPCTMAX | S4 L1389-1391 | system constant | "90" % | Protocol constant | inside the posted curve | DERIVED (curve builder) |
| ECRSPCTMAX | S4 L1392-1394 | system constant | "30" % | Protocol constant | inside the posted curve | DERIVED (curve builder) |
| ECRSMWMIN | S4 L1395-1397 | system constant | "40" MW | Protocol constant | inside the posted curve | DERIVED (curve builder) |
| NSMWMIN | S4 L1398-1400 | system constant | "10" MW | Protocol constant | inside the posted curve | DERIVED (curve builder) |
| Maximum demand prices up to the MCL | S4 L1405-1416 | system constants | Reg-Up "VOLL + 4,052"; RRS "VOLL + 2,051"; ECRS "VOLL + 50"; Non-Spin "VOLL" | Protocol constant | inside the posted curve | DERIVED (curve builder) |
| Minimum prices beyond the MCL | S4 4.4.12(7)(b) L1426-1431; pending NPRR1309 L1444-1458 | system constants | Reg-Up "250"; RRS "100"; pending: ECRS "15", Non-Spin "5", DRRS "0.01" | Protocol constant | inside the posted curve | DERIVED (curve builder) |
| ASDC floor over the plan quantity | S4 4.4.12(9) L1463; pending L1465 | system constant | "$15 per MW per hour"; pending DRRS "$10 per MW per hour" | Protocol constant | inside the posted curve | DERIVED (curve builder) |
| Minimum RRS from Primary Frequency Response | ASM L26; S3 3.16(2)(c) L5278; 3.16(4) L5282 | per month (ERCOT may raise it) | ASM: "shall not be less than 1,377 MWs"; Protocols: "shall not be less than 1,150 MW" | ERCOT posting | `Product.reserved_mw` on `RRS-PFR` (coded as a cap on the other two sub-types) | NONE (set per rulebook; a monthly value needs a new rulebook via `rules.replace`) |
| Maximum RRS from Fast Frequency Response | ASM L26; S3 3.16(2)(b) L5275 | system constant (annual) | "limited to 450 MW" | ERCOT methodology | `Limit('FFR', max_mw=450)` in `Rules.limits` | NONE |
| Relay loads plus FFR, share of RRS | S3 3.16(4) L5282; ASM L26 | system constant | "limited to 60% of the total ERCOT RRS requirement" | Protocol constant | `Limit(max_share=0.60, of='RRS')` | NONE |
| Loads other than CLRs, share of ECRS | S3 3.16(7) L5287 | system constant | "limited to 50% of the total ERCOT ECRS requirement" | Protocol constant | `Limit(max_share=0.50, of='ECRS', where=(('type', 'NCLR'),))` | NONE |
| Minimum Non-Spin from SCED-dispatchable resources | ASM L41; S3 3.16(3) L5279 | per hour | "shall not be less than lower of ERCOT's Most Severe Single Contingency (MSSC) value and the Non-Spin requirement for that hour" | ERCOT methodology | none: `Limit` has maximums only | ABSENT (whether real-time SCED enforces it is not stated) |
| FFR-priority hours (pending NPRR1128) | S3 3.16(2)(b) L5277, 3.16(4) L5284 | per hour | none | ERCOT posting | none | ABSENT (pending) |
| Limits on distribution-connected resources subject to load shed (pending NPRR1128/1171/1213) | S3 3.16(3) L5281 | system | none | ERCOT methodology | a `Limit` with `where` could carry it once a resource column exists | ABSENT (pending) |
| DRRS demand curve and product (pending NPRR1309) | S4 4.4.12(1) L1284; S6 6.5.7.3(14)-(15) L1277-1285 | per hour | see rows above | ERCOT | a new `Product` and `reserve_demand` rows would work in the core; the adapter cannot map a new product | HARD-CODED in the adapter (pending): `adapter.CAPABILITY`, `adapter.OFFER_PRICE`, `adapter.OFFER_TYPES` are keyed by today's product names |

### 1.5 Ancillary service product rules

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| The product list and direction | S4 4.4.12(1) L1282; S3 3.17 L5292-5338 | system | Reg-Up, Reg-Down, RRS, ECRS, Non-Spin | Protocol constant | `Rules.products`, `Product.name`, `Product.direction` | NONE |
| RRS sub-types sharing one demand curve | S6 6.5.7.5(1)(a)-(b) L1409-1419; S3 3.17.2(3) L5299-5305 | system | PFR, FFR, under-frequency relay | Protocol constant | `Product.demand` (`RRS-PFR`, `RRS-FFR`, `RRS-UFR` count towards `RRS`) | NONE |
| Regulation scaling factor against HDL and LDL | S6 6.5.7.3(12)(a)-(b) L1273-1274 | system constant | "A scaling factor of 5/7" | Protocol constant | `Rules.regulation_share`; which products it applies to: `Product.regulation` | NONE |
| Energy plus up awards within HSL; energy less down awards within LSL | S3 3.18(1) L5345 (awards within HSL − LSL); pending NPRR1309 S6 6.5.7.3(14)(c) L1280 | rule | none | Protocol constant | fixed rows in `core/features/reserves.py` `resource_rows()` | NONE (matches; not a switch) |
| Off-line unit: Non-Spin within HSL | S3 3.18(2) L5346 | rule | "less than or equal to the HSL" | Protocol constant | held resource: up awards ≤ max(high − output, 0) | NONE |
| ECRS limit, On-Line generation or ESR | S3 3.18(4)(a) L5355; S8 8.1.1.2.1.7(3) L376 | per resource | "ten times the Emergency Ramp Rate" | Protocol constant | `Product.ramp_minutes = 10` on `ECRS` (adapter); result in `Inputs.reserve_limits` | NONE |
| Minutes of ramp counted for Reg-Up and Reg-Down | S6 6.5.7.1.12(1)(c) L838 ("for the next five minutes"); no award formula | system | not stated as a limit | reconstructed | `Product.ramp_minutes = 5` | NONE |
| Minutes of ramp counted for Non-Spin | S3 3.17.3(1)(a)(i) L5309 ("within 30 minutes"); no award formula | system | not stated as a limit | reconstructed | `Product.ramp_minutes = 30` | NONE |
| RRS-PFR limit per resource | S3 3.18(3)(a) L5350; S2 L781-782 | per resource | default "20% of its Maximum Droop Response Range (MDRR)"; otherwise from verified droop (Nodal Operating Guide Section 8, Attachment N, not in the folder) | ERCOT calculation | `Inputs.reserve_limits.mw` | DERIVED: MDRR (HSL; MPC for a CLR; HSL − LSL for an ESR), verified droop, the 20% default |
| RRS-FFR limit per resource | S3 3.18(3)(d) L5353 | per resource | "less than or equal to its 15-minute rated capacity" | registration | `Inputs.reserve_limits.mw` | DERIVED: 15-minute rated capacity |
| Synchronous condenser RRS and ECRS limit | S3 3.18(3)(b) L5351, (4)(c) L5357 | per resource | "proven 20-second response capability (which may be 100% of the HSL)" | qualification | `Inputs.reserve_limits.mw` | DERIVED: proven 20-second capability |
| Quick-start unit ECRS limit | S3 3.18(4)(b) L5356 | per resource | "proven ten-minute capability" | qualification | `Inputs.reserve_limits.mw` | DERIVED: proven ten-minute capability |
| Operator reduction of a resource's reserve capability | S6 6.4.9.1.1(6) L565 | per resource, per run | none | operator | `Inputs.reserve_limits.mw` | NONE |
| Eligibility by status: generation | S3 3.9.1(5)(b)(i)-(ii) L3379-3401 | per status | SHUTDOWN, STARTUP: "not eligible for an Ancillary Service award"; OFFQS: "ECRS and Non-Spin"; ONSC: "RRS and ECRS"; OFF: "Non-Spin"; ONHOLD: none | Protocol constant | core: rows of `reserve_limits`. Adapter: fixed table | HARD-CODED: `adapter.ELIGIBLE`, `adapter.HELD_WITH_RESERVES` |
| Which statuses SCED may move | S3 3.9.1(5)(b) L3379-3416; S6 6.5.7.3(10) L1268 | per status | ONSC, ONHOLD: "Base Points will be set equal to the telemetered net real power"; ONTEST: "blocked from" SCED; OFFQS: "available for SCED deployment"; CLR OUTL: "not considered as dispatchable capacity" | Protocol constant | core: `Inputs.resources.dispatchable`. Adapter: fixed sets | HARD-CODED: `adapter.DISPATCHABLE` (includes four retired statuses); CLR: `telResStatus == 'ONL'` in `adapter._load_tables` |
| Startup exception | S6 6.4.9.1.1(4)-(5) L563-564; S3 3.9.1(5)(b)(i)(H) L3386 | per resource, per run | eligible MW = "telemetered HSL of the Resource minus its Base Point" | ERCOT (deployment record) | none in the adapter (STARTUP carries nothing); a user can add `reserve_limits` rows by hand | ABSENT: needs a flag that the unit is starting after a manual ECRS or Non-Spin deployment |
| ESR may not offer Off-Line reserves | S4 4.4.7.2(8) L434 | rule | "may not submit an Off-Line Ancillary Service Offer for an ESR" | Protocol constant | not checked | NOT NEEDED FOR CLEARING: an offer validation |
| Under-frequency and FFR trigger settings | S3 3.18(3)(b)-(d) L5351-5353, (4)(c)-(d) L5357-5358 | system constants | "59.80 Hz", "59.70 Hz", "59.85 Hz" | Protocol constant | none | NOT NEEDED FOR CLEARING: qualification and deployment |
| Awards ignore reserves already under deployment | S6 6.4.9.1.1(1) L560 | rule | "regardless of the quantity of Ancillary Service under deployment" | Protocol constant | deployment is not an input | NONE (matches) |
| Substitution between products | S6 6.5.7.6.2(1) L1767 (deployment: "may not substitute one Ancillary Service for another"); nothing for awards | rule | none | not stated | none; `Product.demand` could express it | NONE |
| DRRS resource rules (pending NPRR1309) | S6 6.5.7.3(14)-(15) L1277-1285; S3 3.18(3) L5348 | per resource | off-line and on-line DRRS-qualified MW; COP status history; "minimum of the difference between the HSL and LSL, and the On-Line DRRS-qualified MW" | qualification / COP | `Inputs.reserve_limits.mw` once the product exists | DERIVED (pending): DRRS-qualified MW on-line and off-line, minimum COP capability over the RUC runs |

### 1.6 Storage

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| State of Charge (SOC), MWh | S6 6.5.5.2(14)(c) L738; 6.5.7.3(1) L1001 | per resource, per run | none | QSE telemetry | `Inputs.storage.soc` | NONE |
| Minimum State of Charge (MinSOC), MWh | S6 6.5.5.2(14)(b) L737; S2 L1432-1433 | per resource, per run | none | QSE telemetry | `Inputs.storage.soc_min` | NONE |
| Maximum State of Charge (MaxSOC), MWh | S6 6.5.5.2(14)(a) L736; S2 L1430-1431 | per resource, per run | none | QSE telemetry | `Inputs.storage.soc_max` | NONE |
| Maximum Operating Discharge Power Limit, MW | S6 6.5.5.2(14)(d) L739 | per resource, per run | none | QSE telemetry | none | ABSENT (how SCED uses it is not written; inferred to sit inside HSL) |
| Maximum Operating Charge Power Limit, MW | S6 6.5.5.2(14)(e) L740 | per resource, per run | none | QSE telemetry | none | ABSENT (same) |
| SCED duration requirement per reserve product | S6 6.5.7.3(1) L1001; 6.5.7.5(1) L1410, L1414, L1425, L1438, L1451; 6.3.2(6) L450 | per product | not given under that name; see section 3 | not stated | `Product.duration_hours` | NONE |
| SCED duration requirement for the ESR Base Point | S6 6.5.7.5(1)(l)(viii)-(xi) L1467-1470 | system | not given | not stated | `Rules.interval_hours` (one interval of energy) | NONE |
| Form of the state-of-charge rows; up awards met by charging less need no stored energy | not written (S6 L1001 states the aim only) | fixed behaviour | none | package | `core/features/storage.py` | HARD-CODED: the charge offset (`w` variables) cannot be switched off |
| Charging and discharging efficiency | not in the rules read | per resource | none | not stated | none | ABSENT (not an ERCOT input as far as the text shows) |
| ESR dispatched to charge only by SCED; OUT means unavailable | S6 6.5.7.3(17) L1304; S4 4.4.9.7(3) L957 | rule | none | Protocol constant | negative dispatch; `dispatchable` | NONE |
| ESR HSL and LSL updated for state-of-charge limits | S3 3.8.5(1) L3302 | per resource, per run | none | QSE telemetry | `Inputs.resources.high`, `.low` | NONE |
| Hour Beginning Planned SOC (HBSOC) | S3 3.9.1(5)(h)(iii) L3429; S2 L1428-1429 | per resource, per hour | none | QSE (COP) | none | NOT NEEDED FOR CLEARING: COP, used by RUC and DAM |
| DC-Coupled Resource renewable component telemetry (pending NPRR1029) | S6 6.5.5.2(21) L760-762 | per resource | none | QSE telemetry | none | ABSENT (pending) |

### 1.7 Load resources

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Load Resource net real power consumption | S6 6.5.5.2(6)(a) L690 | per resource, per run | none | QSE telemetry | CLR: `Inputs.resources.output` as negative MW. Other loads: inside the reserve room below | NONE |
| Low Power Consumption (LPC) | S6 6.5.5.2(6)(d) L693; S2 L712-713 | per resource, per run | none | QSE telemetry | CLR: `Inputs.resources.high` = −LPC. Other loads: inside the reserve room | DERIVED: LPC (no column of its own) |
| Maximum Power Consumption (MPC) | S6 6.5.5.2(6)(e) L694; S2 L783-784 | per resource, per run | none | QSE telemetry | CLR: `Inputs.resources.low` = −MPC | DERIVED: MPC (no column of its own; also the proxy reserve offer MW) |
| Reserve room of a load that is not a CLR | S6 6.5.7.5(1)(l)(vii) L1466 (monitor wording); no SCED award rule | per resource, per run | "the Net Power Consumption minus the Low Power Consumption" | ERCOT calculation | adapter: `high` = consumption − LPC, floor 0 | HARD-CODED: `adapter._load_tables`, `room = clip(realPowerConsumption - lowPowerConsumption, 0)` |
| Self-provided RRS and ECRS from relay-controlled loads (MW) | S6 6.5.5.2(6)(f) L695; 6.4.9.1.1(3) L562 | per resource, per run | "limited based on the QSE's Day-Ahead Market (DAM) Ancillary Service awards and trades"; how SCED clears it is not stated | QSE telemetry | adapter: a $0 offer block per product | HARD-CODED: `adapter._load_tables`, `price: 0.0`, products `RRS-UFR`, `RRS-FFR`, `ECRS` |
| High-set under-frequency relay status | S6 6.5.5.2(6)(g) L696 | per resource, per run | "disabled or unarmed" for a load providing Non-Spin | QSE telemetry | folded into `Inputs.reserve_limits` (which products the load may carry) | DERIVED: relay status |
| Load Resource status | S6 6.5.5.2(6)(j) L699; S3 3.9.1(5)(b)(iii) L3402-3409 | per resource, per run | "OUTL – Not available"; "ONL – On-Line and available"; pending NPRR1188: ONTEST, ONHOLD | QSE telemetry | `Inputs.resources.dispatchable` | HARD-CODED in the adapter: `telResStatus == 'ONL'` (counted under 1.5) |
| Which loads are controllable | registration | per resource | none | registration | adapter: a load with a non-zero Base Point or a bid curve | HARD-CODED: `adapter._load_tables`, the `ctrl` test (non-zero Base Point or a bid curve) |
| CLR 5-minute ramp rates | S6 6.5.5.2(6)(n) L703 | per resource, per run | none | QSE telemetry | `Inputs.resources.ramp_low`, `.ramp_high` | DERIVED (counted under 1.1, HDL and LDL for a CLR) |
| CLR Scheduled Power Consumption; "Plus Two Hours" forecast for aggregate loads | S6 6.5.5.2(6)(h) L697, (k) L700; S2 L1306-1309 | per resource | none | QSE telemetry | none | NOT NEEDED FOR CLEARING: marks the zero-deployment level for Non-Spin performance (inferred) |
| Load Resource RRS capability and reserve ramp rates | S6 6.5.5.2(6)(l)-(m) L701-702 | per resource, per run | none | QSE telemetry | `Inputs.reserve_limits.mw` | NONE (counted under 1.1) |
| Where a CLR bid sits on the network | S6 6.5.7.3(14)(b)(iii) L1293; pending NPRR1188 L1295 | per resource | "distributed across all nodes in the Load Zone"; pending: only for an Aggregate Load Resource | Protocol constant | `Inputs.resource_nodes` with `share` | NONE |
| Operator override of a CLR's parameters | S6 6.5.7.3(16) L1303 | per resource | none | operator | the user edits the tables | NONE |
| Provisional CLR Adjusted Bid Cap (pending NPRR1325) | S4 4.4.9.4.4 L902-913; S6 6.5.7.3(14)(b)(iv) L1297 | per resource, per run | thresholds "90%"; Shift Factor "equal to or less than -2%"; cap = lowest constraint contribution plus step-1 System Lambda "minus $0.01/MWh" | ERCOT calculation | none | ABSENT (pending) |

### 1.8 Demand (GTBD) and its components

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Generation To Be Dispatched (GTBD) | S2 L558-559; S6 6.5.7.3(3) L1008 | per run | "calculated every four seconds"; "determined by LFC"; no formula | ERCOT calculation (LFC) | `Inputs.demand` | NONE |
| The adapter's demand | not a rule | per run | none | package | sum of the run's Base Points; `adapter.inputs()` has no demand argument (override afterwards with `inputs.copy(demand=...)`) | HARD-CODED: `adapter.inputs`, `demand=float(res['output'].sum())` |
| GTBD formula and its coefficients (load, frequency and ramp terms, "K factors") | not in the folder: no formula or coefficient in S2 or S6 | per run | not written | ERCOT calculation | none | DERIVED: not written in these documents, so no inputs can be listed |
| CLR consumption subtracted from GTBD | S6 6.5.7.3(3) L1008 | per run | "shall subtract the sum of the telemetered net real power consumption from all CLRs available to SCED" | ERCOT calculation | CLRs are negative output inside the adapter's sum | NONE |
| Output of resources SCED does not move | S3 3.9.1(5)(b)(i)(J)-(K) L3390-3391 | per resource, per run | Base Point "set equal to the telemetered net real power" | QSE telemetry | `Inputs.resources.output` with `dispatchable = False` | NONE |
| DC Tie schedules, as fixed injections | no SCED rule found in the sections read | per run | none | schedules | inside `Inputs.demand` and `Inputs.constraints.flow` (inferred) | NONE |
| Load forecast for the non-binding projection | S6 6.5.7.3(15) L1302 | per future interval | none | ERCOT | none | NOT NEEDED FOR CLEARING: the projection is non-binding |

### 1.9 Network

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Active constraints (contingency and limiting element pairs) | S6 6.5.7.1.11(1) L828; 6.5.7.1.9 L802 | per run | none | operator, after verification | rows of `Inputs.constraints` (`name`) | NONE |
| Constraint limit (rating, dynamic rating, Generic Transmission Limit) | S6 6.5.7.1.13(1)(c) L856-861; 6.5.7.1.7 L797; S2 L556-557 | per constraint, per run | none | TSP ratings / ERCOT | `Inputs.constraints.limit` | NONE |
| Constraint flow before re-dispatch | S6 6.5.7.1.13(1)(b) L855; 6.5.7.1.10(1) L804 | per constraint, per run | none | ERCOT calculation (State Estimator, NSA) | `Inputs.constraints.flow` | NONE |
| Shift Factors | S6 6.5.7.1.13(3)(c) L882; pending NPRR1239/1249 L887; S3 3.19.1(5) L5381-5383; S2 L1402-1403 | per constraint and bus, per run (posted hourly) | "relative to the distributed load reference Bus" | ERCOT calculation | `Inputs.shift_factors` | NONE |
| Resource to node map | S6 6.5.7.3(14)(b)(iii) L1293 | per resource | none | registration | `Inputs.resource_nodes` | NONE |
| Shift Factor cutoff | AttP 3.3 L50 | system constant | "default value of Shift Factor cut off is 0.0001" | ERCOT (EMS setting) | `Rules.shift_factor_cutoff` | NONE |
| Maximum Shadow Price per constraint | S6 6.5.7.1.11(2) L829; AttP L13-15 | per constraint | see next rows | ERCOT | `Inputs.constraints.max_shadow_price`; blank: `Rules.default_max_shadow_price` | NONE |
| Generic caps by constraint class | AttP 3.5 L60-65 | system constants | "Base Case/Voltage Violation: $5,251/MW"; N-1 "Greater than 200 kV: $4,500/MW"; "100 kV to 200 kV: $3,500/MW"; "Less than 100 kV: $2,800/MW" | Protocol constant (PUCT approved) | only one default: `Rules.default_max_shadow_price = 5251` | DERIVED: constraint class (base case or contingency) and voltage level |
| Irresolvable constraint: triggers | AttP 3.6.1 L101-103 | per constraint | "more than two consecutive hours on more than 4 consecutive Operating Days"; "more than a total of 20 hours in a rolling thirty-day period" | ERCOT determination | result in `max_shadow_price` | DERIVED: history of unresolved intervals per constraint |
| Irresolvable constraint: cap | AttP 3.6.2 L110-112 | per constraint | minimum of the generic cap and "the largest value of the Mitigated Offer Cap (MOC) for Resource C" divided by its shift factor "or $2000 per MW" | ERCOT calculation | result in `max_shadow_price` | DERIVED: Resource C, its largest MOC, its shift factor, the generic cap, $2000 |
| Irresolvable constraint: Resources C and D, shift factor screen | AttP 3.6.1 L105-107 | per constraint | ignore shift factors "of less than 0.02" | ERCOT determination | none | DERIVED (same helper) |
| Irresolvable constraint: net margin step-down | AttP 3.6.2 L114-115; 3.6.3 L127-131 | per constraint, per year | above "$95,000/MW": minimum of "$2,000/MWh" or the maximum of the MOC ratio and "LCAP"; net margin = running sum of "¼ times" max(0, reference price − POC); POC = "10 times the Fuel Index Price (FIP)" | ERCOT calculation | result in `max_shadow_price` | DERIVED: Resource D's settlement prices, FIP, LCAP ("2,000", S4 L1260-1262) |
| IROL cap | AttP 3.7 L133-137 | per constraint | Base Case generic cap, or "The power balance penalty price minus the mitigated offer floor for Resource H" divided by its shift factor; Resource H from shift factors "not lower than 10%" | ERCOT determination | result in `max_shadow_price` | DERIVED: Resource H, its floor and shift factor, the penalty price, frequency bias |
| Shift factor efficiency threshold and maximum congestion component (the method behind the generic caps) | AttP 3.2 L36, L42; 3.4 L53-56 | system | "threshold (10%)"; "(say $500/MWh)"; defaults written as "x%", "$y/MWh", "z%" | ERCOT methodology | none | NOT NEEDED FOR CLEARING: explains how the caps were chosen; the caps themselves are the input |
| Form of the constraint row | not written | fixed behaviour | none | package | flow + Σ SF × (MW − output) ≤ limit + violation | NONE (reconstructed; not a switch) |
| Node price formula | AttP 3.1 L18-24 (formula image lost) | rule | LMP = System Lambda − Σ Shift Factor × Shadow Price (terms listed) | Protocol constant | `Result.node_prices()` | NONE |
| Competitive or Non-Competitive designation | S3 3.19.4 L5434-5445; S2 L164-165, L872-873 | per constraint, per run (holds for the hour) | see 1.11 | ERCOT calculation / IMM | none | ABSENT |
| Constraints the adapter can enforce | not a rule | per run | none | package | only constraints in the binding-constraint report that have shift factors; the rest are dropped | HARD-CODED: `adapter.inputs` (drop when no shift factors) and `adapter._constraints` (duplicates: keep the highest shadow price) |
| Breaker status, bus voltages, MW/MVAr pairs, tap positions, weather | S6 6.5.7.1.13(1) L847-868 | per run | none | TSP telemetry | none | NOT NEEDED FOR CLEARING: inputs to the State Estimator and NSA, which produce the constraints |
| Security violation thresholds | S6 6.5.7.1.10(1)(a) L805, (2)(b) L809 | system constants | "100% of the Emergency Rating"; "125% or greater" | Protocol constant | none | NOT NEEDED FOR CLEARING: decides which constraints are raised |

### 1.10 Penalties and price caps

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Under-generation Power Balance Penalty Price | AttP 4.1 L144; S6 6.5.7.1.11(3) L830 | system constant | "the effective Value of Lost Load (VOLL) plus the effective Real-Time System-Wide Offer Cap (RTSWCAP) plus $4,052.01/MWh" | Protocol constant | `Rules.shortage_price` (one number: 5000 + 2000 + 4052.01) | NONE |
| The three parts of that penalty as separate inputs | same | system | VOLL "5,000"; RTSWCAP "2,000"; adder "$4,052.01/MWh" | Protocol constant | VOLL: `Rules.price_cap`. RTSWCAP and the adder: no field | ABSENT for RTSWCAP (counted under 1.2) and for the adder as named fields; the sum does not follow a change of `price_cap` |
| Over-generation Power Balance Penalty Price | AttP 4.1 L144 | system constant | "-$250/MWh" | Protocol constant | `Rules.surplus_price` | NONE |
| Shape of the power balance penalty | AttP L15, L144 | system | "a single value" | Protocol constant | one shortfall and one surplus variable | NONE |
| Effective VOLL | S4 4.4.11(1)(a) L1237; table L1254-1256 | system value, switchable | "HCAP – DAM (DASWCAP)" "5,000" | Protocol constant | `Rules.price_cap` | NONE |
| Cap on System Lambda and reserve prices | S6 6.5.7.3(14)(d) L1301 | rule | "capped at the effective VOLL" | Protocol constant | `Rules.price_cap`, applied after the solve | NONE |
| Cap on a bus price above VOLL | S6 6.5.7.3(14)(d) L1301 | rule | "the greater of the effective VOLL or the initial LMP minus the positive difference between System Lambda and the effective VOLL" | Protocol constant | `Result.node_prices()` with `Rules.price_cap` | NONE |
| Emergency Pricing Program switch | S4 4.4.11(1)(a)(i) L1238-1240; table L1251-1253 | system, per event | "12 hours within a rolling 24-hour period"; ECAP "2,000"; ends "24 hours after" | ERCOT determination | the user makes a rulebook with the lower VOLL | NOT NEEDED FOR CLEARING: it decides which VOLL is in effect; the clearing needs only the effective value |
| Peaker Net Margin switch | S4 4.4.11(1)(a)(ii) L1241; 4.4.11.1 L1271-1280; table L1260-1265 | system, per year | LCAP "2,000"; PNM threshold "315,000" $/MW-year; POC "ten times the effective daily FIP" | ERCOT calculation | same | NOT NEEDED FOR CLEARING: same reason |
| Day-ahead penalty factors | AttP Appendix 1 L147-192 | system | for example "Under Generation" "5,000,000.00" | ERCOT | none | NOT NEEDED FOR CLEARING: day-ahead market only |

### 1.11 Two-step process and mitigation

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Step 1: SCED on Competitive Constraints only, to get Reference LMPs | S6 6.5.7.3(14)(a) L1287 | per run | none | ERCOT calculation | not run: one LP per interval | ABSENT |
| Step-2 curve after mitigation | S6 6.5.7.3(14)(b)(i)-(ii) L1291-1292 | per resource, per run | floor: "the lesser of the Reference LMP (from Step 1) or the appropriate Mitigated Offer Floor"; cap: "the greater of the Reference LMP ... plus a variable not to exceed 0.01 multiplied by the value of the Resource's Mitigated Offer Cap (MOC) curve at the LSL or the appropriate MOC" | ERCOT calculation | `Inputs.energy_offers` (the adapter reads ERCOT's SCED2 curve, taken to be this one; inferred) | DERIVED: Reference LMP per node, Mitigated Offer Floor, MOC curve, mitigation flag, the 0.01 variable |
| Reference LMP at each Resource Node | S6 6.5.7.3(14)(a) L1287 | per node, per run | none | ERCOT calculation | none | ABSENT |
| Mitigated Offer Floor by resource category | S4 4.4.9.4.2 L868-888 | system constants | Nuclear and Hydro "-$250/MWh"; Coal and Lignite "-$20/MWh"; Combined Cycle "-$20/MWh"; Gas/Oil Steam and Combustion Turbine "-$20/MWh"; Qualifying Facility "-$50/MWh"; Wind "-$100/MWh"; PhotoVoltaic "-$50/MWh"; ESR "-$250/MWh"; Other "-$50/MWh" | Protocol constant | none | ABSENT (also needs a resource category column) |
| Mitigated Offer Cap curve, generation | S4 4.4.9.4.1(1) L765-771 | per resource, per hour | "MOC q, r, h = Max [GIHR q, r * Max(FIP, WAFP q, r, h), (IHR q, r * FPRC q, r + OM q, r)]"; Solid Fuel Price "$1.50" (L799) | ERCOT calculation | none | ABSENT: needs heat rates, FIP, FOP, fuel adder, O&M, fuel percentages, Exceptional Fuel Cost (verifiable costs, not public) |
| Mitigated Offer Cap, ESR | S4 4.4.9.4.1(1)(c) L835 | system | "shall be set at the RTSWCAP" | Protocol constant | none | ABSENT |
| Mitigated Offer Cap, special cases (emergency-contracted capacity, quick-start, hydro, RMR) | S4 4.4.9.4.1(1)(a)-(b), (d)-(e) L833-837; 4.4.9.4.3 L890; pending NPRR826 L893-900 | per resource | every point "greater than the effective Value of Lost Load (VOLL)" (L833); RMR pending: "$0.01/MWh", "minus $1/MWh" | ERCOT calculation | none | ABSENT |
| Exceptional Fuel Cost threshold | S4 4.4.9.4.1(1)(f)(i) L839 | system constant | "$1/MMBtu"; purchases of "at least 10%" of the fuel burned (L845) | Protocol constant | none | ABSENT (inside the MOC) |
| The "variable not to exceed 0.01" | S6 6.5.7.3(14)(b)(i) L1291 | system | "not to exceed 0.01"; the value in use is not stated | ERCOT | none | ABSENT |
| Mitigation flag per resource | S3 3.19.4(7)-(8) L5446-5452; S6 6.5.7.4(1)(e) L1397 | per resource, per run (holds for the hour) | all of: Non-Competitive Constraint; pivotal player or ECI share "greater than DMEECP"; shift factor "greater than SFP4" | ERCOT calculation | none | ABSENT |
| SCED Constraint Competitiveness Test | S3 3.19.4(2) L5435-5441; 3.19.2 L5413-5419 | per constraint, per run | ECI "less than ECIT2"; resolvable without the entity's capacity; shift factors at or above SFP3; not already non-competitive this hour | ERCOT calculation | none | ABSENT |
| ECIT2 | S3 3.19.1(6) L5400-5402 | system constant | "2300" | Protocol constant | none | ABSENT |
| SFP1, SFP3, SFP4 | S3 3.19.1(6) L5391-5393, L5403-5405, L5409-5411 | system constants | "2%" each | Protocol constant | none | ABSENT |
| DMEECP | S3 3.19.1(6) L5406-5408 | system constant | "10%" | Protocol constant | none | ABSENT |
| ECIT1, SFP2 (long-term test) | S3 3.19.1(6) L5394-5399 | system constants | "2000"; "2%" | Protocol constant | none | NOT NEEDED FOR CLEARING: the yearly test; SCED uses the per-run test |
| Decision Making Entity of each resource | S3 3.19.1(4) L5380; S6 6.5.7.3(7) L1239 | per resource | none | registration | none | ABSENT |
| Available Capacity for the test | S3 3.19.1(3) L5363-5379; pending NPRR1182 L5372-5374 | per resource, per run | generation: telemetered HSL; ESR: minimum of HSL − LSL and (max SOC − min SOC) "divided by 15 minutes"; DC Tie: full import capability on the export side | ERCOT calculation | none | ABSENT |
| IMM override of a designation | S3 3.19.4(5) L5444 | per constraint | none | IMM | none | ABSENT (would be the user editing the competitive flag) |
| No mitigation of CLR bids | S6 6.5.7.3(14)(b)(iii) L1293 | rule | "There is no mitigation of RTM Energy Bids." | Protocol constant | bids used as given | NONE |

### 1.12 Pricing run and price adders

A second pair of SCED runs with changed inputs. Nothing here exists in the package: every row is ABSENT unless noted.
The adders change settlement prices, not the LMPs of the binding run.

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Whether any reliability deployment is active | S6 6.5.7.3.1(1) L1306-1332 | per run | categories (a)-(i), more pending | ERCOT | none | ABSENT |
| RUC-committed (ONRUC, not opted out) and On-Line RMR resources; pending NPRR1091/1309 adds deployed Off-Line Non-Spin and DRRS | S6 6.5.7.3.1(2)(a) L1334-1339 | per resource, per run | "Set the LSL and LDL to zero"; "Remove all Ancillary Service Offers"; step-1 offer "equal to the power balance penalty price" from 0 MW to HSL | ERCOT calculation | none | ABSENT: needs the RUC/RMR flag |
| RUC'd combined-cycle transition | S6 6.5.7.3.1(2)(b) L1340-1343 | per resource, per run | LSL, LDL and reserve capability cut to the COP values of the QSE-committed configuration; penalty-price offer on the added capacity | ERCOT calculation | none | ABSENT: needs COP HSL and capabilities at the RUC snapshot |
| Ramp relaxation for other generation | S6 6.5.7.3.1(2)(c) L1344-1346; pending NPRR904 L1348-1350 | per resource, per run | "Aggregated Resource Output - (60 minutes * Normal Ramp Rate down), or LSL"; excludes output "less than 95% of LSL" and statuses ONRUC, ONTEST, STARTUP, SHUTDOWN | ERCOT calculation | none | ABSENT: needs ramp rates in MW/min |
| Ramp relaxation for ESRs and CLRs | S6 6.5.7.3.1(2)(d)-(e) L1351-1356; pending L1358-1360 | per resource, per run | "60 minutes"; ESR only "If the ESR SCED Base Point is not at LDL" (or HDL) | ERCOT calculation | none | ABSENT |
| Deployed MW from loads that are not CLRs (RRS, ECRS, Non-Spin) added to GTBD | S6 6.5.7.3.1(2)(f) L1361 | per run | ramped over "the ten-minute ramp period" (RRS, ECRS) or "the 30-minute ramp period" (Non-Spin) | ERCOT calculation from telemetry and instructions | none | ABSENT |
| Bid curve for that deployed load | S6 6.5.7.3.1(2)(f) L1361 | system constants | "$300/MWh for the first MW" to "$700/MWh for the last MW" | Protocol constant | none | ABSENT |
| Deployed ERS MW and its restoration | S6 6.5.7.3.1(2)(g) L1364-1372 | per run | RHours "4.5" hours | ERCOT calculation | none | ABSENT |
| DC Tie emergency imports, exports and curtailments | S6 6.5.7.3.1(1)(e)-(f) L1311-1312, (2)(h)-(i) L1373-1374; pending NPRR904 L1314-1318, L1376-1379 | per run | "shall not exceed 1,250 MW in a single interval" | operator instruction | none | ABSENT |
| Block Load Transfer MW | S6 6.5.7.3.1(1)(g)-(h) L1319-1320, (2)(j)-(k) L1380-1381 | per run | none | operator instruction | none | ABSENT |
| TDSP load management MW (pending NPRR1006), distribution voltage reduction (pending NPRR1105), Voluntary Early Curtailment Load (pending NPRR1238) | S6 L1321-1325, L1329-1330, L1363, L1383 | per run | VECL: "$300/MWh" to "$700/MWh", "30-minute ramp period", "one-hour restoration period" | ERCOT | none | ABSENT (pending) |
| Firm load shed in EEA Level 3 | S6 6.5.7.3.1(1)(i) L1328, (2)(o)-(p) L1387-1388 | per run | adder = "the VOLL used to determine the ASDCs for the RTM minus the System Lambda" | operator | none | ABSENT |
| The pricing run's own two steps | S6 6.5.7.3.1(2)(l)-(n) L1384-1386 | per run | Competitive Constraints only, then mitigation, then all constraints | ERCOT calculation | `pricing_run(unmitigated=...)` runs both steps; a mitigated RUC or RMR unit is capped at its step-1 price | PARTIAL (which resources are mitigated is read from ERCOT's data) |
| Energy adder and reserve adders | S6 6.5.7.3.1(2)(o)-(p) L1387-1388 | per run | "the positive difference" of the two System Lambdas; per product, of the two MCPCs | ERCOT calculation | none | ABSENT |

### 1.13 Timing and solver settings

| Input | Source | Granularity | Value in the rules | Who sets it | In opensced | Gap |
|---|---|---|---|---|---|---|
| Run interval | S6 6.5.7.3(1) L1001 | system | "approximately every five minutes, or more frequently if necessary" | ERCOT | `Rules.interval_hours` | NONE |
| Run timestamp (picks the rulebook) | S6 6.3.2 L373-375 | per run | none | ERCOT | `Inputs.time` | NONE |
| Latest valid offers at the time of the run | S4 4.4.9.3(4) L717; 4.4.9.7(5) L961; S6 6.4.9.1(2) L558 | per run | none | ERCOT | the user supplies that run's offers | NONE |
| Which parts of the clearing are on | not a rule | per rulebook | none | package | `Rules.features` | NONE |
| Objective | S6 6.5.7.3(1) L1001; AttP 4.1 L143 | system | "maximizing bid-based revenues minus offer-based costs"; "the sum of four components" | Protocol constant | fixed in `core/model.py` | NONE (matches) |
| Regulation deployment "minimized over time" | S6 6.5.7.3(2) L1007 | system | no formula | not stated | none | ABSENT (nothing to implement from the text) |
| Non-binding projection | S6 6.5.7.3(15) L1302 | per run | "every five minutes for at least 15 minutes into the future" | ERCOT | none | NOT NEEDED FOR CLEARING |
| HDL and LDL refresh time | S6 6.5.7.2(1) L904 | system | "within four seconds" | ERCOT | none | NOT NEEDED FOR CLEARING |
| Solver and its options | not in the rules | package | none | package | HiGHS through scipy, default options | HARD-CODED: `core/program.py` `solve()`, `method='highs'`, no options |
| Numerical tolerances | not in the rules | package | none | package | 1e-6 MW (movable range, block width, reserve limit), 1e-9, 1e-12 (shift factor) | HARD-CODED: literals in `core/model.py`, `core/features/balance.py`, `reserves.py`, `network.py` |
| Split point at 0 MW in every curve | not in the rules | package | none | package | a knot is always kept at 0 MW | HARD-CODED: `core/features/balance.py` `blocks()` |
| Number of curve points read from the disclosure | not a rule: file format | per file | 35 | package | adapter | HARD-CODED: `adapter.NPT = 35` |

---

## 2. What to add

One line each: the proposed input, its type, unit and default. Defaults keep today's results unless the line says so.

### 2.1 HARD-CODED: turn the constant into an input

1. `Rules.offer_floor`: number, $/MWh, default `-250.0`. Replaces `adapter.PROXY[0]`; the bottom price of every proxy curve (S4 4.4.9.3.1(2)).
2. `Rules.proxy_price_step`: number, $/MWh, default `0.01`. The gap between the floor and the next proxy point (−$249.99) and between RTSWCAP and RTSWCAP − $0.01. Replaces `adapter.PROXY[1]`.
3. `Rules.proxy_mw_step`: number, MW, default `1.0`. The "1 MW" in every proxy curve. Replaces the `hi - 1` literal in `adapter._sced_tables`.
4. `Rules.irr_proxy_price`: number, $/MWh, default `1500.0`. Replaces `adapter.PROXY[2]`; to be used for IRRs only once the proxy helper (item 65) knows resource types.
5. `Rules.no_offer_price`: number, $/MWh, default `0.0`. The price the core gives a dispatchable resource with no curve (`balance.blocks`).
6. `Rules.curve_extension`: text, one of `'flat'`, `'floor'`, default `'flat'`. `'floor'` prices the range below a curve's lowest point at `offer_floor` (+ step), as 6.5.7.3(4)(b) does. Replaces the fixed `np.interp` behaviour in `balance.blocks`.
7. `Rules.reserve_offer_floor`: number, $/MW per hour, default `0.0`. Replaces `max(price, 0.0)` in `reserves.offer_variables` (needed for the pending −$0.01 FFR offers).
8. `Rules.no_reserve_offer_price`: number, $/MW per hour, default `0.0`. The price of reserves when no `reserve_offers` table is given.
9. `Rules.self_arranged_price`: number, $/MW per hour, default `0.0`. Replaces the literal `0.0` on self-provided load reserves in `adapter._load_tables`.
10. `Rules.statuses`: tuple of `Status(name, dispatchable: bool, held_with_reserves: bool, reserve_products: dict offer kind -> tuple of product names or None)`, default = today's `adapter.DISPATCHABLE`, `HELD_WITH_RESERVES` and `ELIGIBLE`. Replaces those three constants and the `'ONL'` test for loads.
11. `Inputs.resources.status`: text, no unit, default `''`. Declares the column the adapter already writes, so a rulebook's `statuses` can act on it.
12. `Product.capability_columns`, `Product.offer_price_columns`, `Product.offer_kinds`: tuples of text, default = today's entries of `adapter.CAPABILITY`, `OFFER_PRICE`, `OFFER_TYPES`. Lets a new product (DRRS) be added without editing the adapter.
13. `adapter.inputs(..., demand=None)`: number, MW, default `None` (= sum of Base Points). Lets GTBD be passed in.
14. `adapter.inputs(..., storage_types=('ESR', 'PWRSTR'))`: tuple of text. Replaces `adapter.STORAGE_TYPES`.
15. `adapter.inputs(..., zero_price_is_blank=None)`: bool, default `None` (= true before 2026-02-03). Replaces `adapter.ZERO_FILL_END`.
16. `adapter.inputs(..., load_room='consumption-lpc')`: text, one of `'consumption-lpc'`, `'mpc-lpc'`. Replaces the fixed `room` formula in `adapter._load_tables`.
17. `adapter.inputs(..., controllable=None)`: list of resource names, default `None` (= loads with a Base Point or a bid curve). Replaces the fixed `ctrl` test.
18. `Rules.clr_no_bid_price`: number or None, $/MWh, default `None` (= hold the load at its Base Point, today's behaviour). Set to the VOLL to follow 6.5.7.3(9).
19. `adapter.inputs(..., missing_shift_factors='drop')`: text, one of `'drop'`, `'error'`. Replaces the silent drop of constraints without shift factors.
20. `Rules.demand_curve_pricing`: text, one of `'mean'`, `'left'`, default `'mean'`. How a segment between two demand-curve points is priced (`reserves.segments`).
21. `Rules.storage_charge_offset`: bool, default `True`. Whether an up award met by charging less is free of stored energy (`storage.py`, the `w` variables).
22. `Rules.zero_split`: bool, default `True`. Whether every curve is cut at 0 MW (`balance.blocks`).
23. `Rules.solver`: text, default `'highs'`; `Rules.solver_options`: dict, default `{}`, passed to `scipy.optimize.linprog(options=...)`.
24. `Rules.tolerance_mw`: number, MW, default `1e-6`. Replaces the `1e-6` literals in `model.py`, `balance.py`, `reserves.py`.
25. `adapter.inputs(..., curve_points=35)`: integer, default `35`. Replaces `adapter.NPT`.

### 2.2 ABSENT: add a place for it

Named prices
26. `Rules.offer_cap`: number, $/MWh, default `2000.0` in the ERCOT rulebooks (`None` in `Rules()`). The RTSWCAP.
27. `Rules.voll`: number, $/MWh, default `5000.0` in the ERCOT rulebooks (`None` in `Rules()`). The effective VOLL; `price_cap` defaults to it.
28. `Rules.shortage_adder`: number, $/MWh, default `4052.01` in the ERCOT rulebooks. When `shortage_price` is `None` it is computed as `voll + offer_cap + shortage_adder`.

Resources
29. `Inputs.resources.output_schedule`: number, MW, default blank. The Output Schedule MW.
30. `Inputs.resources.ruc_committed`: bool, default `False`.
31. `Inputs.resources.rmr`: bool, default `False`.
32. `Inputs.resources.category`: text, default `'other'`. The Mitigated Offer Floor category (nuclear, hydro, coal, combined_cycle, gas_steam_ct, qf, wind, pv, esr, other); also tells the proxy helper which resources are IRRs.
33. `Inputs.resources.entity`: text, default `''`. The Decision Making Entity, for the competitiveness test.
34. `Inputs.resources.max_consumption` and `Inputs.resources.low_consumption`: number, MW, default blank. MPC and LPC of a Load Resource.
35. `Inputs.resources.starting_after_deployment`: bool, default `False`. The startup exception of 6.4.9.1.1(4)-(5): eligible MW = high − output.
36. `Inputs.storage.max_discharge` and `Inputs.storage.max_charge`: number, MW, default blank (not enforced when blank).
37. `Inputs.storage.efficiency`: number, share, default `1.0`. Not an ERCOT input in the text read; listed so the table has the column.

RUC
38. `Rules.ruc_offer_floor`: number, $/MWh, default `250.0`. Floor on a RUC-committed resource's energy curve (6.5.7.3(4)(d)).
39. `Rules.ruc_reserve_offer_price`: number, $/MW per hour, default `250.0`. (6.5.7.3(5)(e)).
40. `Rules.ruc_emergency_offer_price`: number or None, $/MWh, default `None`; `4500.0` when the pending NPRR930/1019 rules apply (the lesser of it and `voll`).

Reserve requirements
41. `Inputs.reserve_requirements`: table `product` (text), `mw` (number, MW); default: the width of the product's demand curve. The Ancillary Service Plan; used by `Limit.max_share`, `Product.reserved_mw` and the proxy offer floor.
42. `Limit.min_mw` and `Limit.min_share`: number, MW and share, default `None`. A minimum for a group of products and resources (Non-Spin from SCED-dispatchable resources; the PFR minimum written as a floor).
43. `Inputs.reserve_minimums`: table `limit` (text), `mw` (number, MW), default none. Per-run values for a named `Limit` (the monthly PFR minimum, the MSSC), overriding the rulebook's number.
44. `Rules.exclusive_reserves`: tuple of `(where, products_a, products_b)`, default `()`. One resource may not hold both groups (Non-Spin with RRS or ECRS on a load that is not a CLR). Needs a yes/no variable per resource, so a mixed-integer solve or a two-pass rule.

Two-step process and mitigation
45. `Inputs.constraints.competitive`: bool, default `True`.
46. `Inputs.resources.mitigated`: bool, default `False`. The result of the competitiveness test for the run.
47. `Inputs.mitigated_offer_caps`: table `resource` (text), `mw` (number, MW), `price` (number, $/MWh); default none. The MOC curve.
48. `Rules.mitigated_offer_floors`: dict category -> $/MWh, default `{'nuclear': -250, 'hydro': -250, 'coal': -20, 'combined_cycle': -20, 'gas_steam_ct': -20, 'qf': -50, 'wind': -100, 'pv': -50, 'esr': -250, 'other': -50}`.
49. `Rules.mitigation_adder_share`: number, share, default `0.01`. The "variable not to exceed 0.01" times the MOC at LSL (the value ERCOT uses is not stated; 0.01 is the upper bound).
50. `Rules.esr_mitigated_offer_cap`: number or None, $/MWh, default `None` (= `offer_cap`).
51. `Rules.competitiveness`: `Competitiveness(eci_max=2300, constraint_shift_factor=0.02, entity_shift_factor=0.02, entity_share=0.10, resource_shift_factor=0.02, esr_minutes=15)`. ECIT2, SFP3, SFP1, DMEECP, SFP4 and the 15 minutes in an ESR's Available Capacity.
52. `Rules.two_step`: bool, default `False`. Runs step 1 on competitive constraints, mitigates, then runs step 2; `Result.reference_prices` holds the step-1 node prices.

Pricing run
53. `Inputs.resources.reliability_deployed`: bool, default `False`. RUC-committed and not opted out, On-Line RMR (pending: deployed Off-Line Non-Spin or DRRS).
54. `Inputs.resources.ramp_up` and `Inputs.resources.ramp_down`: number, MW/min, default blank. Normal Ramp Rates (also used by the HDL/LDL helper in 2.3).
55. `Inputs.deployments`: table `kind` (text: `load_rrs_ecrs`, `load_nonspin`, `ers`, `dc_tie_import`, `dc_tie_export`, `blt_import`, `blt_export`; pending: `tdsp_load_management`, `voltage_reduction`, `vecl`), `mw` (number, MW already ramped for this run); default none.
56. `Inputs.firm_load_shed`: bool, default `False`. EEA Level 3 load shed in effect.
57. `Rules.pricing_run`: `PricingRun(deployed_load_bid=(300.0, 700.0), relaxed_ramp_minutes=60, min_output_share_of_low=0.95, dc_tie_cap_mw=1250.0, ers_restore_hours=4.5)`; `None` switches the pricing run off (default `None`).
58. `opensced.price_adders(inputs, rules)`: returns the energy adder and one adder per reserve product (the positive difference between the pricing run and the binding run).

Pending rules (add when they take effect)
59. `Inputs.resources.provisional`: bool, default `False`; `Rules.pclr_shadow_share`: number, share, default `0.90`; `Rules.pclr_shift_factor`: number, default `-0.02`. Adjusted Bid Caps (NPRR1325).
60. `Product('DRRS', 'up', duration_hours=4.0)` with `Inputs.reserve_limits` rows for it; no new field once item 12 is done (NPRR1309).
61. `Inputs.resources.distribution_load_shed`: bool, default `False`. For the pending limits on distribution-connected resources (NPRR1128/1171/1213), written as a `Limit` with `where`.
62. `Inputs.reserve_priority`: table `product` (text), default none. Hours in which FFR procurement is prioritised (NPRR1128); allows offers down to −$0.01.

Not proposable from the text: "Regulation Services deployment is minimized over time" (S6 6.5.7.3(2)) has no formula.

### 2.3 DERIVED: add the helper that computes the result

63. `ercot.dispatch_limits(resources, minutes=5.0)`: fills `ramp_low` and `ramp_high` from `output`, `low`, `high`, `ramp_up`, `ramp_down`, `status`, `kind` by 6.5.7.2(2)-(7). `Rules.dispatch_minutes`: number, minutes, default `5.0`. Optional `Inputs.resources.forecast_high`: number, MW, default blank (the IRR 5-minute forecast used as HSL).
64. `ercot.reserve_limits(resources, capability, rules)`: `Inputs.reserve_capability`: table `resource` (text), `product` (text), `value` (number), `unit` (text: `'MW'` or `'MW/min'`); limit = value, or value × `Product.ramp_minutes`. Optional per-resource caps as columns of `Inputs.resources`: `emergency_ramp` (MW/min, ECRS ≤ `Product.ramp_minutes` × it), `pfr_limit` (MW; default `Rules.pfr_default_share` = `0.20` of the droop range), `ffr_rated` (MW, 15-minute rated capacity), `fast_response` (MW, proven 20-second capability), `quick_start_mw` (MW, proven ten-minute capability), `augmentation_offline` (MW); all default blank.
65. `ercot.proxy_energy_curves(resources, energy_offers, rules)`: builds every proxy of 6.5.7.3(4), (6), (8), (9) from `output_schedule`, `ruc_committed`, `rmr`, `category`, `max_consumption`, `low_consumption` and `Rules.offer_floor`, `offer_cap`, `voll`, `proxy_price_step`, `proxy_mw_step`, `irr_proxy_price`, `ruc_offer_floor`.
66. `ercot.proxy_reserve_offers(resources, reserve_offers, reserve_demand, reserve_requirements, rules)`: adds the linked proxy block of 6.5.7.3(5). `Rules.proxy_reserve_cap`: number, $/MW per hour, default `2000.0`; `Rules.proxy_reserve_plan_share`: number, share, default `0.95`; `Rules.proxy_reserve_step`: number, $/MW per hour, default `0.01`.
67. `ercot.demand_curves(requirements, voll, aordc, params)`: builds `Inputs.reserve_demand` by 4.4.12. `aordc`: table `mw`, `price` (the aggregate curve; its fitted μ* and σ* are posted elsewhere). `params`: `DemandCurveParams(mcl_mw=3000, reg_up_share=0.90, rrs_max_share=0.90, ecrs_max_share=0.30, ecrs_min_mw=40, non_spin_min_mw=10, reg_up_adder=4052, rrs_adder=2051, ecrs_adder=50, non_spin_adder=0, reg_up_min_price=250, rrs_min_price=100, floor_price=15)`.
68. `ercot.max_shadow_prices(constraints, rules)`: fills `max_shadow_price` from two new optional columns, `Inputs.constraints.kind` (text: `'base'`, `'contingency'`, `'irol'`; default `'contingency'`) and `Inputs.constraints.kv` (number, kV, default blank). `Rules.shadow_price_caps`: dict, $/MW, default `{'base': 5251, 'above_200kv': 4500, '100_to_200kv': 3500, 'below_100kv': 2800}`.
69. `ercot.irresolvable_cap(generic_cap, moc_c, shift_factor_c, floor=2000.0, net_margin=None, net_margin_limit=95000.0, lcap=2000.0)`: the cap of Attachment P 3.6.2. `ercot.irresolvable_triggered(history, hours_in_a_row=2, days_in_a_row=4, hours_in_30_days=20)`; `ercot.resource_c_d(shift_factors, min_shift_factor=0.02)`.
70. `ercot.irol_cap(shortage_price, floor_h, shift_factor_h)`: Attachment P 3.7, option B; `ercot.resource_h(shift_factors, seasonal_range, bias_mw, min_shift_factor=0.10)`.
71. `ercot.mitigate(energy_offers, reference_prices, mitigated_offer_caps, resources, rules)`: the step-2 floor and cap of 6.5.7.3(14)(b) (used by `Rules.two_step`).
72. `ercot.mitigated_offer_cap(heat_rates, fuel_prices, adders, om)`: the MOC formula of 4.4.9.4.1 for a user who has the cost data; inputs `gihr`, `ihr` (MMBtu/MWh), `fip`, `fop`, `wafp`, `fa` ($/MMBtu), `om` ($/MWh), fuel shares (percent), `solid_fuel_price` default `1.50`.
73. `ercot.demand(gtbd, clr_consumption=0.0)`: number, MW. GTBD less the CLR consumption (6.5.7.3(3)). The GTBD formula itself is not in the documents, so no helper is proposed for it.

---

## 3. Battery duration requirements: what is written and what is not

**The phrase.** Section 6 says SCED respects "SCED duration requirements" for ESRs and never gives a number under
that name. It appears at S6 6.3.2(6) L450 ("further capped by Ancillary Service SCED duration requirements and current
available State of Charge (SOC)"), 6.5.7.3(1) L1001 and L1006 ("feasible taking into account SCED duration
requirements for energy and Ancillary Services"), and in the capacity monitor 6.5.7.5(1) at L1410 (PFR), L1414 (FFR),
L1425 (ECRS), L1438 (Non-Spin), L1451 (Reg-Up and Reg-Down) and L1467-1470 (ESR Base Points). No file in the folder
defines the term.

**What Section 8 does write.** Sustain times as limits on the capability a QSE may qualify and telemeter. They apply to
every Resource, not only ESRs, and the text does not call them SCED duration requirements; that they are the same
numbers is inferred.

| Product | Written duration | Where | In `rulebooks.py` today |
|---|---|---|---|
| Reg-Up and Reg-Down | "can be sustained by the Resource for at least 30 minutes" | S8 8.1.1.2.1.1(5) L157; 8.1.1.3.1(2) L416 | RegUp 0.5 h (same); RegDown 0.25 h (differs: 30 minutes is written for both) |
| RRS, resource available for dispatch by SCED | "at least 30 minutes" | S8 8.1.1.2.1.2(10) L174; 8.1.1.3.2(4) L421 | RRS-PFR 0.25 h (differs) |
| RRS, all other resources except loads that are not CLRs providing FFR | "at least one hour" | same paragraphs | no separate product |
| FFR from a load that is not a CLR | "at least 15 minutes" | same paragraphs | RRS-FFR 0.25 h (same) |
| FFR in general | "sustaining that full response for at least 15 minutes" (S2 L480); "sustaining their response for up to 15 minutes" (S3 3.17.2(3)(b) L5301); award at most the "15-minute rated capacity" (S3 3.18(3)(d) L5353) | S2, S3 | RRS-FFR 0.25 h (same) |
| ECRS | "at least one hour" (S8 8.1.1.3.4(2) L429; 8.1.1.2.1.7(3) L376). But the product definition says "sustained at a specified level for two consecutive hours" (S3 3.17.4(1) L5324; S2 L441), and the ESR test speaks of "two-hour and/or four-hour capability" (S8 8.1.1.2(19) L139) | S8, S3, S2 | ECRS 1.0 h (matches Section 8; the two-hour wording conflicts) |
| Non-Spin | "at least four consecutive hours" (S8 8.1.1.3.3(2) L424; 8.1.1.2.1.3(8) L191 "four hours"; S3 3.17.3(1)(a)(ii) L5310) | S8, S3 | NonSpin 4.0 h (same) |
| Non-Spin, pending NPRR1309 | "at least two consecutive hours" (S8 L426, L193; S3 L5312) | pending | not in a rulebook yet |
| DRRS, pending NPRR1309 | "at least four consecutive hours" (S8 8.1.1.3.5(2) L435; 8.1.1.2.1.8(5) L394) | pending | no product yet |

**Related numbers that are not SCED durations.** The PRC formula counts ESR capacity "that can be sustained for 45
minutes per the State of Charge" (S6 6.5.7.5 PRC8 L1657). The competitiveness test divides (max SOC − min SOC) "by 15
minutes" (S3 3.19.1(3)(d)(ii)(B) L5379).

**Not written anywhere in the folder.**
- A table or sentence that names the SCED duration requirement of each product.
- The duration for the ESR Base Point (the package uses one 5-minute interval).
- The state-of-charge inequality itself: whether awards stack, whether Reg-Down and charging count against MaxSOC, and
  whether an up award met by charging less needs stored energy.
- Whether the Section 8 sustain times are the SCED values. The package's `duration_hours` remain "measured from
  disclosed battery awards" for that reason; the two that differ from Section 8 (RegDown, RRS-PFR at 0.25 h against a
  written 30 minutes) are the ones to re-test against the data.

---

## 4. Not read or not found

- **GTBD formula and coefficients** (the LFC calculation, "K factors"): not in Section 2 or Section 6. S2 L559 is a
  one-line definition; S6 6.5.7.6 L1748-1765 lists LFC inputs but not GTBD.
- **Definitions of HDL, LDL and VOLL** in Section 2: only the acronyms are listed (S2 L1702, L1737); the working
  definitions are in S6 6.5.7.1.12 and S4 4.4.11.
- **Formulas lost in the text conversion:** AttP 3.1-3.4 (L18-56), S4 4.4.12(6)(a)-(b) (L1292, L1310), the PRC sums in
  S6 6.5.7.5 (L1488-1680, partly garbled).
- **Outside the folder:** Nodal Operating Guide Section 8 Attachment N (droop-based RRS limits) and Section 2.3.1.1
  (minimum RRS); the Verifiable Cost Manual (MOC inputs); Protocols Section 4.2.1 (Ancillary Service Plan), 5.5.2
  (RUC), 6.5.9 (emergency operations), 3.8.7 (DC-Coupled Resources), 3.10.7.6 (Generic Transmission Constraints); the
  monthly minimum-PFR posting; the fitted μ* and σ* of the aggregate demand curve; the "procedure developed by ERCOT"
  for inclusive and exclusive offers (S4 4.4.7.2(1) L422).
- **Read by search, not line by line:** Section 3 outside 3.9.1, 3.16-3.20; Section 4 outside 4.4.7, 4.4.9, 4.4.11,
  4.4.12; Section 6 outside 6.3.2, 6.4.2-6.4.9, 6.5.5.2, 6.5.7; Section 8 outside 8.1.1.2-8.1.1.3. The earlier audit
  (`docs/ercot_conformance.md`) was reused for rule wording already checked there.
- **How DC Tie schedules enter SCED:** no rule found in the sections read.
