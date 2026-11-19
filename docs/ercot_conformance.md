# ERCOT conformance checklist: opensced against ERCOT's rule documents

## Changes since this audit

The table below is the audit as first written. These rows have since been closed or re-classified. Each was checked
on all 288 SCED runs of August 12, 2026. The last five rows come from a per-resource test: at ERCOT's own node prices and
reserve prices, is ERCOT's dispatch of each resource the best one the model's rows allow? It needs no shift factors.

| Rule | Source | Now | How |
|---|---|---|---|
| Proxy reserve offers | 6.5.7.3(5) | MATCHES, through ERCOT's data | The disclosure's sixth offer block is the proxy offer: its MW equal HSL for generation and HSL - LSL for storage on every row, and its prices are the demand-curve floor or the resource's own highest offer. All 378 on-line resources with reserve capability have one. The adapter has always read it |
| Proxy energy curves, all resource types | 6.5.7.3(4), (6) | MATCHES, through ERCOT's data | Every resource in the disclosure carries a SCED2 curve, proxy curves included. The adapter's own fallback is used only when a file has no curve |
| Units on an Output Schedule (ONOS) | 6.5.7.3(4)(a), 3.9.1(5)(b) | MATCHES | Now dispatchable, on ERCOT's proxy curve |
| Off-line quick-start units (OFFQS) | 3.9.1(5)(b)(i)(I) | MATCHES | Now dispatchable from zero on their offer curve |
| Reserves a status may carry | 3.9.1(5)(b) | MATCHES | OFF: Non-Spin only. OFFQS: ECRS and Non-Spin. ONSC: RRS and ECRS |
| Offer curves are sloped lines | 6.5.7.3; seen in ERCOT base points | MATCHES | ERCOT's base points land exactly where the sloped curve meets the node's price. The clearing is solved again with each curve cut finer around its resource's dispatch (three passes, to 0.005 MW), instead of 5 MW steps alone. Moves lambda by $1 to $8 on scarcity runs |
| Battery charge side: Reg-Down and efficiency | 8.1.1.3 (30 minutes); 3.7.1.3(1)(c) Round Trip Efficiency | MATCHES | efficiency x (0.5 h x Reg-Down + charging MW x 5 min) - discharging MW x 5 min <= room. 31,450 battery-runs on seven days: none breaks it, one in five sits exactly on it. Was 15 minutes with no efficiency, which let batteries carry up to twice the Reg-Down ERCOT allows. Efficiency is not published: read off the awards per battery, 0.85 otherwise |
| Off-line quick-start offers | measured, 3,093 unit-runs | MATCHES | ECRS and Non-Spin from the ONRES row only. The OFFNS row repeats the same MW; it was being added |
| Missing offer type (December 2025) | data | MATCHES | Read from the proxy block; no row wrong on 4.6 million rows of later days |
| Zero-filled offers (before February 3, 2026) | data | APPROXIMATE, cannot be exact | Totals restored exactly from the aggregate curve; which resource held them is inferred from a later day. On a later day with its blanks hidden this costs about $1 of mean lambda error |
| Three kinds of RRS | AS methodology; 3.16 | MATCHES | Three products on one demand curve, each with its own limit and offer price |
| Minimum RRS from primary frequency response | AS methodology (1,365 MW in 2025, 1,377 MW in 2026); 3.16(2)(c) | MATCHES, with a caveat | Two dated rulebooks. Coded as a cap on the other two kinds, which equals the minimum whenever the full requirement clears. ERCOT may set a higher monthly value, which is not yet read from the monthly posting |
| RRS from fast frequency response at most 450 MW | AS methodology | MATCHES | Rulebook limit |
| Relay loads plus fast frequency response at most 60% of RRS | 3.16(4) | MATCHES | Rulebook limit |
| Non-controllable loads at most 50% of ECRS | 3.16(7) | MATCHES | Rulebook limit |
| Non-Spin from non-controllable loads at most the requirement less the Most Severe Single Contingency | AS methodology | MATCHES | Rulebook limit; the 1,430.2 MW is measured, not printed |
| Controllable Load Resources | 6.5.7.3(3) | MATCHES | Dispatched on their bid curves; their consumption leaves demand |
| Regulation scaling of 5/7 | 6.5.7.3(12) | MATCHES | Was labelled reconstructed; it is written |
| Prices capped at the value of lost load | 6.5.7.3(14)(d) | MATCHES | Lambda and reserve prices capped at $5,000 after the solve; node prices above it pulled down |
| Shift factor cutoff 0.0001 | Attachment P 3.3 | MATCHES | Rulebook entry |
| Updated demand curves | 6.4.9.1.2(1) | MATCHES | The latest posting made before the run is used |
| Two-step clearing and offer mitigation | 6.5.7.3(14); 4.4.9.4.1; 4.4.9.4.2 | MATCHES for the mechanics | Step 1 on competitive constraints, floors and caps cut exactly where the curve crosses them. Floors reproduce ERCOT's step-2 curves on 99.2% of raised segments over all 288 runs. Which resources are capped, and their cost-based caps, are inputs |

Still open:

| Rule | Source | Why |
|---|---|---|
| Demand target (GTBD) | 6.5.7.3(3) | Not published. The sum of base points is used |
| Shift factors | 6.5.7.1.13(3)(c) | Posted hourly to the secure area only. NPRR1239 and NPRR1249 move them to the public website on implementation |
| A non-controllable load may not hold Non-Spin with RRS or ECRS | 4.4.7.2.1(6) | A yes/no choice per load, which a linear program cannot make. No load broke it in the August 12 example run |
| Reliability deployment price adder: ERS restoration and DC Tie adjustment | 6.5.7.3.1 | `pricing_run()` covers RUC/RMR relaxation and deployed loads; these two terms are not published per run |
| RUC-committed units' reserve offers at $250 | 6.5.7.3(5)(e) | Expected to be inside the proxy block already; not verified on a day with RUC commitments |
| Monthly minimum for primary frequency response above the floor | 3.16(4) | Needs ERCOT's monthly posting as an input |
| Battery duration requirements | Section 8 (not pulled) | Values are measured from data, not cited |
| The competitiveness test that decides which resources are capped | 3.19.4 | Not run. The set of capped resources is an input |
| Cost-based mitigated offer caps | 4.4.9.4.1 | Verifiable costs are confidential. The generic cap from the gas index price is computed |


