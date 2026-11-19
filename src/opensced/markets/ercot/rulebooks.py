"""ERCOT's rulebooks, one per effective date.

Each entry under `notes` says where the number comes from: 'protocols' (read from ERCOT's Nodal Protocols or a
market notice) or 'measured' (fitted to ERCOT's own disclosed dispatch, because the public documents do not state it).
"""
from opensced.core.rules import Limit, Product, Rulebooks, Rules, Status

def _products(pfr_reserved_mw):
    """ERCOT's reserve products. The last three entries of each say where the adapter finds the product in ERCOT's
    files: the capability columns of the SCED disclosure, the price columns of the reserve offer disclosure (block
    number left out) and the kinds of offer that can carry it."""
    return (
        Product('RegUp', 'up', duration_hours=0.5, regulation=True, ramp_minutes=5,
                capability_columns=('ASCapREGUP',), offer_price_columns=('REGUP',), offer_kinds=('ONRES',)),
        Product('RegDown', 'down', duration_hours=0.5, regulation=True, ramp_minutes=5,
                capability_columns=('ASCapREGDN',), offer_price_columns=('REGDN',), offer_kinds=('REGDN',)),
        Product('RRS-PFR', 'up', duration_hours=0.5, demand='RRS', reserved_mw=pfr_reserved_mw,
                capability_columns=('ASCapRRSPFR',), offer_price_columns=('RRSPFR',), offer_kinds=('ONRES',)),
        Product('RRS-FFR', 'up', duration_hours=0.25, demand='RRS',
                capability_columns=('ASCapRRSFFR',), offer_price_columns=('RRSFFR',), offer_kinds=('ONRES',)),
        Product('RRS-UFR', 'up', duration_hours=0.25, demand='RRS',
                capability_columns=('ASCapRRSUFR',), offer_price_columns=('RRSUFR',), offer_kinds=('ONRES',)),
        Product('ECRS', 'up', duration_hours=1.0, ramp_minutes=10,
                capability_columns=('ASCapECRS',), offer_price_columns=('ECRS',), offer_kinds=('ONRES', 'OFFNS')),
        Product('NonSpin', 'up', duration_hours=4.0, ramp_minutes=30,
                capability_columns=('ASCapNSPIN',), offer_price_columns=('NSPIN',), offer_kinds=('ONRES', 'OFFNS')),
    )


# Telemetered Resource Status (Protocols 3.9.1(5)(b)): what SCED may do with a resource in each.
_ONLINE = {'ONRES': None, 'REGDN': None}
_RRS_ECRS = ('RRS-PFR', 'RRS-FFR', 'RRS-UFR', 'ECRS')
STATUSES = (
    Status('ON', True, _ONLINE), Status('ONRUC', True, _ONLINE), Status('ONOPTOUT', True, _ONLINE), Status('ONEMR', True, _ONLINE),
    Status('ONOS', True, _ONLINE),                                      # on an Output Schedule: held by ERCOT's proxy curve
    # off-line quick start: available for SCED deployment. Its ECRS is offered as an on-line reserve (ONRES), because it
    # can be on within ten minutes; its Non-Spin through either kind of offer
    Status('OFFQS', True, {'ONRES': ('ECRS', 'NonSpin')}),
    # an off-line unit is awarded only what it submitted: ERCOT's proxy offer is not used for its capacity ...
    Status('OFF', False, {'OFFNS': ('NonSpin',)}, proxy_reserves=False),
    # ... unless it is a quick-start unit that happens to telemeter OFF (the adapter's `quick_start` names them)
    Status('OFF-QS', False, {'OFFNS': ('NonSpin',)}),
    Status('ONSC', False, {'ONRES': _RRS_ECRS}),                        # synchronous condenser
    # starting up: held at its base point, but awarded Non-Spin like an off-line unit, from its OFFNS row (measured)
    Status('STARTUP', False, {'OFFNS': ('NonSpin',)}, proxy_reserves=False),
    Status('ONTEST'), Status('ONHOLD'), Status('SHUTDOWN'), Status('OUT'), Status('EMR'), Status('EMRSWGR'),
    Status('ONL', True, {'ONRES': None}),                               # a Load Resource that is on-line
    Status('OUTL'),
    Status('ONREG', True, _ONLINE), Status('ONDSR', True, _ONLINE), Status('ONRR', True, _ONLINE), Status('FRRSUP', True, _ONLINE),   # retired: older files
)


