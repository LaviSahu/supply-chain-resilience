"""
Tests for mitigate.py — mitigation ranking sanity.

Ranking is a genuine re-simulation, not a lookup table, so the sanity
checks here assert *structural* properties rather than exact numbers:

- Every playbook action appears exactly once per ranking.
- `net_benefit == avoided_loss - cost` for every result.
- Results are sorted descending by net_benefit.
- A lever with no structural connection to the scenario (dual-sourcing
  under a pure demand-spike, where capacity_pct is already 1.0 and
  dual-source's +0.5 boost is clamped away) should show ~zero avoided
  loss — a genuine negative net_benefit once its cost is included,
  confirming the ranking isn't hand-tuned to always look good.
"""

import unittest

import _bootstrap  # noqa: F401  (sys.path shim, must run before resilience_radar imports)

from resilience_radar import graph, mitigate, simulate


class TestMitigationRankingSanity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.network = graph.load_network("data/network.json")

    def test_every_playbook_action_present_once(self) -> None:
        scenario = simulate.get_preset("port-closure")
        results = mitigate.rank_mitigations(self.network, scenario)
        action_ids = [r.action_id for r in results]
        expected = {a.id for a, _ in mitigate.PLAYBOOK}
        self.assertEqual(set(action_ids), expected)
        self.assertEqual(len(action_ids), len(mitigate.PLAYBOOK))

    def test_net_benefit_arithmetic(self) -> None:
        scenario = simulate.get_preset("supplier-failure")
        results = mitigate.rank_mitigations(self.network, scenario)
        for r in results:
            self.assertAlmostEqual(r.net_benefit, round(r.avoided_loss - r.cost, 2), places=2)

    def test_sorted_descending_by_net_benefit(self) -> None:
        scenario = simulate.get_preset("port-closure")
        results = mitigate.rank_mitigations(self.network, scenario)
        net_benefits = [r.net_benefit for r in results]
        self.assertEqual(net_benefits, sorted(net_benefits, reverse=True))

    def test_at_most_three_recommended_and_all_positive(self) -> None:
        scenario = simulate.get_preset("supplier-failure")
        results = mitigate.rank_mitigations(self.network, scenario)
        recommended = [r for r in results if r.recommended]
        self.assertLessEqual(len(recommended), 3)
        for r in recommended:
            self.assertGreater(r.net_benefit, 0.0)

    def test_dual_source_irrelevant_to_pure_demand_spike(self) -> None:
        # demand-spike has capacity_pct=1.0 already; dual-source's +0.5pp
        # boost clamps to min(1.0, 1.5)=1.0, i.e. no structural change, so
        # avoided_loss should be ~0 and net_benefit strongly negative
        # (just the $180k cost with nothing to show for it).
        scenario = simulate.get_preset("demand-spike")
        results = mitigate.rank_mitigations(self.network, scenario)
        dual_source = next(r for r in results if r.action_id == "dual-source")
        self.assertAlmostEqual(dual_source.avoided_loss, 0.0, delta=1.0)
        self.assertLess(dual_source.net_benefit, 0.0)
        self.assertFalse(dual_source.recommended)


if __name__ == "__main__":
    unittest.main()
