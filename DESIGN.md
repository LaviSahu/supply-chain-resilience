# Resilience Radar — Dashboard Design Spec (frozen)

One self-contained `output/dashboard.html` (inline CSS + vanilla JS + inline SVG, zero CDN). It must read as a polished ops product — a supply-chain **control tower** — not a generated report.

## Theme system
Dual theme, dark default. CSS custom properties on `:root`, toggle button stamps `data-theme="light|dark"`; also respect `prefers-color-scheme` when no explicit choice. All colors below are validated (colorblind-safe ordering, contrast-checked) — use exactly these, referenced by role, never raw hex in the body.

```css
:root, :root[data-theme="dark"] {
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#222220;
  --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#199e70; --s3:#c98500; --s4:#008300;
  --s5:#9085e9; --s6:#e66767; --s7:#d55181; --s8:#d95926;
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --critical:#d03b3b;
}
:root[data-theme="light"] {
  --page:#f9f9f7; --surface:#fcfcfb; --surface-2:#f0efec;
  --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
  --s1:#2a78d6; --s2:#1baf7a; --s3:#eda100; --s4:#008300;
  --s5:#4a3aa7; --s6:#e34948; --s7:#e87ba4; --s8:#eb6834;
  /* status colors unchanged */
}
```

Typography: `system-ui, -apple-system, "Segoe UI", sans-serif` everywhere (hero numbers included). `font-variant-numeric: tabular-nums` ONLY in table columns and axis ticks. Text always wears ink tokens, never series colors; a colored chip/mark beside text carries identity.

## Layout
Max-width 1280px centered, 24px gutters, CSS grid. Section order:

1. **Header bar** — small inline-SVG radar glyph (concentric arcs + sweep line, stroke `--s1`), product name "Resilience Radar", subtitle "Supply Chain Resilience Control Tower · Meridian Goods (demo network)", generated-at stamp (passed in at build), theme toggle (sun/moon SVG button).
2. **KPI tile row** — 6 stat tiles in a responsive grid (auto-fit, min 170px): Service Level (baseline %), Revenue at Risk ($), Risk Severity Index, Open Risks (with per-tier mini-count chips), Min TTS (wks), Single-Source Nodes. Tile = hero value (28-32px, ink), label (12px, muted, uppercase tracking), and a one-line context row (e.g. worst scenario name). Delta/status accents use status colors WITH an icon+text, never color alone. Border: 1px `--ring`, radius 10px, background `--surface`.
3. **Network map card** — SVG node-link diagram (~1232×420). Node coords come from `network.json` (x,y hand-set, geo-suggestive: Asia left, EU middle, US right). Node encodes type by SHAPE + color: suppliers = circles `--s2`, plants = rounded squares `--s1`, DCs = diamonds `--s5`, markets = circles `--s3`; 16px min, white 2px ring on the surface. Lanes = curved paths (quadratic), stroke `--axis` 1.5px, arrowheads subtle; lane width scales with weekly flow value (1.5–4px). Nodes/lanes carrying an open CRITICAL/HIGH risk get a status-colored halo ring + a small ⚠ badge with tier letter — plus name label. Every node gets a small always-visible label (11px, `--ink-2`). Hover any node/lane → floating tooltip card (name, type, criticality %, days of cover, open risks). A legend row of shape+label chips sits above the map. Single-source nodes get a dashed halo + "single-source" note in tooltip.
4. **Risk register card** — filter chip row (tier chips: All/Critical/High/Medium/Low with counts; category dropdown) + sortable table (click column headers, sort indicators). Columns: Risk, Category, Affected Element, L, I, Score, Tier, VaR ($k), Exposure (days). Tier column = badge: dot + text label (status color dot, text in ink — never white-on-color). Row hover wash `--surface-2`. Numbers tabular. Default sort: score desc. Cap visible rows ~12 with "show all" expander.
5. **Scenario lab card** — tab row (3 preset scenarios; active tab underline `--s1`). Per tab:
   - Left: **service-level line chart** (SVG ~700×260): baseline series `--s1`, scenario series `--s8`, 2px lines, ≥8px hover markers with 2px surface ring, direct labels at line ends ("Baseline", scenario name) — plus a small legend row. Y axis 0–100% with hairline grid `--grid`, weekly x ticks. Crosshair + shared tooltip on hover (vertical hairline, tooltip shows both values for that week). Shade the outage window (weeks the disruption is active) with a faint `--surface-2` band labeled "outage window".
   - Right: **impact panel**: hero number Lost Revenue ($), TTR, TTS, service-level floor; below, a small horizontal bar chart of weekly lost revenue (sequential blue steps, 4px rounded ends anchored to baseline, 2px gaps, per-bar hover tooltip).
6. **Mitigation card** — per active scenario, ranked table: Action, Mechanism (one line), Cost ($k), Avoided Loss ($k), Net Benefit ($k) rendered as a thin inline bar (`--s2`, 4px rounded end) scaled to max, with the value as a visible label. Top action gets a "RECOMMENDED" chip (dot+text, `--good`).
7. **Footer** — one-line methodology note ("Deterministic time-phased simulation over a modeled network; risk scoring = likelihood × impact; TTR/TTS per Simchi-Levi resilience metrics") + "Built with Resilience Radar" + docs pointer.

## Chart rules (non-negotiable)
- One y-axis per chart, never dual-axis. Hairline grids, no chart borders except the card ring.
- Categorical colors assigned in fixed slot order per entity, never repainted on filter.
- Every chart has a hover/tooltip layer; tooltips are HTML divs positioned near the cursor, surface bg, ring border, 12px text, values bold.
- Legends present for ≥2 series AND direct labels where they fit; single-series charts rely on the title.
- No number printed on every mark — selective labels (ends, max/min) only.
- Cards: `--surface` bg, 1px `--ring` border, radius 12px, 20px padding, 16px section titles (600 weight) with a muted 12px kicker above ("NETWORK", "RISK REGISTER", "WHAT-IF LAB", "MITIGATION").

## JS behavior
Single `<script>` at end: `const DATA = {...}` (embedded at build), then small pure functions render each section into placeholder divs. Tab switching re-renders scenario + mitigation cards. Table sort + filters are client-side. Theme toggle persists via localStorage. No frameworks. Keep the whole file readable — it's part of the showcase.

## Quality bar
Open it and it should look like a product screenshot you'd put in a portfolio hero: aligned grids, consistent spacing (8px system), no text under 11px, no pure #000/#fff mixing, nothing clipped at 1280 or 900px width (cards stack on narrow viewports via grid auto-flow; the network SVG scrolls horizontally in its card rather than squashing).
