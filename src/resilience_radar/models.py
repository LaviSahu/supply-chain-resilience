"""
models.py — the shared vocabulary of Resilience Radar.

A resilience program only works if everyone (suppliers, planners, ops,
executives) agrees on what a "risk" is, what a "node" is, and how a
what-if "scenario" is described. This module is that shared vocabulary,
expressed as typed dataclasses instead of prose:

- Network primitives: `Sku`, `Node`, `Lane`, `Network` — the physical/
  commercial graph goods move through (suppliers -> plants -> DCs ->
  markets), the classic three-tier consumer-goods topology.
- Signal primitives: `Event` — a single piece of raw disruption news
  ingested from the outside world (a headline + body + metadata).
- Risk primitives: `Risk` — what `typology.py` + `scoring.py` turn an
  `Event` into: a scored, tiered, network-linked risk register entry.
- Simulation primitives: `Scenario`, `WeekResult`, `SimResult` — the
  time-phased what-if machinery in `simulate.py` speaks this language.

Everything here is a plain `@dataclass`: no behavior, no globals, just
shape. Behavior lives in the modules named after the verbs (classify,
score, simulate, mitigate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


# --------------------------------------------------------------------------
# Enumerations — the controlled vocabularies used across the engine.
# --------------------------------------------------------------------------


class NodeType(str, Enum):
    """The four echelons of a classic three-tier consumer-goods network."""

    SUPPLIER = "supplier"
    PLANT = "plant"
    DC = "dc"
    MARKET = "market"


class LaneMode(str, Enum):
    """Transport mode of a lane; affects lead time and cost intuition."""

    OCEAN = "ocean"
    ROAD = "road"
    RAIL = "rail"
    AIR = "air"
    MULTIMODAL = "multimodal"


class SourceCategory(str, Enum):
    """
    The "source" axis of the risk taxonomy: where a disruption originates.
    See typology.py for the classifier that assigns this from event text.
    """

    INTERNAL_OPERATIONAL = "internal-operational"
    SUPPLIER = "supplier"
    LOGISTICS = "logistics"
    GEOPOLITICAL = "geopolitical"
    NATURAL_HAZARD = "natural-hazard"
    CYBER = "cyber"
    DEMAND = "demand"
    REGULATORY = "regulatory"
    FINANCIAL = "financial"


class ConsequenceClass(str, Enum):
    """
    The "consequence" axis: how severe the disruption is once it lands.
    Deviation < disruption < disaster, roughly in order of severity and
    inversely in order of frequency.
    """

    DEVIATION = "deviation"
    DISRUPTION = "disruption"
    DISASTER = "disaster"


class FrequencyClass(str, Enum):
    """
    LIHF = low-impact, high-frequency (the everyday noise of operations).
    HILF = high-impact, low-frequency (the tail-risk events resilience
    programs exist to prepare for).
    """

    LIHF = "LIHF"
    HILF = "HILF"


class RiskTier(str, Enum):
    """Coarse severity banding of `risk_score` for console/dashboard color."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# --------------------------------------------------------------------------
# Network primitives
# --------------------------------------------------------------------------


@dataclass
class Sku:
    """A stock-keeping unit: the thing that actually earns revenue."""

    id: str
    name: str
    revenue_per_unit: float


@dataclass
class Node:
    """
    A point in the physical network: a supplier, plant, DC, or market.

    `x`/`y` are hand-set canvas coordinates (see data/network.json) used
    only for the SVG network map — they carry no simulation meaning.

    `inventory_days_of_cover` applies to plants/DCs that hold stock
    (sku_id -> days). `weekly_demand` applies to markets (sku_id ->
    units/week). Both default empty so a single Node shape covers every
    node type without subclassing.
    """

    id: str
    name: str
    type: NodeType
    region: str
    country: str
    x: float
    y: float
    aliases: list[str] = field(default_factory=list)
    tier: Optional[int] = None
    category: Optional[str] = None
    port_dependency: Optional[str] = None
    inventory_days_of_cover: dict[str, float] = field(default_factory=dict)
    weekly_demand: dict[str, float] = field(default_factory=dict)


