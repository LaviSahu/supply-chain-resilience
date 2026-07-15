# Implementation Notes — Resilience Radar (engine build pass)

Scope of this pass: everything in SPEC.md except `dashboard.py` (full
version), `docs/`, and `README.md` — those land in a later chunk.
`dashboard.py` in this pass is an intentional stub: `build_context()` is
real and complete (the contract the future renderer will consume);
`render_dashboard()` writes a minimal placeholder HTML page embedding
that context as JSON.

## Deviations

Per SPEC.md's instruction to log deviations, pick the conservative
option, and keep going. None of these block the two verification
commands (`python3 -m unittest discover -s tests -v`,
`python3 -m resilience_radar demo`), both of which pass cleanly.

1. **Tier score thresholds are invented, not specified.** SPEC.md asks
   for `risk_score = likelihood * impact` (1-25) bucketed into
   CRITICAL/HIGH/MEDIUM/LOW but doesn't give cutoffs. Chose
   `>=20 CRITICAL, >=12 HIGH, >=6 MEDIUM, >=1 LOW` (`scoring.TIER_THRESHOLDS`)
   — roughly quartile-shaped over the 1-25 range, biased so a 4x5 or 5x4
   combination (a highly likely, highly impactful event) reads CRITICAL.

2. **Lane capacity is not pooled across SKUs sharing a lane.** Several
   lanes in `data/network.json` carry multiple SKUs (e.g. L13-L16 each
   carry all 5 SKUs). `simulate.py` runs the propagation independently
   per `(dc, sku)` pair and each SKU can use the lane's *full* stated
   `capacity_units_per_week` — a tractability simplification (the
   two-stage DC-pool architecture already solves the more serious
   cross-*market* double-counting problem; solving cross-*SKU* lane
   sharing too would require a joint per-lane allocation across SKUs
   with some prioritization rule SPEC.md doesn't specify). Conservative
   choice: kept SKUs independent rather than inventing an undocumented
   allocation policy.

3. **`simulate.py`'s propagation uses only DC-level inventory.** Plant
   `inventory_days_of_cover` in `network.json` (e.g. `PLANT-CN`,
   `PLANT-PL`) is used only by `scoring.exposure_days_for_node` for the
   risk register's exposure-days figure — it is not a buffer the
   week-by-week simulation draws down. SPEC.md's propagation description
   ("inventory drains at demand rate... when cover exhausted and
   upstream down -> lost sales") maps most naturally onto DC-level
   stock, since DCs are the last node before markets; adding a second,
   upstream inventory-draining stage at plants was judged out of scope
   for a deterministic weekly model without a specified BOM/production
   schedule.

4. **`port-closure` preset's `capacity_pct` was tuned to `0.0`, not a
   partial value, for a visible effect.** An initial `capacity_pct=0.2`
   (20% throughput surviving a 2-week closure) produced zero service
   degradation once run — DC-SG's inventory buffers (10-14 days) plus
   even 20% capacity fully absorbed a 2-week partial closure. Changed to
   full closure (`0.0`) so the scenario produces a real, pedagogically
   interesting result: SKU-C/D/E dip to 79% service for both outage
   weeks while SKU-A/B stay fully protected via the LA3 air-freight
   bypass lane (Shenzhen Assembly Plant -> Singapore DC, 1-week switch
   lag) — a deliberate protected-vs-unprotected-SKU contrast.

5. **`data/network.json` fix: `L6` no longer carries `SKU-E`.** The
   original draft had both `SUP-DE-PREC` (via L4) and `SUP-IN-PACK` (via
   L6) feeding SKU-E into `PLANT-PL`, which silently broke the intended
   "Rhineland Precision GmbH is the sole, unredundant supplier of
   SKU-E" narrative that the `supplier-failure` preset scenario and
   several risk-register events depend on (`graph.single_source_map`
   correctly reported zero single-sourced SKUs, caught by
   `test_kpi.py::test_compute_kpis_full_catalog`). Fixed by removing
   `SKU-E` from L6's `skus` list — Bengaluru Packaging Solutions now
   only feeds packaging-relevant SKU-C/SKU-D to Wroclaw, matching its
   `category: "packaging"`.

6. **`data/network.json` fix: `L15` capacity lowered from 17,500 to
   5,000 units/week.** With the original capacity, the `demand-spike`
   preset (+40% demand at US East Retail for 3 weeks) produced zero
   visible effect — every individual SKU's shocked demand stayed far
   below the lane's stated capacity (since, per deviation #2, each SKU
   independently gets the lane's full capacity). Lowered DC-US ->
   MKT-US-E capacity so it sits just above baseline peak per-SKU demand
   (max 4,200 units/week, SKU-B) but below several SKUs' shocked demand
   (SKU-B 5,880; SKU-C 5,600), producing a real, bounded dip (worst
   service 97.9%, $98.4k total lost revenue, TTR 3 weeks) without
   touching baseline service level (still 100%).

7. **`mitigate.py`'s `allocation-prioritization` action extended beyond
   the original `capacity_pct` bump.** After fixing deviation #6, the
   scenario still showed *zero* avoided loss for every mitigation lever
   — none of the five actions touch raw lane capacity, only
   `scenario.capacity_pct` (a multiplier that's already `1.0` and
   clamped there for a demand-spike, since nothing reduced it in the
   first place) or DC inventory. This correctly reveals a real
   resilience insight (dual-sourcing and safety stock don't fix a
   distribution-capacity ceiling), but left the playbook with no lever
   at all for a full third of the three preset scenarios, which felt
   like an oversight in the playbook's design rather than an intended
   demonstration. Extended `_apply_allocation_prioritization` to *also*
   add 15% physical capacity to every lane touching the disrupted
   element (in addition to its existing 15pp `capacity_pct` recovery),
   modeling "squeeze extra throughput out of the constrained link" more
   literally. This is still the cheapest lever ($8k) and now correctly
   shows a positive, recommended net benefit for `demand-spike`
   ($88.7k avoided) while remaining structurally weaker than
   `dual-source` for pure supply-cut scenarios.

8. **`pre-build-buffer` and `safety-stock-uplift` share one underlying
   mechanism** (extra starting DC inventory via
   `inventory_days_of_cover`), differing only in magnitude (3 vs 7 extra
   days) and cost model (`COGS_FRACTION` one-time spend vs prorated
   `HOLDING_COST_RATE_ANNUAL` carrying cost) — framed in SPEC.md/README
   language as two distinct playbook entries (a permanent policy change
   vs. a one-off pre-build), but mechanically both are
   "front-load inventory." Similarly, **`dual-source` and
   `allocation-prioritization` share the `capacity_pct` boost
   mechanism** (50pp vs 15pp), differing in cost and (after deviation
   #7) whether they also touch raw lane capacity. This wasn't hidden —
   each pair produces genuinely different re-simulation results at
   different costs — but they are not five independent simulation
   levers, only three (capacity restoration, inventory front-load,
   switch-lag removal) at five cost/magnitude points.

9. **CLI default data-path resolution** (`cli.py::_resolve`) prefers a
   path relative to the current working directory and falls back to a
   path relative to the repo root (derived from `__file__`). SPEC.md
   doesn't specify invocation-directory behavior; this makes
   `python -m resilience_radar demo` work identically whether invoked
   from the repo root (the documented case) or elsewhere, without
   requiring `--network`/`--events` flags in the common case.

10. **Test suite path shim: `tests/_bootstrap.py`, not `tests/__init__.py`.**
    `python -m unittest discover -s tests` (no `-t`) treats `tests/` as
    its own top-level directory and imports `test_*.py` as flat
    top-level modules, not as `tests.test_*` — so code in
    `tests/__init__.py` never executes in that invocation and can't be
    used to extend `sys.path`. Every test module instead starts with a
    plain `import _bootstrap` (works because `unittest discover` already
    puts `tests/` itself on `sys.path`), which inserts `src/`. This
    keeps the exact verification command
    (`python3 -m unittest discover -s tests -v`) runnable from a bare
    `python3` with zero environment setup, while the Makefile's
    `PYTHONPATH=src` continues to serve the `demo`/`dashboard`/`test`
    targets consistently. `tests/__init__.py` is kept (marks the
    directory as a package for other tooling, e.g. pytest) but is not
    load-bearing for the specified `unittest discover` invocation.

## Dashboard build pass (real renderer)

Replaced the `render_dashboard` stub with the full self-contained
control tower per DESIGN.md. `build_context` signature/shape is
UNCHANGED — no context-dict extension was needed (`generated_at` was
already present, so the header stamp reads straight from it). Verified:
`python3 -m unittest discover -s tests` → 74 tests OK (67 original + 7
new dashboard structural/self-containment tests); `demo` writes
`output/dashboard.html` (~81 KB); HTML tag-balance parse clean; embedded
`const DATA` round-trips as JSON; rendered in a real browser (dark +
light, all six sections, tab switching, hover tooltips, 1360px & 900px)
with zero console errors.

### Deviations (dashboard pass)

D1. **Node/lane "white 2px ring" → `var(--surface)` ring.** DESIGN.md
    says nodes get a "white 2px ring on the surface". A literal white
    ring is invisible on the light-theme surface. Used a
    surface-colored 2px ring instead — the standard dataviz
    "2px surface ring on overlapping marks" convention, which is what
    "ring on the surface" means and reads correctly in BOTH themes.

D2. **RECOMMENDED chip shown on the top-ranked action only.** The engine
    marks EVERY positive-net-benefit mitigation `recommended: true`
    (three of five for supplier-failure). DESIGN.md says "Top action
    gets a 'RECOMMENDED' chip" (singular). Followed DESIGN literally:
    the chip renders only on list index 0 (and only if it is flagged
    recommended). The per-action economics (cost / avoided / net
    benefit bar) still convey each action's standing.

D3. **Network SVG viewBox padded to `-54 -8 1338 452`** (from the nominal
    ~1232×420). Hand-set node coords place the leftmost node at x=50 with
    a centered name label that overflowed the left edge; the negative-
    origin padding gives labels breathing room so nothing clips, while
    `min-width:1000px` inside an `overflow-x:auto` card preserves the
    "scrolls rather than squashes" rule on narrow viewports.

## Not deviations, but worth flagging

- `llm.py`'s `AnthropicProvider`/`OpenAIProvider` network-call lines are
  marked `# pragma: no cover - network` and are never exercised by the
  test suite or `demo` — `RuleBasedFallback` (wrapping
  `typology.classify_event`) is the only classifier path that runs
  offline, matching SPEC.md's "zero-key offline demo" requirement.
- `graph.py` keeps `revenue_dependency_set`/`dependency_chain_lanes` as
  backward-compatible aliases for the generalized
  `upstream_node_set`/`upstream_chain_lanes` (needed once DC-level
  upstream dependency queries were added for the two-stage simulation
  architecture) — both names are used across the codebase; not a
  deviation, just a naming note for a future reader.

## Review pass (post-build)
- Fixed: `.barlist .fill` / `.netbar .fill` were inline `<span>`s so `width`/`height` never applied — bars rendered as empty tracks. Added `display:block`.
- Fixed: negative net-benefit rows drew a minimum-width green (positive-coded) bar; now zero-width fill, value label carries the sign.

## Design elevation pass (Fable, post-review)
- Network map re-laid out as 4-column echelon flow (suppliers → plants → DCs → markets) with data-driven column headers; deviation from DESIGN.md "geo-suggestive" coords — the flow layout eliminates lane tangle and dead space.
- Backup (non-primary) lanes now dashed with wider arc + legend entry.
- Risk badges: floating ⚠ text → compact ringed disc with tier letter.
- Single-source halo moved from fed plant to the sole-source supplier (`f.supplier_id`) — matches practitioner reading.
- Scenario chart: shaded band between baseline and scenario (the lost-service gap); an under-the-line area fill was tried and rejected (washes the plot when service ≈ 100%).
- Header: DEMO DATA chip + radar sweep animation (disabled under prefers-reduced-motion).
- KPI tiles: de-duplicated context glyphs, hover accent border.
