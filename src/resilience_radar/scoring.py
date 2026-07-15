"""
scoring.py — turning a classified event into a scored, tiered risk.

Classic risk scoring: `risk_score = likelihood x impact`, both on a 1-5
scale, giving a 1-25 score bucketed into CRITICAL/HIGH/MEDIUM/LOW tiers.
This module is where that arithmetic lives, plus the two supporting
numbers a resilience desk actually cares about:

- **exposure_days**: the lead-time cover gap (`graph.exposure_days_for_node`)
  — how many days of inventory buffer are missing relative to how long
  it takes to replenish. Zero or negative means the buffer fully absorbs
  the lead time; positive means a stockout is structurally possible.
- **value_at_risk (VaR)**: weekly revenue flowing through the affected
  element, multiplied by the expected outage duration implied by the
  event's consequence class.

Likelihood blends the event's stated `confidence` with a per-source
reliability adjustment (some source categories are inherently noisier
signals than others). Impact blends the affected node's network
criticality (from `graph.py`) with the expected outage length — a
disruption at a node nobody depends on scores low impact no matter how
severe the event sounds.
"""

from __future__ import annotations

from . import graph
from .models import ConsequenceClass, Event, Network, Risk, RiskTier, SourceCategory
from .typology import Classification

# Source categories whose reporting tends to be noisier / less directly
# actionable than others; applied as a small likelihood adjustment.
SOURCE_RELIABILITY_ADJUSTMENT: dict[SourceCategory, int] = {
    SourceCategory.NATURAL_HAZARD: 0,
    SourceCategory.CYBER: 0,
    SourceCategory.FINANCIAL: 0,
    SourceCategory.LOGISTICS: 0,
    SourceCategory.GEOPOLITICAL: -1,
    SourceCategory.REGULATORY: -1,
    SourceCategory.DEMAND: 0,
    SourceCategory.SUPPLIER: 0,
    SourceCategory.INTERNAL_OPERATIONAL: 0,
}

# Expected outage duration (weeks) implied purely by consequence severity.
# Deterministic lookup rather than free-text extraction — see
# implementation-notes.md for the rationale.
EXPECTED_OUTAGE_WEEKS: dict[ConsequenceClass, float] = {
    ConsequenceClass.DEVIATION: 0.5,
    ConsequenceClass.DISRUPTION: 2.5,
    ConsequenceClass.DISASTER: 8.0,
}

# risk_score = likelihood(1-5) * impact(1-5), range 1-25.
TIER_THRESHOLDS: list[tuple[int, RiskTier]] = [
    (20, RiskTier.CRITICAL),
    (12, RiskTier.HIGH),
    (6, RiskTier.MEDIUM),
    (1, RiskTier.LOW),
]


def _clamp(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, round(value)))


def likelihood_score(event: Event, classification: Classification) -> int:
    """1-5, from event confidence (0-1) plus a source-reliability adjustment."""
    base = event.confidence * 5
    adjustment = SOURCE_RELIABILITY_ADJUSTMENT.get(classification.source_category, 0)
    return _clamp(base + adjustment, 1, 5)


def expected_outage_weeks(classification: Classification) -> float:
    return EXPECTED_OUTAGE_WEEKS[classification.consequence_class]


def affected_criticality(
    classification: Classification, node_criticality: dict[str, float], lane_criticality: dict[str, float]
) -> float:
    """
    Max criticality across every node/lane the event structurally touches.
    Events that match nothing get a small nonzero floor so they still
    produce a (low) score rather than a hard zero.
    """
    values = [node_criticality.get(nid, 0.0) for nid in classification.matched_node_ids]
    values += [lane_criticality.get(lid, 0.0) for lid in classification.matched_lane_ids]
    if not values:
        return 0.01
    return max(values)


def impact_score(criticality: float, outage_weeks: float) -> int:
    """
    1-5, bucketed from criticality x outage_weeks (a "severity-days" proxy
    combining how much revenue depends on the element and how long it
    would plausibly be out).
    """
    severity = criticality * outage_weeks
    if severity >= 1.5:
        return 5
    if severity >= 0.6:
        return 4
    if severity >= 0.25:
        return 3
    if severity >= 0.08:
        return 2
    return 1


def tier_for_score(risk_score: int) -> RiskTier:
    for threshold, tier in TIER_THRESHOLDS:
        if risk_score >= threshold:
            return tier
    return RiskTier.LOW


def value_at_risk(criticality: float, network: Network, outage_weeks: float) -> float:
    """Weekly revenue attributable to the affected element x expected outage weeks."""
    weekly_revenue = criticality * graph.total_weekly_revenue(network)
    return round(weekly_revenue * outage_weeks, 2)


def score_event(
    event: Event,
    classification: Classification,
    network: Network,
    node_criticality: dict[str, float] | None = None,
    lane_criticality: dict[str, float] | None = None,
) -> Risk:
    """Score one classified event into a full `Risk` register entry."""
    node_crit = node_criticality if node_criticality is not None else graph.node_criticality(network)
    lane_crit = lane_criticality if lane_criticality is not None else graph.lane_criticality(network)

    outage_weeks = expected_outage_weeks(classification)
    criticality = affected_criticality(classification, node_crit, lane_crit)

    likelihood = likelihood_score(event, classification)
    impact = impact_score(criticality, outage_weeks)
    risk_score = likelihood * impact
    tier = tier_for_score(risk_score)

    exposure = max(
        (graph.exposure_days_for_node(network, nid) for nid in classification.matched_node_ids),
        default=0.0,
    )
    var = value_at_risk(criticality, network, outage_weeks)

    affected_desc = ", ".join(classification.matched_node_ids + classification.matched_lane_ids) or "network-wide (no specific element matched)"
    rationale = (
        f"{classification.source_category.value}/{classification.consequence_class.value} "
        f"({classification.frequency_class.value}); affects {affected_desc}; "
        f"confidence={event.confidence:.2f}, criticality={criticality:.3f}, "
        f"expected outage={outage_weeks:g}w"
    )

    return Risk(
        id=f"RISK-{event.id}",
        event_id=event.id,
        source_category=classification.source_category,
        consequence_class=classification.consequence_class,
        frequency_class=classification.frequency_class,
        affected_node_ids=classification.matched_node_ids,
        affected_lane_ids=classification.matched_lane_ids,
        likelihood=likelihood,
        impact=impact,
        risk_score=risk_score,
        tier=tier,
        exposure_days=exposure,
        value_at_risk=var,
        headline=event.headline,
        rationale=rationale,
        event_date=event.date,
    )
