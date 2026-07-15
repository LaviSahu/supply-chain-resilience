"""
graph.py — network analytics over the modeled supply chain.

A resilience program needs to answer four structural questions about a
network *before* any disruption ever happens:

1. **Criticality** — if this node vanished, how much revenue would be at
   stake? (`node_criticality`)
2. **Single-sourcing** — which plant/SKU combinations have exactly one
   supplier standing behind them, i.e. zero redundancy? (`single_source_map`)
3. **Concentration** — within an input category (electronics, textiles,
   packaging, ...), how concentrated is supply among suppliers?
   (`hhi_by_category`, the Herfindahl-Hirschman Index used in antitrust
   and supply-risk analysis alike)
4. **Reachability** — which markets does a given node ultimately serve?
   (`downstream_markets`)

These are graph questions, not simulation questions: they describe the
*shape* of risk in the network, independent of any specific event or
what-if scenario. `scoring.py` and `simulate.py` both lean on the
functions here.

Criticality and single-sourcing are computed over **primary lanes only**
(`Lane.primary=True`). Primary lanes represent the network's everyday
flow; a bill-of-materials at a plant is an AND-dependency — every primary
input (components, fabric, packaging, ...) is required to build a unit —
so a node's "dependency set" for a given (market, sku) is the full
backward-reachable set of primary-lane nodes, not a single path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import Lane, Network, Node, NodeType, Sku


def load_network(path: Path | str) -> Network:
    """Load and validate a `network.json` file into a `Network`."""
    data = json.loads(Path(path).read_text())

    skus = [Sku(**s) for s in data["skus"]]

    nodes: list[Node] = []
    for n in data["nodes"]:
        n = dict(n)
        n["type"] = NodeType(n["type"])
        nodes.append(Node(**n))

    from .models import LaneMode

    lanes: list[Lane] = []
    for l in data["lanes"]:
        l = dict(l)
        l["mode"] = LaneMode(l["mode"])
        lanes.append(Lane(**l))

    network = Network(company=data["company"], nodes=nodes, lanes=lanes, skus=skus)
    _validate(network)
    return network


def _validate(network: Network) -> None:
    """Fail fast if lanes/events reference node ids that don't exist."""
    node_ids = {n.id for n in network.nodes}
    for lane in network.lanes:
        if lane.source not in node_ids:
            raise ValueError(f"lane {lane.id!r} has unknown source {lane.source!r}")
        if lane.target not in node_ids:
            raise ValueError(f"lane {lane.id!r} has unknown target {lane.target!r}")
    sku_ids = {s.id for s in network.skus}
    for lane in network.lanes:
        for sid in lane.skus:
            if sid not in sku_ids:
                raise ValueError(f"lane {lane.id!r} references unknown sku {sid!r}")


# --------------------------------------------------------------------------
# Revenue base
# --------------------------------------------------------------------------


def total_weekly_revenue(network: Network) -> float:
    """Sum of weekly_demand * revenue_per_unit across every market and SKU."""
    total = 0.0
    for node in network.nodes:
        if node.type != NodeType.MARKET:
            continue
        for sku_id, units in node.weekly_demand.items():
            total += units * network.sku(sku_id).revenue_per_unit
    return total


def market_sku_revenue(network: Network, market_id: str, sku_id: str) -> float:
    """Weekly revenue of one (market, sku) pair."""
    node = network.node(market_id)
    units = node.weekly_demand.get(sku_id, 0.0)
    return units * network.sku(sku_id).revenue_per_unit


def market_sku_pairs(network: Network) -> list[tuple[str, str]]:
    """Every (market_id, sku_id) pair with nonzero demand."""
    pairs: list[tuple[str, str]] = []
    for node in network.nodes:
        if node.type != NodeType.MARKET:
            continue
        for sku_id, units in node.weekly_demand.items():
            if units > 0:
                pairs.append((node.id, sku_id))
    return pairs


# --------------------------------------------------------------------------
# Dependency sets (backward reachability over primary lanes, per SKU)
# --------------------------------------------------------------------------


def upstream_node_set(network: Network, node_id: str, sku_id: str) -> set[str]:
    """
    `node_id` itself plus every node reachable by walking backward along
    primary lanes carrying `sku_id`. Works for any node (a market, a DC,
    even a plant) — it's the generic "what does this node's supply of
    this SKU ultimately depend on" query. Because plant inputs are
    AND-dependencies, this is a full backward-reachable set, not a single
    path.
    """
    visited = {node_id}
    frontier = [node_id]
    while frontier:
        nxt: list[str] = []
        for n in frontier:
            for lane in network.lanes_into(n):
                if lane.primary and sku_id in lane.skus and lane.source not in visited:
                    visited.add(lane.source)
                    nxt.append(lane.source)
        frontier = nxt
    return visited


