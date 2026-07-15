"""
simulate.py — deterministic, time-phased what-if simulation.

The question this module answers: *"if node/lane X goes down for N weeks,
what actually happens to the business, week by week?"*

The engine runs in weekly buckets over a 12-week horizon, two-stage per
(DC, SKU) pair — because a DC can serve more than one market (Memphis DC
serves both US East and US West), inventory and upstream supply must be
pooled once per DC, not once per market, or a shared buffer gets silently
double-counted:

1. **Upstream stage** (shared across all markets a DC serves): each week,
   compute how many units can physically reach the DC — the bottleneck
   capacity across the supplier -> plant -> DC lane chain, reduced to
   `scenario.capacity_pct` on any lane touching the disrupted element
   while the outage is active. If a non-primary ("alternate sourcing")
   lane exists into the same downstream node and doesn't itself pass
   through the disrupted element, its capacity is added back in starting
   `switch_lag_weeks` after the outage begins — modeling the real-world
   delay of qualifying a backup supplier or re-routing freight.
2. **Downstream stage** (per market the DC serves): each market's demand
   (optionally shocked, for the demand-spike archetype) competes for the
   DC's available pool, additionally capped by its own outbound lane
   capacity. If the pool can't cover every market's deliverable demand,
   it's split proportionally.
3. **Inventory carries forward** week to week: `available = inventory +
   supply_in`; `shipped = min(available, demand)`; unmet demand is a lost
   sale (no backorder — this is a retail network, not a build-to-order one).

Two headline metrics per Simchi-Levi-style resilience metrics:
- **TTS (time to survive)**: consecutive weeks of >=98% service level
  the network sustains *before* the first dip once a disruption begins —
  i.e. how much buffer actually exists.
- **TTR (time to recover)**: weeks from that first dip until service
  returns to >=98% — i.e. how fast the network heals once it breaks.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import graph
from .models import Network, Scenario, SimResult, WeekResult

HORIZON_WEEKS = 12
RECOVERY_THRESHOLD = 0.98
OUTAGE_START_WEEK = 1  # every scenario's disruption begins in week 1 of the horizon


def _within_outage(scenario: Scenario | None, week: int) -> bool:
    return scenario is not None and OUTAGE_START_WEEK <= week <= scenario.outage_weeks


def _lane_touches_disrupted_element(scenario: Scenario, lane) -> bool:
    if scenario.element_kind == "lane":
        return lane.id == scenario.disrupted_element
    return lane.source == scenario.disrupted_element or lane.target == scenario.disrupted_element


def _effective_capacity(scenario: Scenario | None, week: int, lane) -> float:
    cap = lane.capacity_units_per_week
    if scenario is not None and _within_outage(scenario, week) and _lane_touches_disrupted_element(scenario, lane):
        cap *= scenario.capacity_pct
    return cap


def _bottleneck_capacity(chain_lanes: list, scenario: Scenario | None, week: int) -> float:
    if not chain_lanes:
        return float("inf")
    return min(_effective_capacity(scenario, week, lane) for lane in chain_lanes)


def _alt_boost(
    network: Network, sku_id: str, target_node_ids: set[str], scenario: Scenario | None, week: int
) -> float:
    """
    Extra weekly capacity from qualifying non-primary lanes: same target
    as something in the chain, doesn't itself touch the disrupted element,
    and only comes online `switch_lag_weeks` after the outage begins.
    """
    if scenario is None:
        return 0.0
    candidates = [
        lane
        for lane in network.lanes
        if not lane.primary
        and sku_id in lane.skus
        and lane.target in target_node_ids
        and not _lane_touches_disrupted_element(scenario, lane)
    ]
    if not candidates:
        return 0.0
    lag = max(l.switch_lag_weeks for l in candidates)
    if week < OUTAGE_START_WEEK + lag or week > scenario.outage_weeks:
        return 0.0
    return sum(l.capacity_units_per_week for l in candidates)


def _demand_for_week(network: Network, market_id: str, sku_id: str, scenario: Scenario | None, week: int) -> float:
    base = network.node(market_id).weekly_demand.get(sku_id, 0.0)
    if (
        scenario is not None
        and scenario.demand_shock_pct
        and scenario.element_kind == "node"
        and scenario.disrupted_element == market_id
        and _within_outage(scenario, week)
    ):
        return base * (1 + scenario.demand_shock_pct)
    return base


def _initial_inventory_units(network: Network, dc_id: str, sku_id: str) -> float:
    dc = network.node(dc_id)
    days = dc.inventory_days_of_cover.get(sku_id, 0.0)
    weekly_flow = graph.dc_weekly_flow(network, dc_id, sku_id)
    return (days / 7.0) * weekly_flow


@dataclass
class _WeekRevenue:
    demand_revenue: float
    shipped_revenue: float
    lost_revenue: float
    inventory_value: float


def _simulate_dc_sku(
    network: Network, dc_id: str, sku_id: str, scenario: Scenario | None, price: float
) -> list[_WeekRevenue]:
    upstream_lanes = graph.upstream_chain_lanes(network, dc_id, sku_id)
    markets = graph.markets_served(network, dc_id, sku_id)  # [(market_id, outbound_lane), ...]
    inventory = _initial_inventory_units(network, dc_id, sku_id)

    weeks: list[_WeekRevenue] = []
    for week in range(1, HORIZON_WEEKS + 1):
        # --- Stage 1: upstream supply reaching the DC's pool ---
        upstream_cap = _bottleneck_capacity(upstream_lanes, scenario, week)
        upstream_cap += _alt_boost(network, sku_id, {dc_id}, scenario, week)
        total_demand = sum(
            _demand_for_week(network, market_id, sku_id, scenario, week) for market_id, _ in markets
        )
        supply_in = min(upstream_cap, total_demand) if total_demand > 0 else 0.0
        available_pool = inventory + supply_in

        # --- Stage 2: per-market allocation, capped by outbound lane capacity ---
        market_demand: dict[str, float] = {}
        market_deliverable: dict[str, float] = {}
        for market_id, outbound_lane in markets:
            d = _demand_for_week(network, market_id, sku_id, scenario, week)
            outbound_cap = _effective_capacity(scenario, week, outbound_lane)
            outbound_cap += _alt_boost(network, sku_id, {market_id}, scenario, week)
            market_demand[market_id] = d
            market_deliverable[market_id] = min(d, outbound_cap)

        total_deliverable = sum(market_deliverable.values())
        if total_deliverable <= 0:
            total_shipped = 0.0
        elif available_pool >= total_deliverable:
            total_shipped = total_deliverable
        else:
            total_shipped = available_pool  # proportional split; only the aggregate matters here

        total_demand_units = sum(market_demand.values())
        total_lost_units = max(0.0, total_demand_units - total_shipped)
        inventory = max(0.0, available_pool - total_shipped)

        weeks.append(
            _WeekRevenue(
                demand_revenue=total_demand_units * price,
                shipped_revenue=total_shipped * price,
                lost_revenue=total_lost_units * price,
                inventory_value=inventory * price,
            )
        )
    return weeks


def _simulate_network(network: Network, scenario: Scenario | None) -> list[WeekResult]:
    price = {s.id: s.revenue_per_unit for s in network.skus}
    per_pair = [
        _simulate_dc_sku(network, dc_id, sku_id, scenario, price[sku_id])
        for dc_id, sku_id in graph.dc_sku_pairs(network)
    ]

    weeks: list[WeekResult] = []
    for i in range(HORIZON_WEEKS):
        demand_rev = sum(p[i].demand_revenue for p in per_pair)
        shipped_rev = sum(p[i].shipped_revenue for p in per_pair)
        lost_rev = sum(p[i].lost_revenue for p in per_pair)
        inv_val = sum(p[i].inventory_value for p in per_pair)
        service_level = (shipped_rev / demand_rev) if demand_rev > 0 else 1.0
        weeks.append(
            WeekResult(
                week=i + 1,
                service_level=round(service_level, 4),
                lost_revenue=round(lost_rev, 2),
                inventory_position=round(inv_val, 2),
            )
        )
    return weeks


def compute_ttr_tts(
    weeks: list[WeekResult], outage_start: int = OUTAGE_START_WEEK, threshold: float = RECOVERY_THRESHOLD
) -> tuple[int | None, int]:
    """
    TTS = consecutive weeks (from `outage_start`) service stays >= threshold
    before the first dip. TTR = weeks from that first dip until service is
    back >= threshold (None if it never recovers within the horizon).
    If service never dips at all, TTR=0 and TTS covers the full window.
    """
    tts = 0
    incident_week: int | None = None
    for wr in weeks:
        if wr.week < outage_start:
            continue
        if incident_week is None:
            if wr.service_level >= threshold:
                tts += 1
                continue
            incident_week = wr.week

    if incident_week is None:
        return 0, tts

    recovery_week = None
    for wr in weeks:
        if wr.week >= incident_week and wr.service_level >= threshold:
            recovery_week = wr.week
            break
    ttr = (recovery_week - incident_week) if recovery_week is not None else None
    return ttr, tts


def run_scenario(network: Network, scenario: Scenario) -> SimResult:
    """Run baseline (no disruption) and the given scenario, package both into a SimResult."""
    baseline_weeks = _simulate_network(network, None)
    scenario_weeks = _simulate_network(network, scenario)
    ttr, tts = compute_ttr_tts(scenario_weeks)
    total_lost = round(sum(w.lost_revenue for w in scenario_weeks), 2)
    baseline_service = baseline_weeks[0].service_level if baseline_weeks else 1.0
    worst_service = min((w.service_level for w in scenario_weeks), default=1.0)
    return SimResult(
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        baseline_weeks=baseline_weeks,
        scenario_weeks=scenario_weeks,
        ttr=ttr,
        tts=tts,
        total_lost_revenue=total_lost,
        baseline_service_level=baseline_service,
        worst_service_level=worst_service,
        outage_start_week=OUTAGE_START_WEEK,
        outage_end_week=scenario.outage_weeks,
    )


# --------------------------------------------------------------------------
# Preset scenarios (spec: single-source supplier failure, port closure,
# demand spike)
# --------------------------------------------------------------------------

PRESET_SCENARIOS: dict[str, Scenario] = {
    "supplier-failure": Scenario(
        id="supplier-failure",
        name="Single-Source Supplier Failure — Rhineland Precision GmbH",
        disrupted_element="SUP-DE-PREC",
        element_kind="node",
        outage_weeks=4,
        capacity_pct=0.0,
        description=(
            "The sole supplier of precision fasteners (SKU-E) for the Wroclaw plant "
            "fails outright for 4 weeks. No alternate supplier exists for this "
            "component anywhere in the network."
        ),
    ),
    "port-closure": Scenario(
        id="port-closure",
        name="Port of Singapore Closure",
        disrupted_element="DC-SG",
        element_kind="node",
        outage_weeks=2,
        capacity_pct=0.0,
        description=(
            "The Singapore Regional DC is fully closed for 2 weeks. An air-freight "
            "bypass can carry SmartHome Hub and Wireless Charger units directly from "
            "the Shenzhen plant once activated; the Tote Bag, Travel Mug, and "
            "Multi-Tool lines have no bypass."
        ),
    ),
    "demand-spike": Scenario(
        id="demand-spike",
        name="US East Demand Spike (+40%)",
        disrupted_element="MKT-US-E",
        element_kind="node",
        outage_weeks=3,
        capacity_pct=1.0,
        demand_shock_pct=0.4,
        description=(
            "A viral SmartHome Hub post drives +40% demand at US East Retail for "
            "3 weeks, straining Memphis DC's inbound and outbound capacity."
        ),
    ),
}


def get_preset(scenario_id: str) -> Scenario:
    try:
        return PRESET_SCENARIOS[scenario_id]
    except KeyError as exc:
        raise ValueError(
            f"unknown scenario id {scenario_id!r}; choices: {sorted(PRESET_SCENARIOS)}"
        ) from exc


def run_all_presets(network: Network) -> dict[str, SimResult]:
    return {sid: run_scenario(network, scenario) for sid, scenario in PRESET_SCENARIOS.items()}
