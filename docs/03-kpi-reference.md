# KPI Reference

Every formula below is transcribed from `scoring.py`, `graph.py`,
`simulate.py`, and `kpi.py` as actually implemented — not an idealized
textbook version. Where the code makes an opinionated modeling choice
(documented in `implementation-notes.md`), it's called out here too.

## Risk scoring (per event, `scoring.py`)

**Likelihood** (1–5): the event's stated `confidence` (0–1) scaled to a
5-point scale, adjusted by a per-source-category reliability offset, then
clamped:

```
likelihood = clamp(round(confidence * 5 + reliability_adjustment), 1, 5)
```

`geopolitical` and `regulatory` sources get a −1 adjustment (their
reporting tends to be noisier / less directly actionable); everything else
gets 0.

**Impact** (1–5): bucketed from a "severity-days" proxy — criticality of
the affected element times the expected outage length in weeks:

```
severity = criticality * expected_outage_weeks
impact = 5 if severity >= 1.5
       = 4 if severity >= 0.6
       = 3 if severity >= 0.25
       = 2 if severity >= 0.08
       = 1 otherwise
```

`expected_outage_weeks` is a deterministic lookup by consequence class
(not free-text extraction): `deviation` → 0.5w, `disruption` → 2.5w,
`disaster` → 8w.

**Risk score and tier**:

```
risk_score = likelihood * impact          # 1-25
CRITICAL  if risk_score >= 20
HIGH      if risk_score >= 12
MEDIUM    if risk_score >= 6
LOW       if risk_score >= 1
```

These thresholds are an invented, roughly-quartile bucketing over the 1–25
range (SPEC.md specifies the multiplication but not the cutoffs) — biased
so a 4×5 or 5×4 combination (a highly likely, highly impactful event) reads
CRITICAL.

**Value at Risk (VaR)**:

```
weekly_revenue = criticality * total_weekly_revenue(network)
value_at_risk = weekly_revenue * expected_outage_weeks
```

VaR is a **static, pre-buffer estimate** — it never runs the simulator and
deliberately ignores inventory cover and backup lanes. Its only job is to
rank the register. Realized loss under a specific disruption comes from the
what-if simulation, which is why the two numbers never reconcile: the gap
between gross exposure (VaR) and simulated lost revenue *is* the resilience
the buffers and alternate lanes are buying you.

**Exposure days** — the lead-time cover gap, `max(0, lane.lead_time_days -
node.inventory_days_of_cover)` across a node's primary inbound lanes; for
nodes that hold no inventory of their own (suppliers), it looks at the
downstream node's cover instead, since a supplier disruption only bites
once the downstream buffer runs out.

## Network structure (`graph.py`)

**Node/lane criticality** — fraction of total network weekly revenue that
structurally depends on the node or lane. Computed by walking every
`(market, sku)` flow's *full backward-reachable set* of primary-lane nodes
(an AND-dependency: a plant needs every input, not just one path) and
adding that flow's revenue share to every node/lane in the set. Revenue is
deliberately double-counted across a flow's dependency set — that's what
AND-dependency criticality means: removing *any one* of those nodes breaks
the flow.

```
criticality[node] = sum(
    market_sku_revenue(m, s) / total_weekly_revenue
    for (m, s) in market_sku_pairs
    if node in upstream_node_set(m, s)
)
```

**Single-source count** — number of `(plant, sku)` pairs fed by exactly one
supplier via primary lanes. In the demo network: **1** (Rhineland Precision
GmbH is the sole supplier of SKU-E to the Wroclaw plant).

**HHI (Herfindahl-Hirschman Index)** per supplier input category — the
same concentration measure used in antitrust analysis, proxied here by
each supplier's share of total outbound primary-lane capacity within its
category:

```
HHI = sum((supplier_capacity / category_total_capacity) ** 2 for each supplier) * 10000
```

10,000 = single-supplier monopoly on that category; lower is more
diversified.

## Simulation metrics (`simulate.py`)

**Service level** (per week): `shipped_revenue / demand_revenue` (1.0 if
there was no demand that week).

**TTS (time to survive)**: consecutive weeks from the outage's start that
service level stays ≥98% *before* the first dip. If service never dips,
TTS covers the whole 12-week horizon.

**TTR (time to recover)**: weeks from that first dip until service is back
≥98%. `None` if the network never recovers within the 12-week horizon
(kpi.py reports this case as `-1` in `worst_ttr`).

Both are Simchi-Levi-style resilience metrics — the actual textbook
definitions pair TTR with the amount of capacity lost, but here TTR/TTS are
read directly off the simulated weekly service-level series, which is a
simpler, fully-computed operationalization of the same idea.

## KPI catalog (`kpi.py`)

| KPI | formula | demo value |
|---|---|---|
| **RSI** (Risk Severity Index) | mean `risk_score` across the open register | 5.69 |
| **Risk density** | `len(risks) / len(network.nodes)` | 2.69 risks/node |
| **Revenue at Risk** | sum of `value_at_risk` across the open register | $20,994,914 |
| **Open Risks** | register count, broken down by tier | 35 (3 CRITICAL / 6 HIGH / 2 MEDIUM / 24 LOW) |
| **Service Level (baseline)** | `sim_results[any].baseline_service_level * 100` | 100% |
| **Min TTS** | `min(r.tts for r in sim_results.values())` — the network's weakest survival window across presets | 0 weeks (port-closure) |
| **Worst TTR** | `max(r.ttr for r in sim_results.values())` — longest recovery across presets, `None`/`-1` if any scenario never recovers | 3 weeks |
| **Single-Source Nodes** | `len(graph.single_source_map(network))` | 1 |

All KPI values above are read straight from a live `demo` run against
`data/network.json` / `data/events.json` — re-run the demo after editing
either file and these numbers will change; nothing here is hardcoded in
`kpi.py` itself.

Next: [Scenario Guide](04-scenario-guide.md).
