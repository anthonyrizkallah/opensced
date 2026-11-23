# The clearing

One dispatch interval is one linear program, solved with HiGHS through scipy. This page writes it out. Each part is
one short file in `src/opensced/core/features/`, and every number in it comes from the input tables or the rulebook.

## Symbols

| Symbol | Meaning | Where it comes from |
|---|---|---|
| `p[i]` | Output of resource `i`, MW. Negative for a charging battery or a dispatched load | Variable |
| `r[i,s]` | MW of reserve product `s` awarded to resource `i` | Variable |
| `z[j,s]` | MW of reserve offer block `j` used for product `s` | Variable |
| `q[d,k]` | MW bought on segment `k` of demand curve `d` | Variable |
| `short`, `surplus` | Power balance slack, MW | Variable |
| `v[c]` | MW by which constraint `c` is exceeded | Variable |
| `D` | Demand, MW | `inputs.demand` |
| `SF[c,i]` | Shift factor of resource `i` on constraint `c` | `inputs.shift_factors`, `resource_nodes` |
| `flow[c]`, `limit[c]`, `cap[c]` | Flow at current outputs, limit, maximum shadow price | `inputs.constraints` |
| `out[i]` | Output going into the interval | `inputs.resources.output` |

## The program

```text
minimize    energy offer cost
          + reserve offer cost
          - value of the reserves bought on the demand curves
          + shortage price x short  -  surplus price x surplus
          + sum over constraints of cap[c] x v[c]

subject to  the power balance
            each resource's dispatch range
            the network constraints
            reserve headroom, offers, demand and limits
            battery state of charge
```

### Energy and the power balance

A dispatchable resource may move between `max(ramp_low, low)` and `min(ramp_high, high)`. A resource that is not
dispatchable is held at `out[i]`.

An offer curve is a sloped line between its points and flat beyond the ends, so a resource's cost is the area under
that line. The curve is cut at its own points and into steps of at most `rules.block_mw`, each priced at the curve's
value at the step's midpoint. The program is then solved again with each curve cut finer around where its resource
landed (`rules.block_refine` passes, each ten times finer), so dispatch lands where the sloped line meets the price.
`rules.offer_curves = 'exact'` does without steps and solves the quadratic program directly; the refined steps
converge to the same answer.

```text
balance     sum over i of p[i]  +  short  -  surplus  =  D          dual: the system lambda
```

`short` is priced at `rules.shortage_price` and `surplus` at `rules.surplus_price`, so a system that cannot balance
prices at the penalty and is never infeasible.

### The network

```text
constraint c    flow[c]  +  sum over i of SF[c,i] x (p[i] - out[i])  <=  limit[c]  +  v[c]      dual: shadow price mu[c]
```

`flow[c]` is the flow on the element with every resource at its `out[i]`, so only the change in dispatch is multiplied
by shift factors. A violation costs `cap[c]` per MW: a constraint that nothing can relieve prices at its cap.

A resource split over several nodes takes the share-weighted mean of their shift factors. A resource with no node has
shift factor zero on every constraint.

### Reserves

Reserves are cleared in the same program as energy when the rulebook has products and `inputs.reserve_demand` is
given.

```text
ramp        p + share x regulation-up    <=  ramp_high                      share: rules.regulation_share
            p - share x regulation-down  >=  ramp_low
headroom    p + all upward awards        <=  high
            p - all downward awards      >=  low
capability  r[i,s]                       <=  reserve limit of i for s       inputs.reserve_limits
offers      sum over s of z[j,s]         <=  MW of block j                  one MW serves one product
            r[i,s]                        =  sum of z over i's blocks for s
demand      sum over k of q[d,k]         <=  sum of r[.,s] over the products serving curve d
                                                                            dual: the clearing price
limits      the rulebook's limits: awards of a group of products, from all or some resources, add up to at most
            a number of MW, a share of a requirement, or a requirement less a number of MW
```

Each demand curve is cut into segments at its points, each valued at the mean price over the segment. Several
products can serve one demand curve (three kinds of RRS in ERCOT), each with its own offers and limits. Without
reserve offers, every resource with a limit may carry the product at $0.

### Storage

What a battery is told to do over the interval, plus every reserve it is awarded, must fit in the energy it holds:

```text
discharge side   p x interval  +  sum over upward products of r x duration                    <=  soc - soc_min
charge side      eff x (charging MW x interval + sum over downward products of r x duration)
                 - discharging MW x interval                                                  <=  soc_max - soc
```

`duration` is the rulebook's hours each product must be sustained. `eff` is the share of charging energy that ends up
stored. `p` is signed: a charging battery can carry a little more upward reserve, by exactly the energy it takes in
during the interval. Both sides are floored at what the battery's energy dispatch alone can reach, so a battery that
cannot move loses reserves instead of making the program infeasible.

## Prices

Prices are the program's duals.

```text
system lambda          dual of the power balance
shadow price mu[c]     dual of constraint c
node price             lambda  -  sum over c of SF[c,node] x mu[c]
reserve price          dual of the product's demand row
```

## Offer mitigation: two steps

Some markets clear twice to stop a resource from setting a high price where it faces no competition.

```text
step 1   clear with the competitive constraints only. Each resource's price in this run is its reference price.
step 2   clear with every constraint, after adjusting the energy offer curves:
           floor   every curve is raised to the lesser of the resource's reference price and the mitigated offer
                   floor for its category
           cap     a resource marked mitigated has its curve lowered to the greater of
                     reference price + adder share x its mitigated offer cap at its low limit
                     its mitigated offer cap at that output
```

A curve is cut exactly where it crosses the floor or the cap. Which constraints are competitive and which resources
are mitigated are inputs; the market's competitiveness test is not run by the engine.

## A sequence of intervals

`opensced.clear_sequence` clears a list of intervals in order. `carry` picks what each interval takes from the one
before instead of from its own tables: each resource's starting output, the range its ramp rate lets it reach, and
each battery's state of charge.

## What the rulebook holds

Every constant above is a field of `opensced.Rules`: penalty curves, step size and refinement passes, the reserve
products with their direction, ramp minutes and duration, which statuses may be dispatched or carry which product,
system-wide limits, and mitigation floors. A market supplies dated rulebooks, and clearing a date uses the one in
force. See [rules.md](rules.md).
