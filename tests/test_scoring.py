"""Tests for scoring.py — risk arithmetic (likelihood x impact = risk_score, VaR)."""

import unittest
from datetime import date

import _bootstrap  # noqa: F401  (sys.path shim, must run before resilience_radar imports)

from resilience_radar.models import ConsequenceClass, Event, FrequencyClass, RiskTier, SourceCategory
from resilience_radar.scoring import (
    _clamp,
    affected_criticality,
    expected_outage_weeks,
    impact_score,
    likelihood_score,
    score_event,
    tier_for_score,
    value_at_risk,
)
from resilience_radar.typology import Classification

from fixtures import simple_chain_network


def _event(confidence: float) -> Event:
    return Event(
        id="EVT-1",
        date=date(2026, 1, 1),
        headline="Test event",
        body="",
        source="wire",
        region="Global",
        confidence=confidence,
    )


class TestClamp(unittest.TestCase):
    def test_clamps_within_range(self) -> None:
        self.assertEqual(_clamp(0.0, 1, 5), 1)
        self.assertEqual(_clamp(10.0, 1, 5), 5)
        self.assertEqual(_clamp(3.4, 1, 5), 3)


class TestLikelihoodScore(unittest.TestCase):
    def test_high_confidence_no_adjustment(self) -> None:
        classification = Classification(
            source_category=SourceCategory.NATURAL_HAZARD,
            consequence_class=ConsequenceClass.DISASTER,
            frequency_class=FrequencyClass.HILF,
        )
        # confidence 1.0 * 5 = 5, no adjustment for NATURAL_HAZARD -> clamp to 5
        self.assertEqual(likelihood_score(_event(1.0), classification), 5)

    def test_geopolitical_adjustment_lowers_score(self) -> None:
        classification = Classification(
            source_category=SourceCategory.GEOPOLITICAL,
            consequence_class=ConsequenceClass.DISRUPTION,
            frequency_class=FrequencyClass.HILF,
        )
        # confidence 0.8 * 5 = 4.0, geopolitical adjustment -1 -> 3
        self.assertEqual(likelihood_score(_event(0.8), classification), 3)

    def test_floor_at_one(self) -> None:
        classification = Classification(
            source_category=SourceCategory.REGULATORY,
            consequence_class=ConsequenceClass.DEVIATION,
            frequency_class=FrequencyClass.LIHF,
        )
        # confidence 0.1 * 5 = 0.5, regulatory adjustment -1 -> -0.5, clamp to 1
        self.assertEqual(likelihood_score(_event(0.1), classification), 1)


class TestImpactScore(unittest.TestCase):
    def test_high_severity_scores_five(self) -> None:
        self.assertEqual(impact_score(criticality=0.5, outage_weeks=8.0), 5)  # severity 4.0

    def test_low_severity_scores_one(self) -> None:
        self.assertEqual(impact_score(criticality=0.01, outage_weeks=0.5), 1)  # severity 0.005

    def test_boundary_thresholds(self) -> None:
        self.assertEqual(impact_score(criticality=0.3, outage_weeks=1.0), 3)  # severity 0.3 -> bucket 3 (>=0.25)
        self.assertEqual(impact_score(criticality=0.6, outage_weeks=1.0), 4)  # severity 0.6 -> bucket 4 (>=0.6)


class TestTierForScore(unittest.TestCase):
    def test_tiers(self) -> None:
        self.assertEqual(tier_for_score(25), RiskTier.CRITICAL)
        self.assertEqual(tier_for_score(20), RiskTier.CRITICAL)
        self.assertEqual(tier_for_score(15), RiskTier.HIGH)
        self.assertEqual(tier_for_score(8), RiskTier.MEDIUM)
        self.assertEqual(tier_for_score(2), RiskTier.LOW)


class TestExpectedOutageWeeks(unittest.TestCase):
    def test_maps_consequence_to_weeks(self) -> None:
        for consequence, expected in (
            (ConsequenceClass.DEVIATION, 0.5),
            (ConsequenceClass.DISRUPTION, 2.5),
            (ConsequenceClass.DISASTER, 8.0),
        ):
            classification = Classification(
                source_category=SourceCategory.SUPPLIER,
                consequence_class=consequence,
                frequency_class=FrequencyClass.LIHF,
            )
            self.assertEqual(expected_outage_weeks(classification), expected)


class TestAffectedCriticality(unittest.TestCase):
    def test_no_match_gets_floor(self) -> None:
        classification = Classification(
            source_category=SourceCategory.INTERNAL_OPERATIONAL,
            consequence_class=ConsequenceClass.DEVIATION,
            frequency_class=FrequencyClass.LIHF,
        )
        self.assertEqual(affected_criticality(classification, {}, {}), 0.01)

    def test_takes_max_across_matches(self) -> None:
        classification = Classification(
            source_category=SourceCategory.SUPPLIER,
            consequence_class=ConsequenceClass.DISRUPTION,
            frequency_class=FrequencyClass.LIHF,
            matched_node_ids=["A", "B"],
        )
        crit = affected_criticality(classification, {"A": 0.2, "B": 0.9}, {})
        self.assertEqual(crit, 0.9)


class TestValueAtRisk(unittest.TestCase):
    def test_var_scales_with_criticality_and_weeks(self) -> None:
        network = simple_chain_network()
        # total_weekly_revenue = 100 units * $10 = $1000
        var = value_at_risk(criticality=0.5, network=network, outage_weeks=2.0)
        self.assertAlmostEqual(var, 0.5 * 1000.0 * 2.0)


class TestScoreEvent(unittest.TestCase):
    def test_full_pipeline_on_matched_event(self) -> None:
        network = simple_chain_network()
        event = Event(
            id="EVT-DC",
            date=date(2026, 1, 1),
            headline="Typhoon forces DC to halt shipments",
            body="Total shutdown expected at DC for several weeks.",
            source="wire",
            region="Asia",
            confidence=0.9,
        )
        from resilience_radar.typology import classify_event

        classification = classify_event(event, network)
        risk = score_event(event, classification, network)

        self.assertEqual(risk.id, "RISK-EVT-DC")
        self.assertEqual(risk.risk_score, risk.likelihood * risk.impact)
        self.assertIn(risk.tier, (RiskTier.CRITICAL, RiskTier.HIGH, RiskTier.MEDIUM, RiskTier.LOW))
        self.assertGreater(risk.value_at_risk, 0.0)
        self.assertIn("DC", risk.affected_node_ids)


if __name__ == "__main__":
    unittest.main()