def upstream_chain_lanes(network: Network, node_id: str, sku_id: str) -> list[Lane]:
    """All primary lanes carrying `sku_id` within `node_id`'s upstream dependency set."""
    nodes = upstream_node_set(network, node_id, sku_id)
    return [
        l
        for l in network.lanes
        if l.primary and sku_id in l.skus and l.target in nodes and l.source in nodes
    ]


# Market-facing aliases — revenue/criticality reasoning always starts from
# a market, so these names read more naturally at those call sites.
revenue_dependency_set = upstream_node_set
dependency_chain_lanes = upstream_chain_lanes


# --------------------------------------------------------------------------
# Criticality
# --------------------------------------------------------------------------


def node_criticality(network: Network) -> dict[str, float]:
    """
    Fraction of total network weekly revenue that depends on each node
    (i.e. would be at risk if the node were fully unavailable with no
    workaround). Revenue is intentionally double-counted across every
    node a (market, sku) flow depends on — that's what "AND-dependency
    criticality" means: removing *any one* of those nodes breaks the flow.
    """
    total = total_weekly_revenue(network)
    crit = {n.id: 0.0 for n in network.nodes}
    if total <= 0:
        return crit
    for market_id, sku_id in market_sku_pairs(network):
        revenue = market_sku_revenue(network, market_id, sku_id)
        for node_id in revenue_dependency_set(network, market_id, sku_id):
            crit[node_id] += revenue / total
    return crit


def lane_criticality(network: Network) -> dict[str, float]:
    """Same idea as `node_criticality` but for lanes, keyed by lane id."""
    total = total_weekly_revenue(network)
    crit = {l.id: 0.0 for l in network.lanes}
    if total <= 0:
        return crit
    for market_id, sku_id in market_sku_pairs(network):
        revenue = market_sku_revenue(network, market_id, sku_id)
        for lane in dependency_chain_lanes(network, market_id, sku_id):
            crit[lane.id] += revenue / total
    return crit


# --------------------------------------------------------------------------
# DC <-> market flow helpers — used by simulate.py to pool inventory
# correctly at DCs that serve more than one market (e.g. Memphis DC
# serves both US East and US West).
# --------------------------------------------------------------------------


def markets_served(network: Network, dc_id: str, sku_id: str) -> list[tuple[str, Lane]]:
    """(market_id, outbound_lane) pairs this DC primarily serves for `sku_id`."""
    result: list[tuple[str, Lane]] = []
    for lane in network.lanes_out_of(dc_id):
        if lane.primary and sku_id in lane.skus and network.node(lane.target).type == NodeType.MARKET:
            result.append((lane.target, lane))
    return result


def dc_weekly_flow(network: Network, dc_id: str, sku_id: str) -> float:
    """Total steady-state weekly demand (units) a DC must supply for one SKU, summed across every market it serves."""
    return sum(network.node(m).weekly_demand.get(sku_id, 0.0) for m, _ in markets_served(network, dc_id, sku_id))


def dc_sku_pairs(network: Network) -> list[tuple[str, str]]:
    """Every (dc_id, sku_id) pair that actually serves at least one market."""
    pairs: list[tuple[str, str]] = []
    for node in network.nodes:
        if node.type != NodeType.DC:
            continue
        for sku in network.skus:
            if markets_served(network, node.id, sku.id):
                pairs.append((node.id, sku.id))
    return pairs


# --------------------------------------------------------------------------
# Single-source detection
# --------------------------------------------------------------------------


@dataclass
class SingleSourceFlag:
    plant_id: str
    sku_id: str
    supplier_id: str


