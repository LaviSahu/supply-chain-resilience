# Roadmap

Resilience Radar is a showcase-grade demonstration, deliberately scoped to
a deterministic single-run engine over a synthetic network. The gaps below
are the honest list of what a production resilience desk would need next
— not vague aspirations, but specific extensions to specific modules.

## Monte Carlo / stochastic simulation

`simulate.py` today runs exactly one deterministic path per scenario:
fixed `outage_weeks`, fixed `capacity_pct`, fixed demand. A real resilience
desk cares about the *distribution* of outcomes, not one point estimate —
what's the 95th-percentile lost revenue if outage duration itself is
uncertain? The natural extension is sampling `outage_weeks`,
`capacity_pct`, and `demand_shock_pct` from distributions (e.g. outage
duration as a lognormal, capacity loss as a beta distribution) and running
`run_scenario()` hundreds of times, then reporting percentile bands on
lost revenue, TTR, and TTS instead of single numbers. This also unlocks
**CVaR** (below).

## CVaR (Conditional Value at Risk)

`scoring.value_at_risk()` today is a point estimate:
`criticality * weekly_revenue * expected_outage_weeks`, using a
deterministic outage-length lookup by consequence class. A tail-risk-aware
version would report VaR at a chosen confidence level *and* CVaR (the
expected loss *given* that you're already in the worst-case tail) —
standard practice in financial risk management, underused in supply-chain
risk registers. This depends on the Monte Carlo work above: CVaR is only
meaningful once there's an actual distribution of outcomes to average over
the tail of.

## Real news / event feed integration

`radar.py` reads a static `data/events.json`. A production version would
poll real disruption-signal sources (GDELT, trade-press RSS feeds,
customs/logistics APIs) on a schedule, run them through `typology.py` (or
an LLM classifier per [LLM Integration](05-llm-integration.md)), and
append to a running risk register — with deduplication logic, since real
feeds report the same event from multiple sources with different wording.

## Geo map

`network.json`'s node `x`/`y` coordinates are hand-set canvas positions
("geo-suggestive: Asia left, EU middle, US right" per DESIGN.md), not real
latitude/longitude — the dashboard's network map is a schematic diagram,
not a map. A geo-accurate version would place nodes on an actual
projection (even a simple equirectangular SVG, still no external map
tiles needed to stay dependency-free) and could layer real port/route data
on top for genuinely geographic reasoning about exposure (e.g. two
"different" suppliers that route through the same physical strait).

## Multi-echelon inventory optimization

The mitigation playbook (`mitigate.py`) picks from five hand-designed
levers and ranks them by re-simulating with each one applied — it doesn't
*solve* for an optimal inventory policy. A genuine multi-echelon inventory
optimization layer (base-stock levels per node computed jointly across the
network, not independently per DC) would turn "which of these five levers
helps most" into "what is the revenue-minimizing safety-stock allocation
across the entire network subject to a holding-cost budget" — a proper
optimization problem, not a ranked comparison of fixed presets.

## Smaller, more contained items

- Pool lane capacity across SKUs sharing a lane (implementation-notes.md
  deviation #2) instead of letting each SKU claim the lane's full stated
  capacity independently — needs an allocation/prioritization policy this
  project intentionally left unspecified.
- A second, upstream (plant-level) inventory-draining stage in
  `simulate.py`, so a disruption's effect on plant stock is simulated week
  by week rather than only feeding the risk register's static
  exposure-days figure (deviation #3).
- Collapse the mitigation playbook's five actions into their true three
  underlying mechanisms (capacity restoration, inventory front-load,
  switch-lag removal — see deviation #8) with a continuous cost/magnitude
  parameter instead of five discrete presets, so a user could tune
  "how much" a lever does rather than picking from fixed options.

Back to [index](index.md).
