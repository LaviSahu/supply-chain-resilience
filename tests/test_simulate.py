"""
Tests for simulate.py — the time-phased propagation engine.

The core case (`TestKnownToyNetwork`) is hand-computed against
`fixtures.simple_chain_network()`:

- DC inventory_days_of_cover = 7 days = exactly one week of the market's
  100 units/week demand -> initial inventory = 100 units.
- Scenario disrupts the supplier node (SUP) at capacity_pct=0.0 for
  weeks 1-2 (a hard stop on the SUP->PLANT lane).

Week-by-week by hand:
  Week 1: inventory=100, upstream supply_in=0 (SUP->PLANT lane is cut) ->
          available_pool=100, demand=100 -> fully shipped, service=100%.
          Inventory drawn to 0.
  Week 2: inventory=0, upstream still cut -> available_pool=0, demand=100
          -> nothing shipped, service=0%. This is the first dip.
  Week 3: outage over (outage_weeks=2) -> upstream restored, supply_in=100
          -> available_pool=100, demand=100 -> fully shipped, service=100%.
          Recovery.

So TTS (full weeks survived before the first dip) = 1, and TTR (weeks
from the dip at week 2 to recovery at week 3) = 1.
"""

import unittest

import _bootstrap  # noqa: F401  (sys.path shim, must run before resilience_radar imports)

from resilience_radar import simulate
from resilience_radar.models import Scenario

from fixtures import simple_chain_network


class TestKnownToyNetwork(unittest.TestCase):
    def setUp(self) -> None:
        self.network = simple_chain_network()
        self.scenario = Scenario(
            id="toy-outage",
            name="Toy Supplier Outage",
            disrupted_element="SUP",
            element_kind="node",
            outage_weeks=2,
            capacity_pct=0.0,
        )

    def test_baseline_is_full_service_every_week(self) -> None:
        result = simulate.run_scenario(self.network, self.scenario)
        for week in result.baseline_weeks:
            self.assertAlmostEqual(week.service_level, 1.0, places=4)
        self.assertAlmostEqual(result.baseline_service_level, 1.0, places=4)

    def test_week_by_week_service_levels(self) -> None:
        result = simulate.run_scenario(self.network, self.scenario)
        weeks = {w.week: w for w in result.scenario_weeks}
        self.assertAlmostEqual(weeks[1].service_level, 1.0, places=4)
        self.assertAlmostEqual(weeks[2].service_level, 0.0, places=4)
        self.assertAlmostEqual(weeks[3].service_level, 1.0, places=4)

    def test_tts_and_ttr_hand_computed(self) -> None:
        result = simulate.run_scenario(self.network, self.scenario)
        self.assertEqual(result.tts, 1)
        self.assertEqual(result.ttr, 1)

    def test_lost_revenue_only_in_dip_week(self) -> None:
        result = simulate.run_scenario(self.network, self.scenario)
        weeks = {w.week: w for w in result.scenario_weeks}
        self.assertAlmostEqual(weeks[1].lost_revenue, 0.0, places=2)
        self.assertAlmostEqual(weeks[2].lost_revenue, 1000.0, places=2)  # 100 units * $10
        self.assertAlmostEqual(weeks[3].lost_revenue, 0.0, places=2)

    def test_worst_service_level(self) -> None:
        result = simulate.run_scenario(self.network, self.scenario)
        self.assertAlmostEqual(result.worst_service_level, 0.0, places=4)


class TestNeverRecovers(unittest.TestCase):
    def test_ttr_none_when_outage_spans_whole_horizon(self) -> None:
        network = simple_chain_network()
        scenario = Scenario(
            id="permanent-outage",
            name="Permanent Outage",
            disrupted_element="SUP",
            element_kind="node",
            outage_weeks=simulate.HORIZON_WEEKS,  # outage never ends within the horizon
            capacity_pct=0.0,
        )
        result = simulate.run_scenario(network, scenario)
        self.assertIsNone(result.ttr)


class TestPresetScenarios(unittest.TestCase):
    def test_exactly_three_presets(self) -> None:
        self.assertEqual(
            set(simulate.PRESET_SCENARIOS),
            {"supplier-failure", "port-closure", "demand-spike"},
        )

    def test_get_preset_unknown_raises(self) -> None:
        with self.assertRaises(ValueError):
            simulate.get_preset("does-not-exist")

    def test_presets_reference_real_network_elements(self) -> None:
        from resilience_radar import graph

        network = graph.load_network("data/network.json")
        node_ids = {n.id for n in network.nodes}
        lane_ids = {l.id for l in network.lanes}
        for scenario in simulate.PRESET_SCENARIOS.values():
            valid_ids = node_ids if scenario.element_kind == "node" else lane_ids
            self.assertIn(scenario.disrupted_element, valid_ids)

    def test_run_all_presets_returns_three_results(self) -> None:
        from resilience_radar import graph

        network = graph.load_network("data/network.json")
        results = simulate.run_all_presets(network)
        self.assertEqual(len(results), 3)
        for result in results.values():
            self.assertEqual(len(result.scenario_weeks), simulate.HORIZON_WEEKS)
            self.assertEqual(len(result.baseline_weeks), simulate.HORIZON_WEEKS)


if __name__ == "__main__":
    unittest.main()
