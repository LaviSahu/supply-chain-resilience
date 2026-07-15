"""Tests for graph.py — criticality, single-sourcing, HHI, DC pooling."""

import unittest

import _bootstrap  # noqa: F401  (sys.path shim, must run before resilience_radar imports)

from resilience_radar import graph

from fixtures import simple_chain_network, single_source_network, two_market_network


class TestCriticality(unittest.TestCase):
    def test_every_node_in_chain_is_fully_critical(self) -> None:
        # In a single-path chain network, every node is on the sole path
        # from supplier to market, so each should carry 100% criticality.
        network = simple_chain_network()
        crit = graph.node_criticality(network)
        for node_id in ("SUP", "PLANT", "DC", "MKT"):
            self.assertAlmostEqual(crit[node_id], 1.0, places=6)

    def test_lane_criticality_matches_node_criticality(self) -> None:
        network = simple_chain_network()
        crit = graph.lane_criticality(network)
        for lane_id in ("L1", "L2", "L3"):
            self.assertAlmostEqual(crit[lane_id], 1.0, places=6)


class TestDcPooling(unittest.TestCase):
    def test_dc_weekly_flow_sums_across_markets(self) -> None:
        network = two_market_network()
        # MKT-A demand 60 + MKT-B demand 40 = 100, must be pooled once,
        # not double-assigned to each market independently.
        flow = graph.dc_weekly_flow(network, "DC", "SKU-X")
        self.assertEqual(flow, 100.0)

    def test_markets_served_returns_both(self) -> None:
        network = two_market_network()
        served = graph.markets_served(network, "DC", "SKU-X")
        market_ids = {m for m, _ in served}
        self.assertEqual(market_ids, {"MKT-A", "MKT-B"})

    def test_dc_sku_pairs_includes_pair(self) -> None:
        network = two_market_network()
        pairs = graph.dc_sku_pairs(network)
        self.assertIn(("DC", "SKU-X"), pairs)


class TestSingleSource(unittest.TestCase):
    def test_detects_single_sourced_sku(self) -> None:
        network = single_source_network()
        flags = graph.single_source_map(network)
        skus_flagged = {f.sku_id for f in flags}
        # SKU-Y is fed by SUP-1 AND SUP-2 -> not single-sourced.
        self.assertNotIn("SKU-Y", skus_flagged)
        # SKU-Z is fed only by SUP-3 -> single-sourced.
        self.assertIn("SKU-Z", skus_flagged)
        z_flag = next(f for f in flags if f.sku_id == "SKU-Z")
        self.assertEqual(z_flag.supplier_id, "SUP-3")
        self.assertEqual(z_flag.plant_id, "PLANT")


class TestHhi(unittest.TestCase):
    def test_single_supplier_category_is_monopoly(self) -> None:
        network = single_source_network()
        # SUP-1/SUP-2/SUP-3 have no `category` set in this fixture, so
        # hhi_by_category should simply produce no entries (nodes lacking
        # a category are excluded), confirming it doesn't crash on that.
        hhi = graph.hhi_by_category(network)
        self.assertEqual(hhi, {})

    def test_two_equal_suppliers_gives_5000(self) -> None:
        from resilience_radar.models import Lane, LaneMode, Network, Node, NodeType, Sku

        nodes = [
            Node(id="S1", name="S1", type=NodeType.SUPPLIER, region="A", country="A", x=0, y=0, category="cat"),
            Node(id="S2", name="S2", type=NodeType.SUPPLIER, region="A", country="A", x=0, y=1, category="cat"),
            Node(id="P", name="P", type=NodeType.PLANT, region="A", country="A", x=1, y=0),
        ]
        lanes = [
            Lane(id="L1", source="S1", target="P", mode=LaneMode.OCEAN, lead_time_days=1,
                 capacity_units_per_week=500.0, skus=["SKU-X"], primary=True),
            Lane(id="L2", source="S2", target="P", mode=LaneMode.OCEAN, lead_time_days=1,
                 capacity_units_per_week=500.0, skus=["SKU-X"], primary=True),
        ]
        network = Network(company="T", nodes=nodes, lanes=lanes, skus=[Sku(id="SKU-X", name="X", revenue_per_unit=1.0)])
        hhi = graph.hhi_by_category(network)
        self.assertAlmostEqual(hhi["cat"], 5000.0, places=1)


class TestExposureDays(unittest.TestCase):
    def test_no_gap_when_cover_exceeds_lead_time(self) -> None:
        network = simple_chain_network()
        # DC has 7 days cover; inbound lane L2 lead_time_days=5 -> no gap (5-7 <0 -> floored to 0)
        gap = graph.exposure_days_for_node(network, "DC")
        self.assertEqual(gap, 0.0)

    def test_positive_gap_when_lead_time_exceeds_cover(self) -> None:
        from resilience_radar.models import Lane, LaneMode, Network, Node, NodeType, Sku

        nodes = [
            Node(id="P", name="P", type=NodeType.PLANT, region="A", country="A", x=0, y=0),
            Node(
                id="DC",
                name="DC",
                type=NodeType.DC,
                region="A",
                country="A",
                x=1,
                y=0,
                inventory_days_of_cover={"SKU-X": 3.0},
            ),
        ]
        lanes = [
            Lane(id="L1", source="P", target="DC", mode=LaneMode.OCEAN, lead_time_days=10,
                 capacity_units_per_week=100.0, skus=["SKU-X"], primary=True),
        ]
        network = Network(company="T", nodes=nodes, lanes=lanes, skus=[Sku(id="SKU-X", name="X", revenue_per_unit=1.0)])
        gap = graph.exposure_days_for_node(network, "DC")
        self.assertEqual(gap, 7.0)  # 10 days lead time - 3 days cover

    def test_supplier_uses_downstream_cover(self) -> None:
        network = simple_chain_network()
        # SUP has no inventory of its own; falls back to downstream node's
        # cover via its outbound lane (L1 -> PLANT, which has no
        # inventory_days_of_cover set for SKU-X in this fixture, so gap 0).
        gap = graph.exposure_days_for_node(network, "SUP")
        self.assertEqual(gap, 0.0)


if __name__ == "__main__":
    unittest.main()
