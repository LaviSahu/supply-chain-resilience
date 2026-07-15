# Scenario Guide

## The `Scenario` schema

```python
@dataclass
class Scenario:
    id: str
    name: str
    disrupted_element: str   # a node id or a lane id
    element_kind: str        # "node" | "lane"
    outage_weeks: int
    capacity_pct: float      # fraction of normal throughput that survives, 0.0-1.0
    demand_shock_pct: float = 0.0   # e.g. 0.4 for +40%, only meaningful when disrupted_element is a market
    description: str = ""
```

Every scenario runs over a fixed **12-week horizon** (`simulate.HORIZON_WEEKS`),
with the outage always starting in week 1 (`OUTAGE_START_WEEK`). The engine
runs baseline (no scenario) and scenario side by side and diffs them.

## The three presets

| id | disrupted element | outage | capacity_pct | demand shock |
|---|---|---|---|---|
| `supplier-failure` | `SUP-DE-PREC` (Rhineland Precision GmbH, sole supplier of SKU-E) | 4 weeks | 0.0 (full stop) | — |
| `port-closure` | `DC-SG` (Singapore Regional DC) | 2 weeks | 0.0 (full stop) | — |
| `demand-spike` | `MKT-US-E` (US East Retail) | 3 weeks | 1.0 (no supply cut) | +40% |

Results from a live `demo` run:

| scenario | worst service | TTS | TTR | total lost revenue |
|---|---|---|---|---|
| supplier-failure | 85.9% | 1w | 3w | $529,143 |
| port-closure | **79.0%** (worst of the three) | 0w | 2w | $578,800 |
| demand-spike | 97.9% | 0w | 3w | $98,400 |

Baseline service level (no disruption) is 100% across all three — confirms
the network is modeled in equilibrium before any scenario runs.

## Propagation semantics

The engine runs once per `(DC, SKU)` pair, in two stages, because a DC
serving multiple markets (e.g. Memphis DC → US East and US West) has one
shared inventory pool and one shared upstream supply chain that would be
double-counted if simulated per-market instead.

**Stage 1 — upstream (shared across all markets a DC serves).** Each week,
compute the bottleneck capacity across the supplier → plant → DC lane
chain (`graph.upstream_chain_lanes`). Any lane touching the disrupted
element has its capacity multiplied by `scenario.capacity_pct` while the
outage is active. If a non-primary ("alternate") lane exists into the same
node, doesn't itself touch the disrupted element, and the current week is
at least `switch_lag_weeks` past the outage's start, its capacity is added
back in — modeling the real delay of qualifying a backup supplier or
re-routing freight.

**Stage 2 — downstream (per market the DC serves).** Each market's demand
(shocked if this is the demand-spike archetype) competes for the DC's
available pool, additionally capped by its own outbound lane capacity. If
the pool can't cover every market's deliverable demand, the shortfall is
absorbed at the aggregate level (only the total matters for lost-revenue
accounting, not which specific market is short).

**Inventory carries forward** week to week: `available = inventory +
supply_in`, `shipped = min(available, demand)`, and unmet demand is a lost
sale — there is no backorder model (this is a retail network, not
build-to-order).

Initial inventory is computed from `node.inventory_days_of_cover` (days) at
the DC, converted to units via that DC's steady-state weekly flow for the
SKU. **Note:** only DC-level inventory drains week to week in the
simulation; plant-level `inventory_days_of_cover` in `network.json` feeds
`scoring.exposure_days_for_node` for the risk register but is not a second
buffer the weekly propagation draws down — see implementation-notes.md
deviation #3.

## TTR and TTS, precisely

- **TTS (time to survive)**: consecutive weeks from the outage's start
  where service level stays ≥98%, before the first dip. A TTS of 0 (as in
  port-closure) means the very first week of the outage already breaches
  the 98% threshold.
- **TTR (time to recover)**: weeks from that first dip until service
  returns to ≥98%. `None` if the network never recovers within the
  12-week horizon.

## Why port-closure is the worst scenario despite the shortest outage

Two weeks of a *full* DC closure (`capacity_pct=0.0`) hits every SKU routed
through Singapore simultaneously, with only the air-freight bypass lane
(Shenzhen Assembly Plant → Singapore DC, 1-week switch lag) protecting
SmartHome Hub and Wireless Charger. Tote Bag, Travel Mug, and Multi-Tool
have no bypass at all, so they take the full hit for both outage weeks —
producing a lower worst-case service level (79.0%) in a shorter window than
the 4-week supplier failure, whose SKU-E-only blast radius and DC-level
inventory buffer both limit the damage.

## Defining a custom scenario

Scenarios are plain `Scenario` dataclass instances — no config-file DSL.
To add one, extend `simulate.PRESET_SCENARIOS` in `simulate.py`:

```python
PRESET_SCENARIOS["my-scenario"] = Scenario(
    id="my-scenario",
    name="My Custom Disruption",
    disrupted_element="DC-US",       # any node or lane id from network.json
    element_kind="node",             # or "lane"
    outage_weeks=3,
    capacity_pct=0.2,                # 20% of normal throughput survives
    demand_shock_pct=0.0,            # only applies when disrupted_element is a market
    description="...",
)
```

Then run it directly:

```bash
PYTHONPATH=src python3 -m resilience_radar simulate --scenario my-scenario
```

Or programmatically, without touching the preset registry at all:

```python
from resilience_radar import graph, simulate
network = graph.load_network("data/network.json")
scenario = simulate.Scenario(
    id="my-scenario", name="My Custom Disruption",
    disrupted_element="DC-US", element_kind="node",
    outage_weeks=3, capacity_pct=0.2,
)
result = simulate.run_scenario(network, scenario)
print(result.ttr, result.tts, result.total_lost_revenue)
```

`element_kind="lane"` targets a specific lane id (e.g. `"L9"`) instead of a
node — useful for modeling a single transport link failure (a strike on
one ocean route) rather than an entire facility going down. One caveat
worth knowing before you tune `capacity_pct`: per implementation-notes.md
deviation #2, lane capacity is *not* pooled across SKUs sharing a lane —
each SKU independently gets the lane's full stated capacity, so a partial
`capacity_pct` cut can produce a smaller visible effect than you'd expect
if the lane's stated capacity comfortably covers every SKU's individual
demand.

Next: [LLM Integration](05-llm-integration.md).