Audit date: November 16, 2026. Read-only audit; no code was changed.

**Documents read** (plain-text copies; `L` numbers are line numbers in the `.txt` file):

| Short name | File | Version |
|---|---|---|
| S6 | `protocols_06-110626.txt` | Nodal Protocols Section 6, November 6, 2026 |
| S4 | `protocols_04-080126.txt` | Section 4, August 1, 2026 |
| S3 | `protocols_03-110626.txt` | Section 3, November 6, 2026 |
| S2 | `protocols_02-110626.txt` | Section 2 (definitions), November 6, 2026 |
| AttP | `protocols_22P-120525.txt` | Section 22 Attachment P, December 5, 2025 |
| ASM | `as_methodology_2026/ERCOT Methodologies for Determining Minimum AS Requirements 010126.txt` | effective January 1, 2026 |

**Replica code read:** `core/model.py`, `core/features/{balance,reserves,storage,network}.py`, `core/rules.py`,
`markets/ercot/rulebooks.py`, `markets/ercot/adapter.py`.

**Status values:** MATCHES, DIFFERS, MISSING, NOT CHECKABLE FROM TEXT (the rule points to something outside these
documents, or the text does not write the rule down), NOT APPLICABLE.

**Reading notes**
- "Grey box" means text for a rule change not yet in effect ("upon system implementation"). Where a paragraph appears
  twice, the row says so and names the version that reads as current.
- "via data" means the replica does not compute the rule; it reads ERCOT's own published result (HDL, the SCED2 curve,
  the maximum shadow price, the demand curves). That is conformance only as long as the input is ERCOT's.
- "inferred" marks a judgement of mine, not something the text states.
- S6 6.5.7.3 has two paragraphs numbered (9) (L1259 and L1265) and two numbered (14) (L1277 grey box, L1286 current).

---

## 1. Rule-by-rule table

### A. Objective and run structure

