"""
fixtures.py — small, hand-computable toy networks shared across the test
suite. Not a test module itself (no `Test*` classes), so `unittest
discover` skips it as a test case source while still being importable by
the modules that need it.

Two fixtures:

- `simple_chain_network()` — one supplier -> one plant -> one DC -> one
  market, single SKU. Small enough that TTS/TTR under a full-stop
  disruption can be hand-computed exactly (see test_simulate.py).
- `two_market_network()` — one DC serving two markets for a single SKU,
  used to exercise the double-counting fix in `dc_weekly_flow` /
  `dc_sku_pairs` (a DC's inventory pool must not be double-assigned to
  each market it serves).
"""

from __future__ import annotations

from resilience_radar.models import Lane, LaneMode, Network, Node, NodeType, Sku


def simple_chain_network() -> Network:
    """
    SUP --L1--> PLANT --L2--> DC --L3--> MKT, single SKU-X.

    DC inventory_days_of_cover = 7 days == exactly one week of market
    demand (100 units/week), so `_initial_inventory_units` == 100.
    Every lane's capacity_units_per_week (1000) is far above demand, so
    the only ever binding constraint is the disrupted lane/node.
    """
    skus = [Sku(id="SKU-X", name="Widget", revenue_per_unit=10.0)]
    nodes = [
        Node(id="SUP", name="Supplier", type=NodeType.SUPPLIER, region="Asia", country="X", x=0, y=0),
        Node(id="PLANT", name="Plant", type=NodeType.PLANT, region="Asia", country="X", x=1, y=0),
        Node(
            id="DC",
            name="DC",
            type=NodeType.DC,
            region="Asia",
            country="X",
            x=2,
            y=0,
            inventory_days_of_cover={"SKU-X": 7.0},
        ),
        Node(
            id="MKT",
            name="Market",
            type=NodeType.MARKET,
            region="Asia",
            country="X",
            x=3,
            y=0,
            weekly_demand={"SKU-X": 100.0},
        ),
    ]
    lanes = [
        Lane(id="L1", source="SUP", target="PLANT", mode=LaneMode.OCEAN, lead_time_days=5,
             capacity_units_per_week=1000.0, skus=["SKU-X"], primary=True),
        Lane(id="L2", source="PLANT", target="DC", mode=LaneMode.OCEAN, lead_time_days=5,
             capacity_units_per_week=1000.0, skus=["SKU-X"], primary=True),
        Lane(id="L3", source="DC", target="MKT", mode=LaneMode.ROAD, lead_time_days=1,
             capacity_units_per_week=1000.0, skus=["SKU-X"], primary=True),
    ]
    return Network(company="Toy Co", nodes=nodes, lanes=lanes, skus=skus)


def two_market_network() -> Network:
    """
    SUP --L1--> PLANT --L2--> DC --L3--> MKT-A
                                 \\--L4--> MKT-B

    Both markets draw from the same DC pool for SKU-X. Used to confirm
    `dc_weekly_flow` sums demand across both markets rather than
    treating them as independent pools (the bug fixed during design).
    """
    skus = [Sku(id="SKU-X", name="Widget", revenue_per_unit=10.0)]
    nodes = [
        Node(id="SUP", name="Supplier", type=NodeType.SUPPLIER, region="Asia", country="X", x=0, y=0),
        Node(id="PLANT", name="Plant", type=NodeType.PLANT, region="Asia", country="X", x=1, y=0),
        Node(
            id="DC",
            name="DC",
            type=NodeType.DC,
            region="Asia",
            country="X",
            x=2,
            y=0,
            inventory_days_of_cover={"SKU-X": 7.0},
        ),
        Node(
            id="MKT-A",
            name="Market A",
            type=NodeType.MARKET,
            region="Asia",
            country="X",
            x=3,
            y=0,
            weekly_demand={"SKU-X": 60.0},
        ),
        Node(
            id="MKT-B",
            name="Market B",
            type=NodeType.MARKET,
            region="Asia",
            country="X",
            x=3,
            y=1,
            weekly_demand={"SKU-X": 40.0},
        ),
    ]
    lanes = [
        Lane(id="L1", source="SUP", target="PLANT", mode=LaneMode.OCEAN, lead_time_days=5,
             capacity_units_per_week=1000.0, skus=["SKU-X"], primary=True),
        Lane(id="L2", source="PLANT", target="DC", mode=LaneMode.OCEAN, lead_time_days=5,
             capacity_units_per_week=1000.0, skus=["SKU-X"], primary=True),
        Lane(id="L3", source="DC", target="MKT-A", mode=LaneMode.ROAD, lead_time_days=1,
             capacity_units_per_week=1000.0, skus=["SKU-X"], primary=True),
        Lane(id="L4", source="DC", target="MKT-B", mode=LaneMode.ROAD, lead_time_days=1,
             capacity_units_per_week=1000.0, skus=["SKU-X"], primary=True),
    ]
    return Network(company="Toy Co", nodes=nodes, lanes=lanes, skus=skus)


def single_source_network() -> Network:
    """
    Two suppliers feed PLANT for SKU-Y and SKU-Z respectively, so SKU-Y
    is single-sourced (only SUP-1) while SKU-Z... actually both single
    sourced in this minimal shape; a second supplier is added for SKU-Y
    to give one genuinely dual-sourced case.
    """
    skus = [
        Sku(id="SKU-Y", name="Y", revenue_per_unit=5.0),
        Sku(id="SKU-Z", name="Z", revenue_per_unit=5.0),
    ]
    nodes = [
        Node(id="SUP-1", name="Supplier 1", type=NodeType.SUPPLIER, region="Asia", country="X", x=0, y=0),
        Node(id="SUP-2", name="Supplier 2", type=NodeType.SUPPLIER, region="Asia", country="X", x=0, y=1),
        Node(id="SUP-3", name="Supplier 3", type=NodeType.SUPPLIER, region="Asia", country="X", x=0, y=2),
        Node(id="PLANT", name="Plant", type=NodeType.PLANT, region="Asia", country="X", x=1, y=0),
    ]
    lanes = [
        Lane(id="L1", source="SUP-1", target="PLANT", mode=LaneMode.OCEAN, lead_time_days=5,
             capacity_units_per_week=500.0, skus=["SKU-Y"], primary=True),
        Lane(id="L2", source="SUP-2", target="PLANT", mode=LaneMode.OCEAN, lead_time_days=5,
             capacity_units_per_week=500.0, skus=["SKU-Y"], primary=True),
        Lane(id="L3", source="SUP-3", target="PLANT", mode=LaneMode.OCEAN, lead_time_days=5,
             capacity_units_per_week=500.0, skus=["SKU-Z"], primary=True),
    ]
    return Network(company="Toy Co", nodes=nodes, lanes=lanes, skus=skus)
