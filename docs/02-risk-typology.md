# Risk Typology

`typology.py` is where a raw headline becomes a structured risk. Resilience
practice (Sheffi and Rice's "The Resilient Enterprise", Simchi-Levi's
supply-chain risk work) classifies disruptions along two **independent**
axes rather than one severity scale, because "where it comes from" and
"how bad it gets" don't move together — a cyber event and a typhoon can
both land as a `disaster`, but you prepare for them completely differently.

## Axis 1 — source

*Where* the disruption originates. Nine categories, checked in a fixed
priority order (first keyword match wins) because some events plausibly
match more than one category — an "export controls" headline is
geopolitical *before* it's regulatory, by design:

1. `natural-hazard` — typhoon, hurricane, flood, earthquake, wildfire, monsoon, heatwave, storm, El Niño
2. `cyber` — cyberattack, ransomware, data breach, malware, intrusion
3. `financial` — insolvency, bankruptcy, creditor protection, credit downgrade, currency
4. `geopolitical` — export controls, sanctions, trade war, border closure, conflict
5. `regulatory` — tariff, compliance, licensing, recall mandate, policy
6. `logistics` — port congestion, strike, dockworker action, freight rate, vessel queue
7. `demand` — demand surge/spike, viral, consumer confidence, competitor moves
8. `supplier` — supplier-named events, chip/component shortage, diversify-supplier language
9. `internal-operational` — recall, quality control, defect, software glitch (also the default when nothing else matches)

## Axis 2 — consequence

*How bad it is once it lands*, on a three-step ladder, also keyword-matched
in priority order:

- **`deviation`** — minor, everyday noise ("easing", "resolved",
  "preliminary", "no material impact")
- **`disruption`** — a real but recoverable hit ("strike", "congestion",
  "shortage", "recall", "surge")
- **`disaster`** — severe, rare ("typhoon", "earthquake", "bankruptcy",
  "shutdown", "destroyed")

Consequence defaults to `deviation` if no keyword hits — an event with no
signal of severity is treated as low-severity by construction, which
`scoring.py` reflects downstream (see [KPI Reference](03-kpi-reference.md)
for how consequence maps to expected outage weeks).

## LIHF vs. HILF

The two axes combine into a frequency class used throughout the resilience
literature:

- **LIHF** (low-impact, high-frequency) — the everyday operational noise a
  supply chain absorbs without a second thought.
- **HILF** (high-impact, low-frequency) — the tail-risk events a resilience
  program actually exists to prepare for (Ivanov's "ripple effect"
  literature is built almost entirely around HILF propagation).

`typology.frequency_class_for()` assigns **HILF** whenever the consequence
is `disaster`, *or* the source category is one of the archetypal tail-risk
sources: `natural-hazard`, `geopolitical`, `cyber`, `financial`. Everything
else is **LIHF**. This means a `disruption`-level cyber event still reads
HILF (cyber incidents are tail-risk by source, independent of how bad any
one instance turns out) — a deliberate modeling choice, not an oversight.

## The classifier is deterministic, not ML

`classify_event()` is pure keyword + alias matching over
`f"{headline} {body}".lower()` — no embeddings, no network calls, fully
unit-tested (`tests/test_typology.py`, 15 cases). It never guesses: an
event that matches nothing lands as `internal-operational` / `deviation`,
which `scoring.py` naturally down-scores rather than the classifier forcing
a confident-sounding but fabricated category.

Node and lane matching (`match_nodes`, `match_lanes`) is separate from the
source/consequence call and **always** runs through this same alias
matcher, even when an LLM classifier is swapped in for the judgment calls
(see [LLM Integration](05-llm-integration.md)) — which node or lane a
headline mentions is a structural fact about the text, not a judgment call
an LLM should be asked to make.

## Worked example

> "Typhoon Bualoi tracks toward Shenzhen coast, threatening chip fab and
> assembly operations"

- Source: `natural-hazard` (matches "typhoon")
- Consequence: `disaster` (matches "typhoon" again — the same keyword can
  hit both axis rule sets)
- Frequency: `HILF` (natural-hazard is a tail-risk source)
- Matched nodes: `SUP-CN-CHIP`, `PLANT-CN` (via node aliases)

This is `RISK-EVT-001` in the live demo run — it becomes the highest-VaR
risk in the register at $6.96M (see [KPI Reference](03-kpi-reference.md)
for how value-at-risk is computed from here).

Next: [KPI Reference](03-kpi-reference.md).
