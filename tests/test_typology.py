"""Tests for typology.py — the deterministic keyword/alias classifier."""

import unittest
from datetime import date

import _bootstrap  # noqa: F401  (sys.path shim, must run before resilience_radar imports)

from resilience_radar.models import ConsequenceClass, Event, FrequencyClass, SourceCategory
from resilience_radar.typology import classify_consequence, classify_event, classify_source, match_nodes

from fixtures import simple_chain_network


def _event(headline: str, body: str = "", confidence: float = 0.8) -> Event:
    return Event(
        id="EVT-TEST",
        date=date(2026, 1, 1),
        headline=headline,
        body=body,
        source="test-wire",
        region="Global",
        confidence=confidence,
    )


class TestClassifySource(unittest.TestCase):
    def test_natural_hazard_wins(self) -> None:
        event = _event("Typhoon disrupts Shenzhen electronics production")
        source, hits = classify_source(event)
        self.assertEqual(source, SourceCategory.NATURAL_HAZARD)
        self.assertIn("typhoon", hits)

    def test_cyber(self) -> None:
        event = _event("Ransomware attack cripples supplier IT systems")
        source, _ = classify_source(event)
        self.assertEqual(source, SourceCategory.CYBER)

    def test_financial(self) -> None:
        event = _event("Supplier files for insolvency amid mounting debt")
        source, _ = classify_source(event)
        self.assertEqual(source, SourceCategory.FINANCIAL)

    def test_geopolitical_before_regulatory(self) -> None:
        # "export control" should win as GEOPOLITICAL even though the same
        # text could plausibly be read as REGULATORY — ordering matters.
        event = _event("New export control regime announced by trade ministry")
        source, _ = classify_source(event)
        self.assertEqual(source, SourceCategory.GEOPOLITICAL)

    def test_logistics_strike(self) -> None:
        event = _event("Dockworker strike halts port operations")
        source, _ = classify_source(event)
        self.assertEqual(source, SourceCategory.LOGISTICS)

    def test_demand_surge(self) -> None:
        event = _event("Viral social post drives massive demand surge for hub")
        source, _ = classify_source(event)
        self.assertEqual(source, SourceCategory.DEMAND)

    def test_default_internal_operational(self) -> None:
        event = _event("Quarterly newsletter published with no notable news")
        source, hits = classify_source(event)
        self.assertEqual(source, SourceCategory.INTERNAL_OPERATIONAL)
        self.assertEqual(hits, [])


class TestClassifyConsequence(unittest.TestCase):
    def test_disaster(self) -> None:
        event = _event("Earthquake forces total plant shutdown")
        consequence, _ = classify_consequence(event)
        self.assertEqual(consequence, ConsequenceClass.DISASTER)

    def test_disruption(self) -> None:
        event = _event("Port congestion causes multi-day shipping delays")
        consequence, _ = classify_consequence(event)
        self.assertEqual(consequence, ConsequenceClass.DISRUPTION)

    def test_deviation_default(self) -> None:
        event = _event("Routine maintenance completed with no material impact")
        consequence, _ = classify_consequence(event)
        self.assertEqual(consequence, ConsequenceClass.DEVIATION)


class TestFrequencyClass(unittest.TestCase):
    def test_natural_hazard_is_hilf(self) -> None:
        network = simple_chain_network()
        event = _event("Typhoon forces total shutdown at supplier")
        classification = classify_event(event, network)
        self.assertEqual(classification.frequency_class, FrequencyClass.HILF)

    def test_demand_deviation_is_lihf(self) -> None:
        network = simple_chain_network()
        event = _event("Modest, routine uptick in orders, resolved quickly")
        classification = classify_event(event, network)
        self.assertEqual(classification.frequency_class, FrequencyClass.LIHF)


class TestNodeMatching(unittest.TestCase):
    def test_matches_node_by_name(self) -> None:
        network = simple_chain_network()
        event = _event("Fire reported near Supplier facility", "Supplier operations affected.")
        hits = match_nodes(event, network)
        self.assertIn("SUP", hits)

    def test_no_match_for_unrelated_text(self) -> None:
        network = simple_chain_network()
        event = _event("Global coffee prices tick up slightly")
        hits = match_nodes(event, network)
        self.assertEqual(hits, [])

    def test_classify_event_ties_everything_together(self) -> None:
        network = simple_chain_network()
        event = _event("Typhoon forces Plant to halt operations", "Plant shutdown expected to last weeks.")
        classification = classify_event(event, network)
        self.assertEqual(classification.source_category, SourceCategory.NATURAL_HAZARD)
        self.assertEqual(classification.consequence_class, ConsequenceClass.DISASTER)
        self.assertIn("PLANT", classification.matched_node_ids)


if __name__ == "__main__":
    unittest.main()