@dataclass
class Lane:
    """
    A directed transport link between two nodes carrying one or more SKUs.

    `primary=True` lanes represent the network's everyday flow; the
    `simulate.py` engine treats non-primary (`primary=False`) lanes as
    alternate-sourcing capacity that can be activated after
    `switch_lag_weeks` once a primary lane/node is disrupted.
    """

    id: str
    source: str
    target: str
    mode: LaneMode
    lead_time_days: int
    capacity_units_per_week: float
    skus: list[str]
    primary: bool = True
    switch_lag_weeks: int = 0
    aliases: list[str] = field(default_factory=list)


@dataclass
class Network:
    """The full modeled supply network: nodes, lanes, and the SKU catalog."""

    company: str
    nodes: list[Node]
    lanes: list[Lane]
    skus: list[Sku]

    def node(self, node_id: str) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(f"unknown node id: {node_id!r}")

    def lane(self, lane_id: str) -> Lane:
        for l in self.lanes:
            if l.id == lane_id:
                return l
        raise KeyError(f"unknown lane id: {lane_id!r}")

    def sku(self, sku_id: str) -> Sku:
        for s in self.skus:
            if s.id == sku_id:
                return s
        raise KeyError(f"unknown sku id: {sku_id!r}")

    def lanes_into(self, node_id: str) -> list[Lane]:
        return [l for l in self.lanes if l.target == node_id]

    def lanes_out_of(self, node_id: str) -> list[Lane]:
        return [l for l in self.lanes if l.source == node_id]


# --------------------------------------------------------------------------
# Signal primitives
# --------------------------------------------------------------------------


@dataclass
class Event:
    """A single raw disruption-feed item, before any classification."""

    id: str
    date: date
    headline: str
    body: str
    source: str
    region: str
    confidence: float


# --------------------------------------------------------------------------
# Risk primitives
# --------------------------------------------------------------------------


@dataclass
class Risk:
    """
    A scored, network-linked risk register entry: what an `Event` becomes
    after `typology.classify_event` and `scoring.score_event` have run.
    """

    id: str
    event_id: str
    source_category: SourceCategory
    consequence_class: ConsequenceClass
    frequency_class: FrequencyClass
    affected_node_ids: list[str]
    affected_lane_ids: list[str]
    likelihood: int
    impact: int
    risk_score: int
    tier: RiskTier
    exposure_days: float
    value_at_risk: float
    headline: str
    rationale: str
    event_date: date


# --------------------------------------------------------------------------
# Simulation primitives
# --------------------------------------------------------------------------


@dataclass
class Scenario:
    """
    A what-if disruption to simulate.

    `disrupted_element` is a node id or lane id, disambiguated by
    `element_kind`. `capacity_pct` is the fraction of *normal* throughput
    that survives on every lane touching the disrupted element while the
    outage is active (0.0 = full stop, 1.0 = no supply-side effect).
    `demand_shock_pct` (e.g. 0.4 for +40%) is applied to demand at the
    disrupted element when it is a market node — used for the
    demand-spike archetype.
    """

    id: str
    name: str
    disrupted_element: str
    element_kind: str  # "node" | "lane"
    outage_weeks: int
    capacity_pct: float
    demand_shock_pct: float = 0.0
    description: str = ""


@dataclass
class WeekResult:
    """One week of a simulated (or baseline) time series."""

    week: int
    service_level: float
    lost_revenue: float
    inventory_position: float


@dataclass
class SimResult:
    """The full output of one scenario run: baseline vs. scenario, scored."""

    scenario_id: str
    scenario_name: str
    baseline_weeks: list[WeekResult]
    scenario_weeks: list[WeekResult]
    ttr: Optional[int]
    tts: int
    total_lost_revenue: float
    baseline_service_level: float
    worst_service_level: float
    outage_start_week: int
    outage_end_week: int


# --------------------------------------------------------------------------
# JSON helpers — shared by radar.py / simulate.py / dashboard.py so the
# dashboard's embedded <script> DATA blob and output/*.json files use one
# consistent, dependency-free serialization convention.
# --------------------------------------------------------------------------


def jsonable(obj):
    """
    Recursively convert dataclasses / Enums / dates / dicts / lists into
    plain JSON-serializable structures. Used instead of a library like
    `pydantic` to keep the project stdlib-only.
    """
    from dataclasses import is_dataclass, fields

    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj
