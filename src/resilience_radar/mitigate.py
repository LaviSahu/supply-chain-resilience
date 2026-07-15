"""
mitigate.py — the mitigation playbook and its ranking.

Five standard resilience levers, each with a cost estimate and an
*effect model expressed as a network/scenario transform* rather than a
hardcoded percentage. Ranking works by literally re-running
`simulate.run_scenario` on the transformed network/scenario and comparing
lost revenue to the untouched baseline scenario run:

    avoided_loss = base_result.total_lost_revenue - mitigated_result.total_lost_revenue
    net_benefit  = avoided_loss - cost

This means an action that doesn't structurally help a given scenario
(e.g. dual-sourcing a supplier that a pure demand spike never touches)
correctly nets out to ~zero avoided loss instead of an arbitrary
hand-tuned discount — the ranking is a genuine simulation result, not a
lookup table.

The five actions:

- **dual-source**: qualify a second supplier/lane for the disrupted
  element, restoring half of normal throughput immediately (no switch
  lag). Effective only when the disruption is a hard capacity cut.
- **safety-stock-uplift**: permanently raise days-of-cover at every DC —
  a recurring carrying-cost lever that cushions *any* disruption.
- **alt-lane-mode-shift**: pre-negotiate existing alternate lanes so they
  activate with zero switch lag instead of their normal lag.
- **pre-build-buffer**: a one-time, cheaper-per-unit production run
  ahead of a known risk window (same mechanism as safety stock — extra
  starting inventory — but smaller and framed as a one-off spend; see
  implementation-notes.md).
- **allocation-prioritization**: smarter demand/supply matching that
  squeezes a modest amount of extra effective throughput out of
  constrained capacity, at near-zero capital cost.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable

from . import graph, simulate
from .models import Network, NodeType, Scenario, SimResult

ApplyFn = Callable[[Network, Scenario], tuple[Network, Scenario, float]]

HOLDING_COST_RATE_ANNUAL = 0.15  # % of unit revenue, annualized carrying cost
COGS_FRACTION = 0.40  # fraction of revenue_per_unit treated as unit production cost


@dataclass
class MitigationAction:
    id: str
    name: str
    mechanism: str


@dataclass
class MitigationResult:
    action_id: str
    action_name: str
    mechanism: str
    cost: float
    avoided_loss: float
    net_benefit: float
    recommended: bool = False


def _apply_dual_source(network: Network, scenario: Scenario) -> tuple[Network, Scenario, float]:
    """Restore up to 50 percentage points of capacity via a qualified second source."""
    new_scenario = copy.deepcopy(scenario)
    new_scenario.capacity_pct = min(1.0, scenario.capacity_pct + 0.5)
    # Cost: flat supplier-qualification/setup estimate, independent of network scale.
    cost = 180_000.0
    return network, new_scenario, cost


def _apply_safety_stock_uplift(network: Network, scenario: Scenario, extra_days: float = 7.0) -> tuple[Network, Scenario, float]:
    """Permanently raise days-of-cover at every DC by `extra_days`."""
    new_network = copy.deepcopy(network)
    cost = 0.0
    price = {s.id: s.revenue_per_unit for s in new_network.skus}
    weekly_carry_rate = HOLDING_COST_RATE_ANNUAL * 12 / 52  # prorated to the 12-week horizon
    for node in new_network.nodes:
        if node.type != NodeType.DC:
            continue
        for sku_id in list(node.inventory_days_of_cover):
            weekly_flow = graph.dc_weekly_flow(new_network, node.id, sku_id)
            extra_units = (extra_days / 7.0) * weekly_flow
            cost += extra_units * price[sku_id] * weekly_carry_rate
            node.inventory_days_of_cover[sku_id] += extra_days
    return new_network, scenario, round(cost, 2)


def _apply_alt_lane_mode_shift(network: Network, scenario: Scenario) -> tuple[Network, Scenario, float]:
    """Pre-negotiate every alternate lane so it activates with zero switch lag."""
    new_network = copy.deepcopy(network)
    qualifying = 0
    for lane in new_network.lanes:
        if not lane.primary and lane.switch_lag_weeks > 0:
            lane.switch_lag_weeks = 0
            qualifying += 1
    cost = qualifying * 15_000.0
    return new_network, scenario, cost


def _apply_pre_build_buffer(network: Network, scenario: Scenario, extra_days: float = 3.0) -> tuple[Network, Scenario, float]:
    """One-time pre-built inventory ahead of a known risk window."""
    new_network = copy.deepcopy(network)
    cost = 0.0
    price = {s.id: s.revenue_per_unit for s in new_network.skus}
    for node in new_network.nodes:
        if node.type != NodeType.DC:
            continue
        for sku_id in list(node.inventory_days_of_cover):
            weekly_flow = graph.dc_weekly_flow(new_network, node.id, sku_id)
            extra_units = (extra_days / 7.0) * weekly_flow
            cost += extra_units * price[sku_id] * COGS_FRACTION
            node.inventory_days_of_cover[sku_id] += extra_days
    return new_network, scenario, round(cost, 2)


def _touches_disrupted_element(scenario: Scenario, lane) -> bool:
    if scenario.element_kind == "lane":
        return lane.id == scenario.disrupted_element
    return lane.source == scenario.disrupted_element or lane.target == scenario.disrupted_element


def _apply_allocation_prioritization(network: Network, scenario: Scenario) -> tuple[Network, Scenario, float]:
    """
    Smarter demand/supply matching squeezes extra effective throughput from
    constrained capacity: a modest 15pp `capacity_pct` recovery (helps
    supply-side capacity cuts) plus a 15% physical capacity bump on every
    lane touching the disrupted element (helps distribution-capacity
    ceilings, e.g. an outbound lane that's the true bottleneck under a
    demand spike, where `capacity_pct` alone has nothing to restore).
    """
    new_network = copy.deepcopy(network)
    new_scenario = copy.deepcopy(scenario)
    new_scenario.capacity_pct = min(1.0, scenario.capacity_pct + 0.15)
    for lane in new_network.lanes:
        if _touches_disrupted_element(scenario, lane):
            lane.capacity_units_per_week *= 1.15
    cost = 8_000.0
    return new_network, new_scenario, cost


PLAYBOOK: list[tuple[MitigationAction, ApplyFn]] = [
    (
        MitigationAction(
            "dual-source",
            "Dual-Source the Disrupted Input",
            "Qualify a second supplier/lane for the disrupted element ahead of time; "
            "restores up to 50pp of normal throughput immediately (no switch lag).",
        ),
        _apply_dual_source,
    ),
    (
        MitigationAction(
            "safety-stock-uplift",
            "Raise Safety Stock (+7 days cover)",
            "Permanently add 7 days of cover at every DC; a recurring carrying-cost "
            "lever that cushions any disruption, not just this scenario.",
        ),
        _apply_safety_stock_uplift,
    ),
    (
        MitigationAction(
            "alt-lane-mode-shift",
            "Pre-Negotiate Alternate Lanes",
            "Contract alternate lanes/modes in advance so they activate with zero "
            "switch lag instead of their normal qualification delay.",
        ),
        _apply_alt_lane_mode_shift,
    ),
    (
        MitigationAction(
            "pre-build-buffer",
            "Pre-Build Buffer Stock (+3 days)",
            "One-time production run ahead of a known risk window; cheaper per unit "
            "than permanent safety stock but doesn't persist after the buffer is drawn down.",
        ),
        _apply_pre_build_buffer,
    ),
    (
        MitigationAction(
            "allocation-prioritization",
            "Prioritized Allocation",
            "Smarter demand/supply matching during shortage squeezes modest extra "
            "effective throughput out of constrained capacity, at near-zero capital cost.",
        ),
        _apply_allocation_prioritization,
    ),
]


def rank_mitigations(
    network: Network, scenario: Scenario, base_result: SimResult | None = None
) -> list[MitigationResult]:
    """
    Re-run `simulate.run_scenario` with each playbook action applied, rank
    by net benefit (avoided loss - cost) descending, and flag the top 3.
    """
    base_result = base_result or simulate.run_scenario(network, scenario)

    results: list[MitigationResult] = []
    for action, apply_fn in PLAYBOOK:
        mod_network, mod_scenario, cost = apply_fn(network, scenario)
        mod_result = simulate.run_scenario(mod_network, mod_scenario)
        avoided_loss = round(base_result.total_lost_revenue - mod_result.total_lost_revenue, 2)
        net_benefit = round(avoided_loss - cost, 2)
        results.append(
            MitigationResult(
                action_id=action.id,
                action_name=action.name,
                mechanism=action.mechanism,
                cost=round(cost, 2),
                avoided_loss=avoided_loss,
                net_benefit=net_benefit,
            )
        )

    results.sort(key=lambda r: r.net_benefit, reverse=True)
    for r in results[:3]:
        if r.net_benefit > 0:
            r.recommended = True
    return results