| # | Rule | Source | What the rule says | Replica today | Status |
|---|---|---|---|---|---|
| 1 | Objective | S6 6.5.7.3(1) L1001; AttP 4.1 L143 | "maximizing bid-based revenues minus offer-based costs", subject to power balance, ASDCs and network constraints. AttP: objective is the sum of four parts: dispatch cost, AS cost, power balance penalty, network penalty. | One LP: energy offer cost + reserve offer cost − demand curve value + balance penalties + constraint violation penalties (`model.py`). | MATCHES |
| 2 | Run interval | S6 6.5.7.3(1) L1001 | "approximately every five minutes, or more frequently if necessary". | One run per SCED timestamp; `interval_hours = 5/60`. | MATCHES |
| 3 | Two-step SCED, step 1 (Reference LMPs) | S6 6.5.7.3(14)(a) L1287 (current); L1289 grey box NPRR1188 only renames the bid | Step 1 runs SCED with only Competitive Constraints plus power balance and AS constraints, on unmitigated curves, to get Reference LMPs. | Not run. One LP per interval. | MISSING |
| 4 | Step 2 offer floor and cap (mitigation) | S6 6.5.7.3(14)(b)(i)-(ii) L1291-1292; floors S4 4.4.9.4.2 L868-888; test S3 3.19.4(7) L5446-5451, thresholds S3 3.19.1(6) L5388-5411 | Every curve bounded below at "the lesser of the Reference LMP ... or the appropriate Mitigated Offer Floor". Mitigated curves capped at the greater of Reference LMP + (a variable "not to exceed 0.01" × MOC at LSL) or the MOC. Floors: Nuclear/Hydro −$250, Coal/CC/Gas steam/CT −$20, QF −$50, Wind −$100, PV −$50, ESR −$250, Other −$50. | Uses the disclosed SCED2 curve, taken to be the step-2 curve. No floor or cap computed. | MATCHES (via data; inferred that SCED2 is the step-2 curve) |
| 5 | No mitigation of CLR bids | S6 6.5.7.3(14)(b)(iii) L1293 (current); L1295 grey box NPRR1188 | "There is no mitigation of RTM Energy Bids." | Bid curves used as disclosed. | MATCHES |
| 6 | Price caps after the solve | S6 6.5.7.3(14)(d) L1301 | System Lambda and MCPCs from step 2 "capped at the effective VOLL". A bus LMP above VOLL is set to the greater of VOLL or (LMP − (System Lambda − VOLL)). ERCOT posts capped and uncapped values. | Returns raw duals. Lambda can reach $11,052.01; an MCPC can exceed $5,000. Scoring reads `systemLambda` first, `cappedMCPC` first. | MISSING |
| 7 | Pricing run: Real-Time Reliability Deployment Price Adders | S6 6.5.7.3.1 L1305-1388 | When reliability deployments exist, SCED is re-run: ONRUC/RMR units get LSL = LDL = 0, AS offers removed, step-1 offer at the power balance penalty price from 0 to HSL (L1337-1339); others get LDL/HDL widened to output ∓ 60 minutes × ramp rate (L1345-1346); deployed non-CLR Load Resource MW added to GTBD with a bid curve from "$300/MWh for the first MW" to "$700/MWh for the last MW" (L1361); ERS restoration RHours = 4.5 (L1371); DC Tie adjustment capped at 1,250 MW (L1311). Energy adder = positive difference of the two System Lambdas (L1387); AS adder likewise per product (L1388). EEA3 load shed: adder = VOLL − step-2 lambda. Several sub-paragraphs have grey-box versions (NPRR904, 1091, 1188, 1238, 1309). | `markets/ercot/pricing.py`: `pricing_run()` relaxes ONRUC and RMR units (opt-outs read off ERCOT's relaxed MW), caps a mitigated RUC unit at its step-1 reference price, adds deployed loads and returns the adder. Against ERCOT's published adder on 22 days of 2026 (6,432 runs): mean absolute error $0.16, 96% of runs within $1. ERS restoration and the DC Tie adjustment are not modelled. | PARTIAL |
| 8 | Non-binding look-ahead projection | S6 6.5.7.3(15) L1302 | Indicative Base Points, awards and prices "for at least 15 minutes into the future". | Not modelled; not part of binding clearing. | NOT APPLICABLE |
| 9 | Regulation deployment minimised over time | S6 6.5.7.3(2) L1007 | SCED "must monitor cumulative deployment of Regulation Services and ensure that Regulation Services deployment is minimized over time". No formula. | Nothing. | NOT CHECKABLE FROM TEXT |

### B. Power balance and its penalties

| # | Rule | Source | What the rule says | Replica today | Status |
|---|---|---|---|---|---|
| 10 | Demand target (GTBD) | S2 L558-559; S6 6.5.7.3(3) L1008 | GTBD: "A dynamically calculated system total generation MW requirement ... calculated every four seconds", determined by LFC. No formula. | Demand = sum of ERCOT's published Base Points (`adapter.inputs`: `res['output'].sum()`). Equal to GTBD only when ERCOT's own run had no shortfall or surplus (inferred). | DIFFERS |
| 11 | CLR consumption netted from GTBD | S6 6.5.7.3(3) L1008 | ERCOT "shall subtract the sum of the telemetered net real power consumption from all CLRs available to SCED". | CLRs are negative output inside the base-point sum. | MATCHES |
| 12 | Under-generation penalty | AttP 4.1 L144; values S4 4.4.11 L1254-1259 | "effective Value of Lost Load (VOLL) plus the effective Real-Time System-Wide Offer Cap (RTSWCAP) plus $4,052.01/MWh". Table: HCAP-DAM 5,000; HCAP-RTM 2,000. VOLL = HCAP for DAM (L1237). | `shortage_price = 5000 + 2000 + 4052.01`, a fixed number. | MATCHES (at the table's current values) |
| 13 | Over-generation penalty | AttP 4.1 L144 | "The SCED over-generation Power Balance Penalty Price is -$250/MWh." | `surplus_price = -250`. | MATCHES |
| 14 | VOLL changes during the year | S4 4.4.11(1)(a)(i) L1238; (ii) L1241; 4.4.11.1(3) L1276-1280; table L1251-1265 | VOLL for the ASDCs drops to ECAP (2,000) under the Emergency Pricing Program (lambda + adder at or above HCAP-DAM for 12 hours in a rolling 24), or to LCAP (2,000) once Peaker Net Margin passes 315,000 $/MW-year. Because the penalty in row 12 uses the *effective* VOLL, it moves too (inferred). | No switch; the penalty and curves are fixed per rulebook date. Curves follow automatically if the published ASDC file is used. | MISSING |

### C. Energy offers, bids and proxy curves

| # | Rule | Source | What the rule says | Replica today | Status |
|---|---|---|---|---|---|
| 15 | Energy Offer Curve shape | S4 4.4.9.3 L715; 4.4.9.3.1 L727, L730, L733 | Monotonically non-decreasing, "no more than ten price/quantity pairs"; within −$250.00 and RTSWCAP; bounded in SCED by telemetered LSL and HSL; in Real-Time "always considered to be inclusive with Ancillary Service Offers". | Curve clipped to max(LDL, LSL)..min(HDL, HSL); energy and reserves share one headroom. Reads up to 35 SCED2 points. | MATCHES |
| 16 | How a sloped curve is priced inside the solver | none found | Not stated. | Cuts curves into blocks of at most 5 MW priced at the midpoint (`block_mw`), a modelling choice. | NOT CHECKABLE FROM TEXT |
| 17 | Proxy curve: non-IRR on an Output Schedule | S6 6.5.7.3(4)(a) L1010-1022 | LSL at −$250.00; Output Schedule MW at −$249.99; Output Schedule + 1 MW at RTSWCAP − $0.01; HSL at RTSWCAP. | Status `ONOS` is not in the adapter's dispatchable set, so these units are held at their Base Point and get no reserve limits. No such proxy is built. | DIFFERS |
| 18 | Proxy curve: extending a partial curve | S6 6.5.7.3(4)(b) L1023-1034; IRR (4)(c)(ii) L1045-1055 | Above the top point: to HSL at the top point's price. Below the bottom point: "1 MW below lowest MW" at −$249.99, LSL at −$250.00. | Curve held flat beyond both ends (`np.interp`). The upward side matches; the downward side uses the lowest offer price, not −$249.99/−$250. No effect if SCED2 already carries the extension (inferred). | DIFFERS |
| 19 | Proxy curve: IRR with no curve | S6 6.5.7.3(4)(c)(i) L1036-1044 | LSL at −$250.00; HSL − 1 MW at −$249.99; HSL at $1,500. | Same three prices (`PROXY`), but anchored on max(LDL, LSL)..min(HDL, HSL) and applied to every resource type that lacks a curve, not only IRRs. | DIFFERS |
| 20 | RUC-committed energy curves | S6 6.5.7.3(4)(d)(i)-(ii) L1056-1072; combined-cycle cases L1082-1105 | No curve: $250 from zero to HSL. With a curve: every point "Greater of $250 or" the submitted price. | No RUC rule. `ONRUC` units use the SCED2 curve (floor inherited via data, inferred) or, with no curve, the IRR proxy of row 19. | DIFFERS |
| 21 | RUC curves at $4,500 (AAN, switchable units) | S6 6.5.7.3(4)(d) grey boxes NPRR930 L1073-1080, NPRR1019 L1107-1147 | "$4,500 or the effective Value of Lost Load (VOLL), whichever is less". Grey box: not yet in effect. | Not modelled. | NOT APPLICABLE |
| 22 | ESR Energy Bid/Offer Curve | S4 4.4.9.7.1 L970, L973-974 | One curve; negative MW is charging, positive is discharging; bounded by −$250.00 and RTSWCAP; inclusive of AS offers. | One curve across zero; a knot is kept at 0 MW. | MATCHES |
| 23 | Proxy for a partial ESR curve | S6 6.5.7.3(6)(a) L1198-1236 | Above the top point: RTSWCAP for MW ≥ 0 (the top point's price for the part below zero). Below the bottom point: −$250.00 for MW ≤ 0 (the bottom point's price for the part above zero). | Flat at the end prices on both sides. | DIFFERS |
| 24 | ESR with no curve, or on an Output Schedule | S6 6.5.7.3(6)(b) L1237, (c) L1238; S4 4.4.9.7(7) L965 | No curve: "-$250/MWh for the MW portion ... less than zero MW" and RTSWCAP above zero. Output Schedule: −$250 from LSL to the schedule, RTSWCAP from the schedule to HSL. | No curve: the IRR proxy of row 19 ($1,500 top, not RTSWCAP). `ONOS` ESRs are held at Base Point. | DIFFERS |
| 25 | CLR bid: partial coverage | S6 6.5.7.3(8) L1240-1248 (current); L1250-1258 grey box NPRR1188 renames the bid | LPC up to (MPC − maximum bid MW) at the "Price associated with the lowest MW" in the bid; MPC at the lowest price on the curve. Bids monotonically non-increasing (L1265). | Bid curve mirrored to negative output and held flat beyond its ends. | MATCHES (inferred from the flat extension) |
| 26 | CLR with no bid | S6 6.5.7.3(9) L1259-1263 | Proxy bid "LPC to MPC" at "Effective Value of Lost Load (VOLL)". | A CLR with no bid curve is held at its Base Point (`disp` needs `has_bid`). | DIFFERS |
| 27 | CLR status OUTL | S6 6.5.7.3(10) L1268 (current); L1270 grey box NPRR1188 adds ONHOLD | OUTL: "not considered as dispatchable capacity by SCED". | Dispatchable only when `telResStatus == ONL`. | MATCHES |
| 28 | PCLR bid capping | S6 6.5.7.3(1) grey box L1003-1005; (14)(b)(iv) grey box L1297 | Dynamic capping of Provisional CLR bid curves. Grey box (NPRR1188/1325): not yet in effect. | Not modelled. | NOT APPLICABLE |

### D. Resource limits and status

| # | Rule | Source | What the rule says | Replica today | Status |
|---|---|---|---|---|---|
| 29 | HDL / LDL, generation | S6 6.5.7.2(2)-(3) L905-927; 6.5.7.1.12(1) L838-839 | HDL = Min (POWERTELEM + (NORMRAMPUP * 5), HSLTELEM); SHUTDOWN: HDL = POWERTELEM – (NORMRAMPDN * 5). LDL = Max (POWERTELEM - (NORMRAMPDN * 5), LSLTELEM); STARTUP: LDL = POWERTELEM + (NORMRAMPUP * 5). | Reads ERCOT's disclosed HDL, LDL, HSL, LSL. | MATCHES (via data) |
| 30 | HDL / LDL, ESR | S6 6.5.7.2(4)-(5) L940-964 | ONHOLD: HDL = LDL = 0. ONTEST: Max (Min (POWERTELEM, HSLTELEM), LSLTELEM). Otherwise the generation formulas. | Reads disclosed values. | MATCHES (via data) |
| 31 | HDL / LDL, CLR | S6 6.5.7.2(6)-(7) L975-988 | HDL = Min (POWERTELEM + (NORMRAMPDN * 5), HSLTELEM); LDL = Max (POWERTELEM - (NORMRAMPUP * 5), LSLTELEM). | Reads disclosed values; falls back to consumption when blank. | MATCHES (via data) |
| 32 | Base Point inside HDL and LDL | S6 6.5.7.4(1) L1390 | "The Base Point set by SCED must observe a Resource's HDL and LDL." | Dispatch range is LDL..HDL (`dispatch_limits='ramp'`). ERCOT's HDL sits up to 0.05 MW above HSL on about 200 resources per run and the base point follows it. | MATCHES |
| 33 | HASL / LASL | none | The terms do not appear in S2, S3, S4 or S6 (0 matches). They are no longer part of the rules read here. | Not used. | NOT APPLICABLE |
| 34 | Which statuses SCED may move | S3 3.9.1(5)(b)(i)-(iv) L3378-3416 | Generation: ONRUC, ON, ONOS, ONTEST, ONEMR, ONOPTOUT, SHUTDOWN, STARTUP, OFFQS, ONSC, ONHOLD. ONSC and ONHOLD: "Base Points will be set equal to the telemetered net real power". OFFQS: "Off-Line but available for SCED deployment". | Dispatchable set: ON, ONREG, ONRUC, ONEMR, ONDSR, ONRR, ONOPTOUT, FRRSUP. `ONOS` is missing; ONREG, ONDSR, ONRR, FRRSUP are not in the current list. OFFQS is held at its Base Point. | DIFFERS |
| 35 | Operator overrides of HDL / LDL | S6 6.5.7.1.10(3)(g) L818; 6.5.7.1.13(8)-(10) L898-900 | ERCOT may re-dispatch "by over-riding HDLs and LDLs". Operator action; no formula. | Uses disclosed HDL/LDL, taken to include overrides (inferred). | NOT CHECKABLE FROM TEXT |

### E. Reserve awards per resource

| # | Rule | Source | What the rule says | Replica today | Status |
|---|---|---|---|---|---|
| 36 | Reg-Up against HDL | S6 6.5.7.3(12)(a) L1273 | "A scaling factor of 5/7" so that Base Point + 5/7 × Reg-Up award "does not exceed HDL". | `regulation_share = 5/7`; row p + 5/7·RegUp ≤ HDL. | MATCHES |
| 37 | Reg-Down against LDL | S6 6.5.7.3(12)(b) L1274 | Base Point − 5/7 × Reg-Down award "does not go below LDL". | Row p − 5/7·RegDown ≥ LDL. | MATCHES |
| 38 | CLR regulation direction | S6 6.5.7.1.12(2)(c)-(d) L843-844 | For a CLR, HDL limits Reg-Down and LDL limits Reg-Up. | CLR limits are sign-flipped (`ramp_low = -HDL`, `ramp_high = -LDL`), giving the same result. | MATCHES |
| 39 | Awards within telemetered capability | S6 6.5.7.3(12) L1272; telemetry S6 6.5.5.2 L701-702, L717-718 | Awards "aligned with a Resource's qualifications and telemetered Ancillary Service capabilities". RRS capability is telemetered in MW; other products as "a blended ramp rate (in MW/min)". | RRS limits = capability MW; others = capability × minutes. Zero where there is no capability. | MATCHES |
| 40 | ECRS limit, On-Line generation and ESR | S3 3.18(4)(a) L5355 | "less than or equal to ten times the Emergency Ramp Rate". | 10 × `ASCapECRS`. Same factor of ten; that the disclosed rate is the Emergency Ramp Rate is inferred. | MATCHES (inferred) |
| 41 | Minutes for Regulation (5) and Non-Spin (30) | S6 6.5.7.1.12(1)(c) L838 ("for the next five minutes"); S3 3.17.3(1)(a)(i) L5309 ("within 30 minutes") | The text gives the time windows but no "award ≤ rate × minutes" rule for these two products. | 5 × rate for Reg-Up/Reg-Down, 30 × rate for Non-Spin (reconstructed from data). | NOT CHECKABLE FROM TEXT |
| 42 | Total awards within the operating range | S3 3.18(1) L5345 | HSL "must be greater than or equal to the Low Sustained Limit (LSL) and the sum of the Resource-specific awards" for RRS, ECRS, Reg-Up, Reg-Down and Non-Spin. | Rows p + up awards ≤ HSL and p − down awards ≥ LSL together imply it. | MATCHES |
| 43 | Energy plus awards against HSL | S6 6.5.7.3(14)(c) grey box NPRR1309 L1280 only | Grey box: HSL ≥ "the sum of the Resource-specific awards ... for energy, RRS, ECRS, Reg-Up, Reg-Down, Non-Spin, and DRRS" (Reg-Down is in the sum as written). The current text has no energy-inclusive row. | p + RegUp + RRS + ECRS + NonSpin ≤ HSL; p − RegDown ≥ LSL (reconstructed from data). | NOT CHECKABLE FROM TEXT |
| 44 | Off-Line units | S3 3.18(2) L5346; S6 6.5.7.3(14)(d) grey box L1281 | "the amount of Non-Spin awarded must be less than or equal to the HSL for Off-Line Generation Resources". Grey box: ECRS + Non-Spin + DRRS ≤ HSL. | A held unit's up awards ≤ max(HSL − output, 0). | MATCHES |
| 45 | Product eligibility by status | S3 3.9.1(5)(b) L3385-3396 | SHUTDOWN and STARTUP: "not eligible for an Ancillary Service award". OFFQS: ECRS and Non-Spin. ONSC: RRS and ECRS. OFF: Non-Spin. ONHOLD: none. | OFF and OFFQS may take Non-Spin and ECRS (`OFFNS` offers); ONSC may take any `ONRES` product. No per-status product list; relies on capability being zero. STARTUP/SHUTDOWN/ONHOLD correctly get nothing. | DIFFERS |
| 46 | Startup exception | S6 6.4.9.1.1(4)-(5) L563-564 | An Off-Line unit starting after a manual Non-Spin deployment stays eligible for Non-Spin; a QSGR in startup stays eligible for ECRS and Non-Spin. Eligible capacity = "telemetered HSL of the Resource minus its Base Point". | STARTUP units carry no reserves. | MISSING |
| 47 | RRS-PFR limit per resource | S3 3.18(3)(a) L5350 | Set by verified droop under Nodal Operating Guide Section 8, Attachment N; default "20% of its Maximum Droop Response Range (MDRR)". | Uses disclosed `ASCapRRSPFR`. | NOT CHECKABLE FROM TEXT |
| 48 | RRS-FFR limit per resource | S3 3.18(3)(d) L5353; S2 L480 | "less than or equal to its 15-minute rated capacity"; FFR must sustain "for at least 15 minutes". | Disclosed `ASCapRRSFFR`; battery duration for RRS = 0.25 h. | MATCHES |
| 49 | Synchronous condenser limits | S3 3.18(3)(b) L5351, (4)(c) L5357 | RRS or ECRS "up to the Generation Resource's proven 20-second response capability". | Disclosed capability. | NOT CHECKABLE FROM TEXT |
| 50 | QSGR ECRS limit | S3 3.18(4)(b) L5356 | "less than or equal to its proven ten-minute capability" (Section 8.1.1.2, not in these documents). | 10 × `ASCapECRS`. | NOT CHECKABLE FROM TEXT |
| 51 | Operator reduction of AS capability | S6 6.4.9.1.1(6) L565 | ERCOT "may manually reduce the amount of Ancillary Service eligible to be awarded" for transmission reasons. | Nothing. | NOT CHECKABLE FROM TEXT |
| 52 | Awards ignore AS under deployment | S6 6.4.9.1.1(1) L560 | Awards are based on capability and ASDCs "regardless of the quantity of Ancillary Service under deployment". | Deployment is not an input. | MATCHES |

### F. Reserve offers

| # | Rule | Source | What the rule says | Replica today | Status |
|---|---|---|---|---|---|
| 53 | Linked offers | S4 4.4.7.2.1(1)(c) L448; S6 6.5.7.3(5)(a) L1150 | An offer names the MW and "any other Ancillary Service offered from this same capacity"; the proxy offer is "a linked Ancillary Service Offer across all Ancillary Service products". | Offer blocks: one MW of a block serves one product (`offer_rows`). | MATCHES |
| 54 | AS offer price bounds | S4 4.4.7.2.1(3) L457 (current); L459 grey box NPRR1128 allows −$0.01 for FFR in some hours | "No Ancillary Service Offer price may be less than $0 per MW"; not above RTSWCAP after 1430 Day-Ahead. | Prices floored at 0. No upper check. | MATCHES |
| 55 | Block indicators in Real-Time | S4 4.4.7.2.1(1)(g) L453-454 | Fixed and variable block indicators "will be ignored for awarding of Ancillary Services in the Real-Time Market". | All awards continuous. | MATCHES |
| 56 | Proxy AS offer: quantity and price | S6 6.5.7.3(5)(a)-(b) L1149-1166 | ERCOT offers all qualified capacity: MW = telemetered HSL (generation), HSL − LSL (ESR), MPC (Load Resource). Price: Reg-Up/RRS = max of the floor, own highest Reg-Up/RRS, ECRS and Non-Spin prices; ECRS = max of the floor, own ECRS and Non-Spin; Non-Spin and Reg-Down = max of the floor and own highest. | When offers are given, a resource with no submitted offer for a product gets a limit of zero, and awards stop at the submitted block MW. No proxy offer. | MISSING |
| 57 | Proxy AS offer price floor | S6 6.5.7.3(5)(c) L1171-1186; (d) L1191 | Per product: "the lesser of" $2,000 per MW per hour or the ASDC price at "95% of the Ancillary Service Plan", "minus $0.01". Floors may differ for On-Line/Off-Line and by sub-type. | Not computed. | MISSING |
| 58 | RUC-committed AS offers | S6 6.5.7.3(5)(e) L1192-1196 | No offer: "$250 per MWh for the full operating range of the Resource up to its telemetered HSL". With an offer: max of own highest price or $250. | `ONRUC` units use submitted offers unchanged. | MISSING |
| 59 | Latest offers used | S6 6.4.9.1(2) L558 | "SCED shall use the latest updated Ancillary Service Offers available to it". | Reads the per-run offer disclosure. | MATCHES (via data) |
| 60 | Self-provision by relay-controlled loads | S6 6.4.9.1.1(3) L562; telemetry L695 | Load Resources on high-set under-frequency relays "may self-provide" RRS and ECRS, limited by the QSE's DAM awards and trades. How SCED clears that MW is not stated. | Self-arranged MW (RRS-UFR, RRS-FFR, ECRS) entered as $0 offer blocks. | NOT CHECKABLE FROM TEXT |
| 61 | Non-controllable load: Non-Spin not with RRS or ECRS | S4 4.4.7.2.1(6) L462 | Such a load "will not be awarded Non-Spin and RRS or Non-Spin and ECRS on the same Load Resource simultaneously in Real-Time". | No exclusion; a load may hold all three. | MISSING |

### G. Demand curves and system-wide reserve rules

| # | Rule | Source | What the rule says | Replica today | Status |
|---|---|---|---|---|---|
| 62 | Products with a demand curve | S4 4.4.12(1) L1282 (current); L1284 grey box adds DRRS | Reg-Up, Reg-Down, RRS, ECRS, Non-Spin. | Five curves; RRS is served by three sub-type products. | MATCHES |
| 63 | Reg-Down curve | S4 4.4.12(4) L1287 | "a constant value equal to VOLL for the full range of the Ancillary Service Plan for Reg-Down". | Reads the published curve. | MATCHES (via data) |
| 64 | Aggregate curve (AORDC) fit | S4 4.4.12(6) L1291-1321 | Built from June 1, 2014 to August 31, 2025 intervals with reserves under 10,000 MW; points at 1 MW steps for reserve level ≥ 3,000 MW and price > $0.01/MWh. The formulas at L1292 and L1310 are missing or garbled in the text file. | Not built; the published curves are read. | NOT APPLICABLE |
| 65 | Split up to the Minimum Contingency Level | S4 4.4.12(7)(a) L1323-1416 | MCL "set at 3,000 MW"; RUPCT 90, RRSPCTMAX 90, ECRSPCTMAX 30, ECRSMWMIN 40, NSMWMIN 10. Max demand prices: Reg-Up VOLL + 4,052; RRS VOLL + 2,051; ECRS VOLL + 50; Non-Spin VOLL. | Not built; read from the published curves. | NOT APPLICABLE |
| 66 | Split beyond the MCL, and the floor | S4 4.4.12(7)(b) L1417-1431 (current); L1433-1458 grey box NPRR1309; (9) L1463 | Reg-Up down to 250; RRS down to 100; then ECRS and Non-Spin alternately; floor "$15 per MW per hour" over the AS Plan quantity. | Not built; read from the published curves. | NOT APPLICABLE |
| 67 | Curve between points | S4 4.4.12(8) L1462 | "Each ASDC will be represented by a linear approximation to the corresponding part of the AORDC." | Each segment between two published points is priced at their mean (`segments`). | MATCHES (inferred) |
| 68 | Curves re-posted during the day | S6 6.4.9.1.2(1) L569 | If the AS Plan changes, ERCOT will "update and post ASDCs for each impacted Ancillary Service product". | Takes the first posting for the hour (`postedDatetime.min()`), so an updated curve is ignored. | DIFFERS |
| 69 | Reserve price | S6 6.5.7.3(14)(b) L1290; 6.4.9.1.1(8) L567 | Step 2 produces "Real-Time MCPCs". The equation is not written. | MCPC = dual of the product's demand row. | MATCHES (inferred) |
| 70 | Minimum RRS from Primary Frequency Response | ASM L26; S3 3.16(2)(c) L5278; 3.16(4) L5282 | ASM: "shall not be less than 1,377 MWs". Protocols: "shall not be less than 1,150 MW"; posted monthly. | 1,377 MW from January 1, 2026 (1,365 MW before, measured). Written as a ceiling on FFR + UFR of (demand curve total MW − 1,377), not as a floor on PFR. The two differ when less RRS clears than the curve's full width. | DIFFERS (number matches; form differs) |
| 71 | Maximum RRS from FFR | ASM L26; S3 3.16(2)(b) L5275 | "limited to 450 MW". | No limit on RRS-FFR. | MISSING |
| 72 | Relay loads plus FFR share of RRS | S3 3.16(4) L5282 (current); L5284 grey box NPRR1128 keeps the 60%; ASM L26 | "shall be limited to 60% of the total ERCOT RRS requirement". The ASM words it as "DAM will limit". | No limit. | MISSING |
| 73 | Non-controllable loads' share of ECRS | S3 3.16(7) L5287 | "limited to 50% of the total ERCOT ECRS requirement". | No limit. | MISSING |
| 74 | Minimum Non-Spin from SCED-dispatchable Resources | ASM L41 | "shall not be less than lower of ERCOT's Most Severe Single Contingency (MSSC) value and the Non-Spin requirement for that hour". | Rulebook limit `Non-Spin from loads`: non-controllable loads together hold at most the hour's Non-Spin requirement (AS Plan, NP4-33-CD) less 1,430.2 MW. The methodology does not print the MSSC; 1,430.2 is measured (72 runs on four days sit exactly on it, none of 6,335 runs on 22 days is above it). Needs the `dam_as_plan` file. | MATCHES (MSSC measured) |
| 75 | Substitution or cascading between products | none found | No sentence in S6 6.5.7.3, S4 4.4.12 or S3 3.16-3.18 lets one product's MW count toward another's curve. Each product has its own curve. | No substitution. Only the three RRS sub-types share a curve. | NOT CHECKABLE FROM TEXT |
| 76 | DRRS | S6 6.5.7.3(14)-(15) grey box L1276-1285; S3 3.17.5 grey box L5339-5343 | New product under NPRR1309. Grey box: not yet in effect. | Not modelled. | NOT APPLICABLE |

### H. Batteries (ESRs)

| # | Rule | Source | What the rule says | Replica today | Status |
|---|---|---|---|---|---|
| 77 | State of charge feasibility | S6 6.5.7.3(1) L1001 (current; L1003-1006 grey box keeps the sentence) | Base Points and awards must be "feasible taking into account SCED duration requirements for energy and Ancillary Services" and must not violate MinSOC and MaxSOC. No equation. | Discharge-side and charge-side rows (`storage.py`); up awards covered by charging less need no stored energy. | MATCHES (form inferred) |
| 78 | Duration per product | S6 6.5.7.5(1) L1410, L1414, L1425, L1438, L1451; 6.3.2(6) L450 | The text refers to "SCED duration requirements" of PFR, FFR, ECRS, Non-Spin and Regulation but gives no numbers. | Reg-Up 0.5 h, Reg-Down 0.25 h, RRS 0.25 h, ECRS 1 h, Non-Spin 4 h (measured). | NOT CHECKABLE FROM TEXT |
| 79 | Duration for the Base Point itself | S6 6.5.7.5(1)(l)(viii)-(xi) L1467-1470 | "SCED duration requirements for ESR Base Points". No number. | 5 minutes (`interval_hours`). | NOT CHECKABLE FROM TEXT |
| 80 | Product definitions that carry a duration | S3 3.17.4(1) L5324; 3.17.3(1)(a)(ii) L5310 (current), L5312 grey box NPRR1309 | ECRS: capacity "sustained at a specified level for two consecutive hours". Non-Spin: "at least four consecutive hours" (grey box: two). These define the products; the text does not say they are the SCED durations. | ECRS 1 h; Non-Spin 4 h. | DIFFERS (ECRS, if the definition is the SCED duration) |
| 81 | ESR availability | S6 6.5.7.3(17) L1304; S4 4.4.9.7(3) L957 | An ESR "may withdraw energy ... only when dispatched by SCED"; unavailable when status is OUT. | Charging is the negative part of dispatch; non-dispatchable statuses are held. | MATCHES |

### I. Load Resources

| # | Rule | Source | What the rule says | Replica today | Status |
|---|---|---|---|---|---|
| 82 | CLR Base Point | S6 6.5.7.4(1)(b) L1392 | Base Point is "MW consumption for CLR". | Negative output on the bid curve. | MATCHES |
| 83 | Non-controllable load reserve room | S6 6.5.7.5(1)(l)(vii) L1466 | Capacity monitor counts "the Net Power Consumption minus the Low Power Consumption from Load Resources". No explicit SCED award rule. | Up awards ≤ consumption − low power consumption. | MATCHES (inferred) |
| 84 | Where a CLR bid sits on the network | S6 6.5.7.3(14)(b)(iii) L1293 (current); L1295 grey box NPRR1188 limits this to aggregate loads | A CLR bid is "distributed across all nodes in the Load Zone in which the CLR is located". | Uses the caller's `resource_nodes` (shares across nodes are supported). | NOT CHECKABLE FROM TEXT |

### J. Network

| # | Rule | Source | What the rule says | Replica today | Status |
|---|---|---|---|---|---|
| 85 | Which constraints are active | S6 6.5.7.1.11(1) L828 | Only constraints ERCOT has verified are activated in SCED. | Enforces the constraints in ERCOT's binding-constraint report that have shift factors. Active constraints that did not bind are not in that report. | MATCHES (via data) |
| 86 | Shadow price capped per constraint | S6 6.5.7.1.11(2) L829; AttP L13 | Cost to relieve one more MW "is limited to the maximum Shadow Price"; at the cap "the constraint will be violated". | Violation variable priced at the published `maxShadowPrice`. | MATCHES |
| 87 | Generic caps | AttP 3.5 L60-65 | Base Case/Voltage $5,251/MW; N-1 above 200 kV $4,500/MW; 100 kV to 200 kV $3,500/MW; below 100 kV $2,800/MW. | Reads the published cap per constraint; $5,251 only as a fallback for a blank. | MATCHES (via data) |
| 88 | Irresolvable constraints | AttP 3.6.1 L100-107; 3.6.2 L108-115; 3.6.3 L126-131 | Trigger: unresolved "more than two consecutive hours on more than 4 consecutive Operating Days" or "more than a total of 20 hours in a rolling thirty-day period". Cap = minimum of the generic cap and the maximum of (Resource C's largest MOC ÷ its shift factor) or $2000 per MW. After net margin above $95,000/MW: minimum of $2,000/MWh or the maximum of that ratio and LCAP. Shift factors under 0.02 ignored. | Not computed; arrives in the published cap. | NOT CHECKABLE FROM TEXT |
| 89 | IROL cap | AttP 3.7 L132-139 | Base Case generic cap, or (power balance penalty price − mitigated offer floor of Resource H) ÷ Resource H's shift factor. | Not computed; arrives in the published cap. | NOT CHECKABLE FROM TEXT |
| 90 | Shift factor cutoff | AttP 3.3 L50 | "default value of Shift Factor cut off is 0.0001". | Drops only |SF| ≤ 1e-12. | DIFFERS |
| 91 | Node price | AttP 3.1 L18-24 | LMP = System Lambda less the sum of shift factor × shadow price (the formula image is missing from the text file; the terms are listed). | Same (documented in `network.py`). | MATCHES |
| 92 | Form of the constraint row | none found | The Protocols do not write the row. | published flow + Σ SF × (MW − Base Point) ≤ limit + violation (reconstructed). | NOT CHECKABLE FROM TEXT |
| 93 | Shift factor reference | S3 3.19.1(5) L5381-5383 | Computed "relative to the distributed load reference Bus"; contingency constraints with the contingency removed. | Caller supplies shift factors. | NOT CHECKABLE FROM TEXT |

---

## 2. Gaps most likely to change prices

Ranked by my judgement of how often and how far they move lambda, node prices or reserve prices (inferred; none was
tested here).

1. **Proxy reserve offers are missing (rows 56, 57; S6 6.5.7.3(5)).** ERCOT offers every qualified MW, beyond what the
   QSE submitted, at a floor of min($2,000, ASDC price at 95% of the AS Plan) − $0.01. The replica stops at submitted
   MW, so it has less reserve supply and can clear reserve prices too high whenever submitted offers run short. Needs:
   the hourly AS Plan quantity per product, and a check of whether the offer disclosure already contains proxy offers.
2. **Demand is the sum of Base Points, not GTBD (row 10; S6 6.5.7.3(3), S2 L559).** In any run where ERCOT itself was
   short or long, the sum of Base Points already excludes the violation, so the replica cannot reach the penalty
   prices. Needs: ERCOT's GTBD per SCED run.
3. **No price caps after the solve (row 6; S6 6.5.7.3(14)(d)).** Lambda and reserve prices are capped at the effective
   VOLL and bus prices above VOLL are pulled down. The replica can report lambda up to $11,052.01 and Reg-Up above
   $5,000. Matters only in scarcity, but then by thousands of dollars. Needs: nothing new.
4. **RRS sub-type limits (rows 70-72; ASM L26, S3 3.16(4)).** FFR is capped at 450 MW and relay loads plus FFR at 60% of
   the requirement; the PFR minimum is written in the replica as a ceiling tied to the curve's full width. These decide
   which resources hold RRS and so the RRS price and the headroom left for energy. Needs: the hourly RRS requirement.
5. **Resources on Output Schedules are frozen (rows 17, 34; S6 6.5.7.3(4)(a), S3 3.9.1(5)(b)(i)(C)).** `ONOS` is not in
   the dispatchable set, so these units neither move nor carry reserves. Needs: nothing new (status is in the
   disclosure); the schedule MW itself is not public, but the disclosed curve may already be the proxy.
6. **Reliability deployment pricing run is partial (row 7; S6 6.5.7.3.1).** `pricing_run()` reproduces ERCOT's adder to
   $0.16 on average over 22 days, with 96% of runs within $1. Open: which units opted out of RUC settlement is inferred
   from ERCOT's relaxed MW, not known beforehand; ERS restoration and the DC Tie adjustment are not modelled.
7. **Proxy energy curves for batteries and no-curve units (rows 19, 23, 24; S6 6.5.7.3(4), (6)).** A battery without a
   full curve is priced at RTSWCAP above zero and −$250 below; the replica uses the IRR proxy ($1,500) or a flat
   extension. Changes prices when such units are marginal, mostly in tight intervals. Needs: resource type; confirm
   whether SCED2 already holds ERCOT's proxy.
8. **Updated demand curves are ignored (row 68; S6 6.4.9.1.2).** When ERCOT changes the AS Plan intraday (the ASM allows
   up to 1,000 MW more Non-Spin, L40), the replica keeps the first curve. Needs: use the latest posting before the run.
9. **RUC-committed units' reserve offers at $250 (row 58; S6 6.5.7.3(5)(e)).** Small unless many units are RUC-committed.
   Needs: nothing new (`ONRUC` status).
10. **Load Resource limits (rows 61, 73; S4 4.4.7.2.1(6), S3 3.16(7)).** No Non-Spin with RRS/ECRS on one
    non-controllable load; non-controllable loads at most 50% of ECRS. Affects ECRS and Non-Spin prices when loads are
    cheap suppliers. Needs: the hourly ECRS requirement.
11. **Eligibility by status and the startup exception (rows 45, 46).** Mostly neutral if telemetered capability is zero
    where a product is not allowed. Needs: nothing new.
12. **VOLL switch under the Emergency Pricing Program or Peaker Net Margin (row 14; S4 4.4.11).** Rare; changes the
    penalty price and the cap of row 6. Needs: ERCOT's notices of the effective period.
13. **CLR with no bid, shift factor cutoff, lower extension of partial curves (rows 26, 90, 18).** Small.

---

## 3. Things the documents do not specify

So nobody looks for them here again.

- **GTBD formula** and its coefficients. S2 L559 gives a one-line definition only; S6 says it is "determined by LFC".
- **Battery duration numbers** for each product and for the Base Point. S6 refers to "SCED duration requirements"
  nine times and never gives a value. (Section 8, where the owner's notes place them, is not in the folder.)
- **The state-of-charge inequality** itself, including how charging offsets up awards.
- **The headroom rows.** No current paragraph writes energy + awards ≤ HSL or energy − Reg-Down ≥ LSL. Only S3 3.18(1)
  (awards within HSL − LSL) and the NPRR1309 grey box exist.
- **Minutes that turn a ramp rate into an award limit** for Regulation and Non-Spin. Only ECRS has "ten times the
  Emergency Ramp Rate" (S3 3.18(4)(a)).
- **Whether and how Real-Time SCED enforces the RRS sub-type limits.** S3 3.16 and the ASM state the limits as
  procurement rules ("DAM will limit"); S6 6.5.7.3 does not mention them.
- **Substitution between products.** Nothing found either way.
- **How self-provided Load Resource MW enter the clearing** (fixed award, $0 offer, or removed from demand).
- **How an OFFQS unit is dispatched for energy** ("available for SCED deployment" is all the text says).
- **How a sloped offer curve is integrated**, tie-breaking, and solver tolerances.
- **Hourly AS Plan quantities**, the monthly minimum-PFR posting, and the μ, σ, μ*, σ* of the aggregate curve: posted
  elsewhere by ERCOT.
- **Mitigation inputs:** the list of Competitive Constraints per run, the "variable not to exceed 0.01", verifiable
  costs behind the Mitigated Offer Cap (S4 4.4.9.4.1 was located at L764-866 but not transcribed for this audit).
- **Per-resource qualification limits:** droop-based RRS limits (Nodal Operating Guide Section 8, Attachment N),
  QSGR ten-minute capability, 20-second synchronous condenser capability (Section 8.1.1.2).
- **Which constraints are irresolvable today and their caps**, Resource C / D / H: operator determinations.
- **The "procedure developed by ERCOT"** for inclusive/exclusive offers (S4 4.4.7.2(1) L422).
- **Formulas lost in the text conversion:** AttP 3.1-3.4 (LMP and congestion formulas, L18-56) and S4 4.4.12(6)(a)-(b)
  (the reserve price and AORDC formulas, L1292, L1310) are blank or garbled in the `.txt` files. Read the PDF or Word
  versions for those.