RTC_B = Rules(
    name='ercot/2025-12-05',
    effective='2025-12-05',
    source='Real-Time Co-optimization plus Batteries (RTC+B) go-live, December 5, 2025',
    shortage_price=None,                     # = voll + offer_cap + shortage_adder = 11,052.01
    voll=5000.0,
    offer_cap=2000.0,
    offer_floor=-250.0,
    shortage_adder=4052.01,
    surplus_price=-250.0,
    default_max_shadow_price=5251.0,
    block_mw=5.0,
    dispatch_limits='ramp',
    interval_hours=5 / 60,
    regulation_share=5 / 7,
    products=_products(pfr_reserved_mw=1365.0),
    limits=(
        Limit('FFR', ('RRS-FFR',), max_mw=450.0, source='AS methodology, RRS: fast frequency response is limited to 450 MW'),
        Limit('relay loads + FFR', ('RRS-FFR', 'RRS-UFR'), max_share=0.60, of='RRS',
              source='Protocols 3.16(4): load resources on under-frequency relays and FFR are limited to 60% of the RRS requirement'),
        Limit('ECRS from loads', ('ECRS',), max_share=0.50, of='ECRS', where=(('type', 'NCLR'),),
              source='Protocols 3.16(7): load resources other than controllable ones are limited to 50% of the ECRS requirement'),
    ),
    price_cap=None,                          # = voll
    shift_factor_cutoff=0.0001,
    storage_charge_efficiency=0.85,
    block_refine=3,
    self_arranged_price=-10000.0, reserve_offer_floor=-1e9,
    statuses=STATUSES,
    two_step=True,
    mitigated_offer_floors={'nuclear': -250.0, 'hydro': -250.0, 'coal': -20.0, 'combined_cycle': -20.0, 'gas_steam_ct': -20.0,
                            'qf': -50.0, 'wind': -100.0, 'pv': -50.0, 'esr': -250.0, 'other': -50.0},
    mitigation_adder_share=0.0,
    generic_heat_rates={'in_service_by_2004': 10.5, 'in_service_after_2004': 14.5},
    shadow_price_caps={'base': 5251.0, 'above_200kv': 4500.0, '100_to_200kv': 3500.0, 'below_100kv': 2800.0},
    features=('network', 'reserves', 'storage'),
    notes={
        'shortage_price': 'protocols: effective value of lost load 5,000 + effective system-wide offer cap 2,000 + 4,052.01',
        'surplus_price': 'protocols: the over-generation penalty',
        'default_max_shadow_price': 'a fallback, used only when ERCOT publishes a constraint without its maximum shadow price',
        'dispatch_limits': 'protocols 6.5.7.3: SCED dispatches each resource between its LDL and HDL. Measured on three days of 2026: '
                           'about 200 resources per run have an HDL up to 0.05 MW above their HSL (6 MW per run in all), and the base point '
                           'follows the HDL on nearly nine in ten of them; no base point is above its HDL beyond rounding. With reserves '
                           'awarded, base point + upward awards stays within the higher of HSL and HDL',
        'regulation_share': 'protocols 6.5.7.3(12): a scaling factor of 5/7 on Reg-Up against HDL and on Reg-Down against LDL',
        'price_cap': 'protocols 6.5.7.3(14)(d): system lambda and reserve prices are capped at the effective value of lost load, 5,000',
        'shift_factor_cutoff': 'protocols Section 22 Attachment P 3.3: default cutoff 0.0001',
        'limits': 'written as procurement rules (3.16 and the AS methodology, which says "DAM will limit"); applied here in real time too',
        'duration_hours': 'Section 8.1.1.3 qualification times: Reg-Up, Reg-Down and RRS-PFR 30 min, RRS-FFR 15 min, ECRS 1 h, Non-Spin 4 h. '
                          'Measured against ERCOT awards on seven days: about 361,000 battery-runs with upward awards, none breaks the '
                          'stored-energy rule and two thirds sit exactly on it; 31,450 battery-runs with Reg-Down, none breaks the '
                          'charge-side rule at 30 min times the battery\'s efficiency and one in five sits exactly on it',
        'storage_charge_efficiency': 'protocols 3.7.1.3(1)(c): Round Trip Efficiency is a registered Resource Parameter and is not published. '
                                     'helpers.battery_efficiency() reads each battery\'s value off ERCOT\'s Reg-Down awards (0.81 to 1.0; '
                                     'a third of batteries have no award to read it from). 0.85 is the most common value, used for the rest',
        'self_arranged_price': 'measured on four days (190,980 load-runs with self-provided reserves): the ECRS award equals the self-provided '
                               'ECRS, or the room left after RRS, on 97%; where room is short RRS is filled first on 95%. A load is '
                               'never awarded anything while not ONL (341,380 load-runs). The price is only a device to make the clearing '
                               'take self-provided MW first; it is never the marginal offer',
        'statuses_startup': 'measured on three days (21 unit-runs, 422 MW-runs): a unit in STARTUP is awarded Non-Spin within its OFFNS row on '
                            'every one, and above its ONRES row on half. On March 23, 2026 at 21:30 three such units held 110 MW',
        'statuses_offqs': 'measured on two days (3,093 unit-runs): an off-line quick-start unit is awarded ECRS and Non-Spin from its '
                          'ONRES row only. Its OFFNS row repeats the same MW and is not added',
        'shadow_price_caps': 'protocols Section 22 Attachment P: base case 5,251; contingency by voltage 4,500 / 3,500 / 2,800',
        'statuses': 'protocols 3.9.1(5)(b). Which off-line units get ERCOT\'s proxy offer (6.5.7.3(5), "qualified Resources") is measured on three '
                    'days: a quick-start unit does, whether it telemeters OFFQS (74 of 74 unit-runs awarded above the MW it submitted) or '
                    'OFF (6 of 6 awarded at full capability with nothing submitted); any other off-line unit does not (0 of 10 with the '
                    'proxy price under the clearing price, and 0 of 4 above its submitted MW)',
        'storage_signed_energy': 'measured: base point x 5 minutes (signed) + awards x duration <= SOC - MinSOC holds on every one of '
                                 'about 260,000 battery-runs with upward awards on five days of 2026, and about 40% sit exactly on it',
        'two_step': 'protocols 6.5.7.3(14): step 1 on competitive constraints gives reference prices; step 2 floors and caps the offers',
        'mitigated_offer_floors': 'protocols 4.4.9.4.2',
        'generic_heat_rates': 'protocols 4.4.9.4.1: generic incremental heat rate 10.5 for commercial operation on or before January 1, 2004, else 14.5',
        'mitigation_adder_share': 'protocols 6.5.7.3(14)(b)(i): "a variable not to exceed 0.01". The value ERCOT uses is not stated; 0 here',
        'ramp_minutes': 'reconstructed: awards against disclosed capability (Reg 5, ECRS 10, Non-Spin 30 minutes)',
        'RRS-PFR reserved_mw': 'AS methodology: RRS from primary frequency response shall not be less than 1,365 MW (2025) / '
                               '1,377 MW (2026), and ERCOT may set a higher value by month. Confirmed in the disclosure: the '
                               'RRS-PFR awarded sits at exactly this many MW in nearly every run',
        'block_mw': 'a modelling choice, not an ERCOT rule: the step used to cut sloped offer curves',
        'not modelled': "ERCOT's demand target (not published: the sum of base points is used); the rule that a "
                        'non-controllable load may not hold Non-Spin together with RRS or ECRS (it needs a yes/no choice per '
                        'load, which a linear program cannot make); the reliability deployment price adder (a second pricing run)',
    },
)

PFR_1377 = RTC_B.replace(
    name='ercot/2026-01-01',
    effective='2026-01-01',
    source='ERCOT Methodologies for Determining Minimum Ancillary Service Requirements, effective January 1, 2026: RRS from primary frequency response at least 1,377 MW (was 1,365)',
    products={'RRS-PFR': {'reserved_mw': 1377.0}},
)

ALL = Rulebooks([RTC_B, PFR_1377])
