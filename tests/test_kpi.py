"""Tests for kpi.py — the resilience KPI catalog."""

import unittest
from datetime import date

import _bootstrap  # noqa: F401  (sys.path shim, must run before resilience_radar imports)

from resilience_radar import graph, kpi, simulate
from resilience_radar.models import (
    ConsequenceClass,
    FrequencyClass,
    Risk,
    RiskTier,
    SourceCategory,
)


def _risk(risk_score: int, tier: RiskTier, var: float = 1000.0) -> Risk:
    return Risk(
        id=f"RISK-{risk_score}-{tier.value}",
        event_id="EVT-X",
        source_category=SourceCategory.SUPPLIER,
        consequence_class=ConsequenceClass.DISRUPTION,
        frequency_class=FrequencyClass.LIHF,
        affected_node_ids=[],
        affected_lane_ids=[],
        likelihood=3,
        impact=3,
        risk_score=risk_score,
        tier=tier,
        exposure_days=0.0,
        value_at_risk=var,
        headline="Test",
        rationale="test",
        event_date=date(2026, 1, 1),
    )


class TestKpiPrimitives(unittest.TestCase):
    def test_risk_severity_index_is_mean(self) -> None:
        risks = [_risk(10, RiskTier.HIGH), _risk(20, RiskTier.CRITICAL)]
        self.assertEqual(kpi.risk_severity_index(risks), 15.0)

    def test_risk_severity_index_empty(self) -> None:
        self.assertEqual(kpi.risk_severity_index([]), 0.0)

    def test_revenue_at_risk_sums_var(self) -> None:
        risks = [_risk(10, RiskTier.HIGH, var=500.0), _risk(5, RiskTier.LOW, var=250.0)]
        self.assertEqual(kpi.revenue_at_risk(risks), 750.0)


class TestKpiCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.network = graph.load_network("data/network.json")
        cls.sim_results = simulate.run_all_presets(cls.network)

    def test_compute_kpis_full_catalog(self) -> None:
        risks = [_risk(20, RiskTier.CRITICAL), _risk(10, RiskTier.HIGH), _risk(4, RiskTier.LOW)]
        kpis = kpi.compute_kpis(self.network, risks, self.sim_results)

        expected_keys = {
            "service_level",
            "revenue_at_risk",
            "rsi",
            "open_risks",
            "min_tts",
            "single_source_nodes",
            "risk_density",
            "worst_ttr",
        }
        self.assertEqual(set(kpis), expected_keys)

        self.assertAlmostEqual(kpis["service_level"].value, 100.0, places=2)  # baseline is always ~100%
        self.assertEqual(kpis["open_risks"].value, 3.0)
        self.assertGreaterEqual(kpis["single_source_nodes"].value, 1.0)  # Rhineland Precision is single-sourced

    def test_worst_ttr_sentinel_when_none(self) -> None:
        # Force a "never recovers" scenario via a permanent outage.
        from resilience_radar.models import Scenario

        never_recovers = simulate.run_scenario(
            self.network,
            Scenario(
                id="permanent",
                name="Permanent",
                disrupted_element="SUP-DE-PREC",
                element_kind="node",
                outage_weeks=simulate.HORIZON_WEEKS,
                capacity_pct=0.0,
            ),
        )
        sim_results = {"permanent": never_recovers}
        kpis = kpi.compute_kpis(self.network, [], sim_results)
        self.assertEqual(kpis["worst_ttr"].value, -1.0)


if __name__ == "__main__":
    unittest.main()