def single_source_map(network: Network) -> list[SingleSourceFlag]:
    """
    Every (plant, sku) fed by exactly one supplier via primary lanes —
    i.e. zero redundancy in the bill-of-materials for that SKU at that
    plant. A single-plant-wide failure of that one supplier stops the SKU.
    """
    plants = [n for n in network.nodes if n.type == NodeType.PLANT]
    suppliers_by_id = {n.id: n for n in network.nodes if n.type == NodeType.SUPPLIER}

    flags: list[SingleSourceFlag] = []
    for plant in plants:
        skus_at_plant: set[str] = set()
        for lane in network.lanes_into(plant.id):
            if lane.primary and lane.source in suppliers_by_id:
                skus_at_plant.update(lane.skus)
        for sku_id in skus_at_plant:
            feeding_suppliers = {
                lane.source
                for lane in network.lanes_into(plant.id)
                if lane.primary and lane.source in suppliers_by_id and sku_id in lane.skus
            }
            if len(feeding_suppliers) == 1:
                (supplier_id,) = feeding_suppliers
                flags.append(SingleSourceFlag(plant.id, sku_id, supplier_id))
    return flags


# --------------------------------------------------------------------------
# Supplier concentration (HHI)
# --------------------------------------------------------------------------


def hhi_by_category(network: Network) -> dict[str, float]:
    """
    Herfindahl-Hirschman Index (0-10000) per supplier input category.
    Share is proxied by each supplier's total outbound primary lane
    capacity within the category. 10000 = single supplier monopoly on
    that input category; lower = more diversified.
    """
    suppliers = [n for n in network.nodes if n.type == NodeType.SUPPLIER and n.category]
    capacity_by_supplier: dict[str, float] = {}
    for s in suppliers:
        capacity_by_supplier[s.id] = sum(
            l.capacity_units_per_week for l in network.lanes_out_of(s.id) if l.primary
        )

    categories: dict[str, list[str]] = {}
    for s in suppliers:
        categories.setdefault(s.category, []).append(s.id)

    result: dict[str, float] = {}
    for category, supplier_ids in categories.items():
        total_cap = sum(capacity_by_supplier[sid] for sid in supplier_ids)
        if total_cap <= 0:
            result[category] = 0.0
            continue
        hhi = sum((capacity_by_supplier[sid] / total_cap) ** 2 for sid in supplier_ids) * 10000
        result[category] = round(hhi, 1)
    return result


# --------------------------------------------------------------------------
# Downstream reachability
# --------------------------------------------------------------------------


def downstream_markets(network: Network, node_id: str) -> set[str]:
    """
    Every market id reachable forward from `node_id` via any lane
    (primary or alternate — this answers "what could this node serve",
    not "what does it serve today").
    """
    if network.node(node_id).type == NodeType.MARKET:
        return {node_id}
    visited = {node_id}
    frontier = [node_id]
    markets: set[str] = set()
    while frontier:
        nxt: list[str] = []
        for n in frontier:
            for lane in network.lanes_out_of(n):
                if lane.target in visited:
                    continue
                visited.add(lane.target)
                if network.node(lane.target).type == NodeType.MARKET:
                    markets.add(lane.target)
                else:
                    nxt.append(lane.target)
        frontier = nxt
    return markets


# --------------------------------------------------------------------------
# Exposure (lead-time cover gap) — used by scoring.py
# --------------------------------------------------------------------------


def exposure_days_for_node(network: Network, node_id: str) -> float:
    """
    Lead-time cover gap for a node: max(0, inbound_lead_time - days_of_cover)
    across its primary inbound lanes/SKUs. For nodes that hold no inventory
    themselves (suppliers), this looks at the *downstream* node's cover
    instead — a supplier disruption only bites once the downstream buffer
    runs out.
    """
    node = network.node(node_id)
    if node.inventory_days_of_cover:
        best = 0.0
        for lane in network.lanes_into(node_id):
            if not lane.primary:
                continue
            for sku_id in lane.skus:
                cover = node.inventory_days_of_cover.get(sku_id)
                if cover is None:
                    continue
                gap = max(0.0, lane.lead_time_days - cover)
                best = max(best, gap)
        return best

    # No inventory of its own (e.g. a supplier): look at what it feeds.
    best = 0.0
    for lane in network.lanes_out_of(node_id):
        if not lane.primary:
            continue
        downstream = network.node(lane.target)
        for sku_id in lane.skus:
            cover = downstream.inventory_days_of_cover.get(sku_id)
            if cover is None:
                continue
            gap = max(0.0, lane.lead_time_days - cover)
            best = max(best, gap)
    return best


def lane_flow_units(lane: Lane) -> float:
    """
    Approximate weekly flow on a lane, used by dashboard.py to scale lane
    widths on the network map. Primary lanes are assumed to run at their
    full stated capacity in steady state; alternate lanes carry no
    everyday flow (they only activate under a scenario).
    """
    return lane.capacity_units_per_week if lane.primary else 0.0
