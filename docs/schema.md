# Input tables (schema version 2)

Generated from the code by `opensced.schema()`. The code is the definition: `Inputs.validate()` checks every table against it.

```text
resources  (one row per resource; required)
    Everything that can inject, consume or carry reserves in this interval.
    name             text                    required. Unique id of the resource.
    low              number  [MW]            required. Lowest output it can sustain (its low sustained limit). Negative for a battery that can charge.
    high             number  [MW]            required. Highest output it can sustain (its high sustained limit).
    ramp_low         number  [MW]            optional, default low. Lowest output it can reach within this interval, given where it is now and its ramp rate.
    ramp_high        number  [MW]            optional, default high. Highest output it can reach within this interval.
    output           number  [MW]            optional, default 0.0. Its output going into the interval. A resource that is not dispatchable is held here, and the constraints' `flow` is measured with every resource at this output.
    dispatchable     bool                    optional, default True. True if the clearing may move it. False holds it at `output` (it may still carry reserves).
    kind             text                    optional, default generator. 'generator', 'storage' or 'load'. Informational, except that a 'load' carries reserves by cutting consumption.
    status           text                    optional, default . The market's status code for the resource. A rulebook's `statuses` say what each may do; adapters use it.
    type             text                    optional, default . The market's resource type. Rulebook limits can select on it.
    category         text                    optional, default other. Fuel or technology category, for helpers that build proxy curves or mitigated offers.
    ramp_up          number  [MW/min]        optional, default None. Normal ramp rate up. Used by helpers that compute ramp_high.
    ramp_down        number  [MW/min]        optional, default None. Normal ramp rate down. Used by helpers that compute ramp_low.
    output_schedule  number  [MW]            optional, default None. Scheduled output of a resource that submitted a schedule instead of an offer curve.
    ruc_committed    bool                    optional, default False. Committed by the reliability unit commitment process.
    mitigated        bool                    optional, default False. Its offer is capped in the second step of a two-step clearing: it failed the market's competitiveness test for this interval.
    max_consumption  number  [MW]            optional, default None. Maximum power consumption of a load resource.
    low_consumption  number  [MW]            optional, default None. Low power consumption of a load resource.

energy_offers  (one row per offer curve point; optional)
    Each resource's energy offer curve. Price is linear between points and flat beyond the ends. A dispatchable resource with no points offers at $0.
    resource         text                    required. Resource name.
    mw               number  [MW]            required. Output level. Negative MW is consumption: a battery's charging bid.
    price            number  [$/MWh]         required. Offer price at that output.

storage  (one row per battery; optional)
    State of charge of each storage resource. Only needed when reserves are cleared.
    resource         text                    required. Resource name.
    soc              number  [MWh]           required. Energy stored going into the interval.
    soc_min          number  [MWh]           required. Lowest allowed state of charge.
    soc_max          number  [MWh]           required. Highest allowed state of charge.
    efficiency       number  [share]         optional, default 1.0. Share of charging energy that ends up stored. Used when state of charge is carried from one interval to the next.

reserve_limits  (one row per resource and product; optional)
    How much of each reserve product a resource is able to carry.
    resource         text                    required. Resource name.
    product          text                    required. Reserve product, as named in the rulebook.
    mw               number  [MW]            required. The most it can be awarded of that product.

reserve_offers  (one row per offer block and product; optional)
    Reserve offers. A block is a quantity of MW that may serve any one of the products priced in it, so one MW is never sold twice. When this table is given, a resource carries only what it offered.
    resource         text                    required. Resource name.
    block            text                    required. Id of the block, unique within the resource.
    mw               number  [MW]            required. Size of the block. Repeat it on each of the block's product rows.
    product          text                    required. Reserve product the block is offered for.
    price            number  [$/MW per hour] required. Offer price for that product.

reserve_demand  (one row per demand curve point; optional)
    What the system pays for each MW of each reserve product: a falling curve of cumulative MW against price. Giving this table switches reserve co-optimization on.
    product          text                    required. The demand curve's name: a reserve product, or the name several products count towards.
    mw               number  [MW]            required. Cumulative MW of the product.
    price            number  [$/MW per hour] required. Value of the MW at that point. Linear between points.

constraints  (one row per network constraint; optional)
    The transmission constraints to enforce: flow + sum(shift factor x (MW - output)) <= limit.
    name             text                    required. Unique id. Must match a row of shift_factors.
    limit            number  [MW]            required. The most the element may carry.
    flow             number  [MW]            required. Flow on the element with every resource at its `output`.
    max_shadow_price number  [$/MWh]         required. Price at which the clearing gives up and lets the limit be exceeded.
    kind             text                    optional, default contingency. 'base', 'contingency' or 'irol'. Used by helpers that set max_shadow_price.
    kv               number  [kV]            optional, default None. Voltage of the limiting element. Used by helpers that set max_shadow_price.
    competitive      bool                    optional, default True. Whether the constraint is a competitive constraint, for offer mitigation.

mitigated_offer_caps  (one row per curve point; optional)
    The cost-based cap on each resource's offer, used in the second step of a two-step clearing for resources marked `mitigated`. Linear between points, flat beyond the ends.
    resource         text                    required. Resource name.
    mw               number  [MW]            required. Output level.
    price            number  [$/MWh]         required. The mitigated offer cap at that output.

reserve_requirements  (one row per demand curve; optional)
    How many MW of each reserve the system plans to hold. Shares in the rulebook (a limit of 60% of a requirement, MW reserved for one product) are taken of this. Default: the total MW of the product's demand curve.
    product          text                    required. The demand curve's name.
    mw               number  [MW]            required. The requirement.

limit_values  (one row per rulebook limit; optional)
    This interval's own numbers for limits named in the rulebook, for values the market resets by month or by hour. A row named after a product overrides the MW reserved for that product.
    limit            text                    required. Name of the rulebook Limit, or of a product with reserved MW.
    min_mw           number  [MW]            optional, default None. Floor for this interval.
    max_mw           number  [MW]            optional, default None. Cap for this interval.

demand
    One number, MW: what the dispatched resources must add up to in this interval.

shift_factors
    DataFrame. Index: constraint name. Columns: node name, or resource name when resource_nodes is not given. Value: MW of flow on the constraint per MW injected there. Anything missing is taken as 0.

resource_nodes
    Where each resource injects. A Series or dict resource -> node, or a DataFrame with columns resource, node and optionally share for a resource split over several nodes.

mitigated
    True if energy_offers already hold the mitigated curves, so a two-step rulebook clears once. Default False.

time
    Optional timestamp of the interval. A market uses it to pick the rulebook in force.
```
