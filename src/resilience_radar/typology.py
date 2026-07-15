"""
typology.py — the risk taxonomy and a deterministic, rule-based classifier.

Resilience practice (see Sheffi/Simchi-Levi's supply chain risk work)
classifies disruptions along two independent axes:

- **source**: *where* the disruption originates — supplier, logistics,
  geopolitical, natural-hazard, cyber, demand, regulatory, financial, or
  purely internal-operational.
- **consequence**: *how bad* it is once it lands — a `deviation` (minor,
  everyday noise), a `disruption` (a real but recoverable hit), or a
  `disaster` (severe, rare). This maps onto the frequency axis used in
  resilience engineering: LIHF (low-impact, high-frequency — the everyday
  deviations) vs. HILF (high-impact, low-frequency — the disasters a
  resilience program actually exists to prepare for).

`classify_event` is a deterministic keyword + network-alias matcher —
no ML, no network calls, fully unit-testable. It never guesses: an event
with no keyword hits and no node/lane alias hits is classified as a
low-confidence `internal-operational` / `deviation`, which `scoring.py`
will naturally down-score.

An optional LLM-backed classifier (`llm.py`) can replace this for the
source/consequence call, but node/lane matching always runs through the
same alias matcher here — that part is structural, not judgment-based.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import ConsequenceClass, Event, FrequencyClass, Network, SourceCategory

# --------------------------------------------------------------------------
# Keyword rules — ordered by priority; first category with a hit wins.
# Ordering matters for events that could plausibly match more than one
# category (e.g. "export controls" is geopolitical before it's regulatory).
# --------------------------------------------------------------------------

SOURCE_KEYWORD_RULES: list[tuple[SourceCategory, tuple[str, ...]]] = [
    (
        SourceCategory.NATURAL_HAZARD,
        (
            "typhoon", "hurricane", "flood", "flooding", "earthquake", "wildfire",
            "monsoon", "heatwave", "storm", "el nino", "el niño",
        ),
    ),
    (
        SourceCategory.CYBER,
        (
            "cyber", "ransomware", "cyberattack", "data breach", "malware",
            "intrusion", "hacked", "hacking",
        ),
    ),
    (
        SourceCategory.FINANCIAL,
        (
            "insolvency", "bankruptcy", "creditor protection", "credit downgrade",
            "financial distress", "currency", "margins", "leasing rates",
        ),
    ),
    (
        SourceCategory.GEOPOLITICAL,
        (
            "export control", "sanctions", "trade war", "border closure",
            "conflict", "trade delegation", "free trade agreement", "diplomatic",
        ),
    ),
    (
        SourceCategory.REGULATORY,
        (
            "tariff", "regulation", "compliance", "licensing requirement",
            "recall mandate", "policy",
        ),
    ),
    (
        SourceCategory.LOGISTICS,
        (
            "port congestion", "congestion", "strike", "dockworker", "labor shortage",
            "labor unrest", "port closure", "freight rate", "vessel queue",
            "warehouse", "cargo capacity", "crane malfunction", "shipping",
        ),
    ),
    (
        SourceCategory.DEMAND,
        (
            "demand surge", "demand spike", "viral", "orders", "consumer confidence",
            "competitor", "rival product",
        ),
    ),
    (
        SourceCategory.SUPPLIER,
        (
            "supplier", "chip shortage", "component shortage", "diversify supplier",
        ),
    ),
    (
        SourceCategory.INTERNAL_OPERATIONAL,
        (
            "recall", "quality control", "defect", "software glitch", "internal",
        ),
    ),
]

CONSEQUENCE_KEYWORD_RULES: list[tuple[ConsequenceClass, tuple[str, ...]]] = [
    (
        ConsequenceClass.DISASTER,
        (
            "typhoon", "hurricane", "earthquake", "bankruptcy", "insolvency",
            "creditor protection", "ransomware", "shutdown", "destroyed", "closure",
        ),
    ),
    (
        ConsequenceClass.DISRUPTION,
        (
            "strike", "congestion", "delay", "delays", "shortage", "recall",
            "surge", "spike", "intrusion", "export control", "malfunction",
        ),
    ),
    (
        ConsequenceClass.DEVIATION,
        (
            "easing", "minor", "modest", "routine", "resolved", "preliminary",
            "steady", "ticks up", "no material", "not yet binding",
        ),
    ),
]


@dataclass
class Classification:
    """The result of classifying one `Event` against a `Network`."""

    source_category: SourceCategory
    consequence_class: ConsequenceClass
    frequency_class: FrequencyClass
    matched_node_ids: list[str] = field(default_factory=list)
    matched_lane_ids: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)


def _text(event: Event) -> str:
    return f"{event.headline} {event.body}".lower()


def match_nodes(event: Event, network: Network) -> list[str]:
    """Node ids whose name or any alias appears (case-insensitively) in the event text."""
    text = _text(event)
    hits: list[str] = []
    for node in network.nodes:
        candidates = [node.name, *node.aliases]
        if any(c.lower() in text for c in candidates):
            hits.append(node.id)
    return hits


def match_lanes(event: Event, network: Network) -> list[str]:
    """Lane ids whose alias appears (case-insensitively) in the event text."""
    text = _text(event)
    hits: list[str] = []
    for lane in network.lanes:
        if any(a.lower() in text for a in lane.aliases):
            hits.append(lane.id)
    return hits


def classify_source(event: Event) -> tuple[SourceCategory, list[str]]:
    """Deterministic keyword classification for the source axis."""
    text = _text(event)
    for category, keywords in SOURCE_KEYWORD_RULES:
        hits = [kw for kw in keywords if kw in text]
        if hits:
            return category, hits
    return SourceCategory.INTERNAL_OPERATIONAL, []


def classify_consequence(event: Event) -> tuple[ConsequenceClass, list[str]]:
    """Deterministic keyword classification for the consequence axis."""
    text = _text(event)
    for consequence, keywords in CONSEQUENCE_KEYWORD_RULES:
        hits = [kw for kw in keywords if kw in text]
        if hits:
            return consequence, hits
    return ConsequenceClass.DEVIATION, []


def frequency_class_for(
    source: SourceCategory, consequence: ConsequenceClass
) -> FrequencyClass:
    """
    HILF (high-impact, low-frequency) for the archetypal tail-risk source
    categories or any disaster-level consequence; LIHF otherwise.
    """
    hilf_sources = {
        SourceCategory.NATURAL_HAZARD,
        SourceCategory.GEOPOLITICAL,
        SourceCategory.CYBER,
        SourceCategory.FINANCIAL,
    }
    if consequence == ConsequenceClass.DISASTER or source in hilf_sources:
        return FrequencyClass.HILF
    return FrequencyClass.LIHF


def classify_event(event: Event, network: Network) -> Classification:
    """
    Classify one event: source axis, consequence axis, frequency class, and
    which nodes/lanes it structurally touches. Fully deterministic.
    """
    source, source_hits = classify_source(event)
    consequence, consequence_hits = classify_consequence(event)
    frequency = frequency_class_for(source, consequence)
    return Classification(
        source_category=source,
        consequence_class=consequence,
        frequency_class=frequency,
        matched_node_ids=match_nodes(event, network),
        matched_lane_ids=match_lanes(event, network),
        matched_keywords=sorted(set(source_hits) | set(consequence_hits)),
    )
