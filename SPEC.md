# Resilience Radar — Build Spec (frozen)

Showcase-grade, self-contained supply chain resilience platform. Pure Python 3.10+ **stdlib only** (no pip installs needed to run the demo). Original work — NO references to EY, clients, or any consulting firm anywhere in code or docs.

## What it is
An end-to-end resilience engine: ingest a disruption-event feed → classify + score risks against a modeled supply network → simulate what-if scenarios (time-phased propagation) → rank mitigations → render a single-file HTML dashboard.

## Repo layout
```
resilience-radar/
├── README.md                      # showcase README (chunk C)
├── LICENSE                        # MIT, copyright Lavi Sahu
├── pyproject.toml                 # metadata only, no deps
├── Makefile                       # demo / test / dashboard targets
├── data/
│   ├── network.json               # synthetic 3-tier network
│   └── events.json                # synthetic disruption feed (~35 events)
├── src/resilience_radar/
│   ├── __init__.py  __main__.py  cli.py
│   ├── models.py    # dataclasses: Node, Lane, Sku, Event, Risk, Scenario, SimResult
│   ├── graph.py     # network analytics
│   ├── typology.py  # risk taxonomy + rule-based classifier
│   ├── scoring.py   # scoring engine
│   ├── radar.py     # event feed -> risk register
│   ├── simulate.py  # what-if time-phased simulation
│   ├── mitigate.py  # mitigation playbook + ranking
│   ├── kpi.py       # KPI catalog computed from real outputs
│   ├── llm.py       # optional LLM adapter (Anthropic/OpenAI/none), offline fallback
│   └── dashboard.py # self-contained HTML dashboard generator (inline CSS/JS/SVG)
├── tests/           # stdlib unittest, runnable via `python -m unittest discover`
├── docs/            # wiki-style pages (chunk C)
└── output/          # gitignored except .gitkeep; dashboard.html + risk_register.json land here
```

## Domain spec

### network.json (synthetic — invent a plausible consumer-goods company "Meridian Goods")
- ~4 suppliers (tier-2/1, one single-source), 2 plants, 3 DCs, 4 markets; lanes with lead_time_days, mode, capacity; 5 SKUs with revenue_per_unit, weekly demand per market, days_of_cover inventory at nodes. Geographies spread across Asia/EU/US incl. one port dependency (e.g., "Port of Singapore transshipment").

### typology.py — taxonomy (two axes)
- `source`: internal-operational, supplier, logistics, geopolitical, natural-hazard, cyber, demand, regulatory, financial
- `consequence`: deviation, disruption, disaster; frequency class LIHF/HILF
- Rule-based classifier: keyword/geo matching from event text → (source_category, affected node/lane candidates). Deterministic, unit-tested.

### scoring.py
- likelihood (1-5, from event confidence + source reliability), impact (1-5, from affected node criticality × value at risk), exposure_days (lead-time cover gap = lead_time - days_of_cover, floor 0)
- `risk_score = likelihood * impact`, tiered CRITICAL/HIGH/MEDIUM/LOW
- Value-at-Risk per risk: weekly revenue through affected element × expected outage weeks.

### graph.py
- Criticality per node: fraction of total revenue flowing through it (path-based)
- Single-source detection (any plant/SKU fed by exactly one supplier)
- Supplier concentration HHI per input category
- Downstream reachability (which markets does node X serve)

### simulate.py — deterministic time-phased engine (weekly buckets, horizon 12 weeks)
- Scenario = {disrupted_element (node|lane), outage_weeks, capacity_pct, demand_shock_pct optional}
- Propagation: inventory drains at demand rate; when cover exhausted and upstream down → lost sales; alternate sourcing if another lane exists (with capacity limit + switch lag)
- Outputs per week: service_level, lost_revenue, inventory position; scalar TTR (time to recover = weeks until service back ≥98%) and TTS (time to survive = weeks of full service with element down)
- Baseline vs scenario delta. Include 3 preset scenarios: single-source supplier failure 4wks, port closure 2wks, demand spike +40% 3wks.

### mitigate.py
- Playbook actions (dual-source, safety-stock uplift, alt-lane/mode shift, pre-build, allocation) each with cost estimate + effect model (e.g., safety stock +X days cover)
- Rank by (avoided lost revenue − cost) computed by re-running simulate with the action applied. Greedy top-3 recommendation per scenario.

### kpi.py — catalog, each computed (not hardcoded): RSI (risk severity index = mean score of open risks), risk density (risks per network node), TTR, TTS, service level, revenue at risk, single-source count, HHI.

### radar.py
- Load events.json → classify → score → risk register (JSON out). Optional `--llm` flag routes classification through llm.py adapter; default fully offline.

### llm.py
- Adapter interface `classify_event(text) -> dict`; providers: anthropic, openai (read keys from env), and `RuleBasedFallback` (default). Never required. Keep it ~80 lines.

### dashboard.py
- ONE self-contained output/dashboard.html: dark professional theme, inline CSS + vanilla JS + inline SVG charts (no CDN). Sections: KPI tile row, risk register table (sortable, tier-colored), network map (SVG node-link, positioned by hand-set coords in network.json, disrupted elements highlighted), scenario comparison (baseline vs scenario service-level line chart + lost-revenue bars), top mitigations table. Data embedded as JSON in a <script> tag at build time.

### cli.py
```
python -m resilience_radar scan                 # events -> output/risk_register.json (+ console table)
python -m resilience_radar simulate --scenario port-closure
python -m resilience_radar demo                 # scan + all 3 scenarios + mitigations + dashboard
python -m resilience_radar dashboard            # rebuild HTML from last outputs
```
Console output: clean aligned tables, ANSI tier colors.

### tests/ — unittest: typology classification cases, scoring math, TTS/TTR on a known toy network, mitigation ranking sanity, dashboard file renders and embeds data.

## Style
- Type hints everywhere, dataclasses, no globals; each module has a docstring explaining the concept for a reader learning resilience.
- Deviations from this spec: log in implementation-notes.md under "Deviations", pick the conservative option, keep going.
