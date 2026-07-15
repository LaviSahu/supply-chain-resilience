# Resilience Radar — Wiki Home

Resilience Radar is a pure-stdlib Python platform that turns a disruption-event
feed into a scored risk register, runs deterministic what-if simulations
against a modeled supply network, ranks mitigations, and renders a
self-contained HTML control tower. This wiki is the practitioner-facing
reference layer — the README gets you running in 60 seconds, these pages
explain *why* the engine is built the way it is.

## Pages

1. **[Architecture](01-architecture.md)** — module map, data flow from
   `events.json`/`network.json` to `dashboard.html`, the dashboard context
   contract.
2. **[Risk Typology](02-risk-typology.md)** — the two-axis taxonomy
   (source × consequence), LIHF/HILF framing, and the deterministic
   classification rules.
3. **[KPI Reference](03-kpi-reference.md)** — every formula as implemented
   in `kpi.py` and `scoring.py`, not an idealized textbook version.
4. **[Scenario Guide](04-scenario-guide.md)** — the `Scenario` schema, the
   three presets, propagation semantics (inventory drain, alt-sourcing
   switch lag, capacity caps), and TTR/TTS definitions.
5. **[LLM Integration](05-llm-integration.md)** — the adapter design, the
   offline rule-based fallback, and why this project deliberately keeps
   the LLM to classification-only rather than agentic code generation.
6. **[Roadmap](06-roadmap.md)** — Monte Carlo, real news feeds, a geo map,
   multi-echelon inventory optimization, CVaR.

## Ground truth

Every number in this wiki and the README comes from actually running:

```bash
PYTHONPATH=src python3 -m resilience_radar demo
```

against the synthetic "Meridian Goods" network in `data/network.json` and
the ~35-event feed in `data/events.json`. Nothing is hardcoded — if you
edit either input file, the numbers in the dashboard and console change
accordingly, and these docs would need a re-run to stay accurate.

Back to the [README](../README.md).
