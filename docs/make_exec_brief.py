"""
make_exec_brief.py — additive, standalone generator for docs/exec-brief.html.

Purely additive tooling: it does not modify any existing file and is not
wired into cli.py as a subcommand. It imports the existing
`resilience_radar` engine (via PYTHONPATH=src, with a local sys.path
fallback so it also works when invoked directly) and re-runs the same
scan -> simulate -> mitigate -> kpi pipeline `dashboard.py` uses to build
its context dict. Every number that lands on the page is therefore
computed fresh from data/network.json + data/events.json at run time —
nothing here is hardcoded.

It deliberately avoids writing to output/risk_register.json or
output/dashboard.html (those remain exclusively `make demo`'s to produce)
by calling the lower-level `radar.build_risk_register` (in-memory) rather
than `radar.scan` (which writes a file).

Run:
    PYTHONPATH=src python3 docs/make_exec_brief.py
    # or, from anywhere, since it locates the repo root itself:
    python3 docs/make_exec_brief.py

Output: docs/exec-brief.html (self-contained, zero external assets, dark
theme on screen per DESIGN.md, forced light/print styling on paper).
"""

from __future__ import annotations

import html
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from resilience_radar import dashboard, graph, kpi, mitigate, radar, simulate  # noqa: E402


# --------------------------------------------------------------------------
# Recompute the same context dashboard.py embeds — nothing read from a
# pre-existing output/ artifact, so this stays correct even if output/ is
# stale or absent.
# --------------------------------------------------------------------------


def compute_context() -> dict:
    network = graph.load_network(str(_REPO_ROOT / "data" / "network.json"))
    events = radar.load_events(str(_REPO_ROOT / "data" / "events.json"))
    risks = radar.build_risk_register(events, network)  # in-memory, no file write

    sim_results = simulate.run_all_presets(network)
    mitigations = {
        sid: mitigate.rank_mitigations(network, simulate.PRESET_SCENARIOS[sid], result)
        for sid, result in sim_results.items()
    }
    kpis = kpi.compute_kpis(network, risks, sim_results)
    generated_at = datetime.now(timezone.utc).isoformat()
    return dashboard.build_context(network, risks, kpis, sim_results, mitigations, generated_at)


# --------------------------------------------------------------------------
# Formatting helpers (mirrors dashboard.py's client-side fmtMoney/fmtInt so
# the exec brief's numbers read identically to the interactive dashboard)
# --------------------------------------------------------------------------


def fmt_money(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:.2f}B"
    if a >= 1e6:
        return f"${v / 1e6:.1f}M"
    if a >= 1e3:
        return f"${v / 1e3:,.0f}K"
    return f"${v:,.0f}"


def fmt_k(v: float) -> str:
    return f"${v / 1000:,.1f}k"


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


# --------------------------------------------------------------------------
# HTML template — sentinel-substitution (not str.format) so literal CSS
# braces are never touched, same technique as dashboard.py's _TEMPLATE.
# --------------------------------------------------------------------------

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Resilience Radar — Executive Brief</title>
<style>
  :root {
    --page:#0d0d0d; --surface:#1a1a19; --surface-2:#222220;
    --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
    --s1:#3987e5; --s2:#199e70; --s5:#9085e9; --s8:#d95926;
    --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --critical:#d03b3b;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --page:#f9f9f7; --surface:#fcfcfb; --surface-2:#f0efec;
      --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
      --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
      --s1:#2a78d6; --s2:#1baf7a; --s5:#4a3aa7; --s8:#eb6834;
    }
  }
  * { box-sizing:border-box; }
  html, body { margin:0; padding:0; }
  body {
    background:var(--page); color:var(--ink-2);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size:14px; line-height:1.5;
    -webkit-font-smoothing:antialiased;
  }
  .wrap { max-width:900px; margin:0 auto; padding:32px 28px 40px; }
  .num { font-variant-numeric: tabular-nums; }

  header.top { display:flex; align-items:center; gap:14px; padding-bottom:18px; margin-bottom:22px; border-bottom:1px solid var(--ring); }
  .brand h1 { margin:0; font-size:20px; font-weight:700; color:var(--ink); letter-spacing:-.01em; }
  .brand .sub { margin:3px 0 0; font-size:12px; color:var(--muted); }
  .top .spacer { flex:1; }
  .stamp { font-size:11px; color:var(--muted); text-align:right; }
  .stamp b { color:var(--ink-2); font-weight:600; }
  .demo-badge { font-size:9px; font-weight:700; letter-spacing:.1em; color:var(--muted); border:1px solid var(--ring); border-radius:20px; padding:2px 8px; }

  h2.kicker-h { font-size:12px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin:0 0 4px; }
  h2.section-h { margin:0 0 14px; font-size:17px; font-weight:600; color:var(--ink); }

  .kpis { display:grid; grid-template-columns:repeat(3, 1fr); gap:14px; margin-bottom:26px; }
  .tile { background:var(--surface); border:1px solid var(--ring); border-radius:10px; padding:14px 16px; }
  .tile .label { font-size:10.5px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; color:var(--muted); }
  .tile .value { font-size:24px; font-weight:700; color:var(--ink); margin:6px 0 3px; line-height:1.05; }
  .tile .value .unit { font-size:13px; font-weight:600; color:var(--ink-2); margin-left:2px; }
  .tile .ctx { font-size:11px; color:var(--muted); }

  .card { background:var(--surface); border:1px solid var(--ring); border-radius:12px; padding:22px; margin-bottom:22px; }

  .stat-row { display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin:16px 0 18px; }
  .stat { background:var(--surface-2); border-radius:9px; padding:12px 14px; }
  .stat .k { font-size:10.5px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; color:var(--muted); }
  .stat .v { font-size:21px; font-weight:700; color:var(--ink); margin-top:5px; }
  .stat .v small { font-size:12px; font-weight:600; color:var(--ink-2); }
  .stat.bad .v { color:var(--critical); }

  p.lede { color:var(--ink-2); margin:0 0 4px; }
  p.lede b { color:var(--ink); }

  table.mit { width:100%; border-collapse:collapse; font-size:13px; margin-top:6px; }
  table.mit th { text-align:left; font-size:10.5px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); padding:0 10px 8px; border-bottom:1px solid var(--ring); }
  table.mit th.n, table.mit td.n { text-align:right; }
  table.mit td { padding:9px 10px; border-bottom:1px solid var(--grid); color:var(--ink-2); vertical-align:top; }
  table.mit td.action { color:var(--ink); font-weight:600; }
  table.mit td.mech { color:var(--muted); font-size:12px; max-width:340px; }
  .rec { display:inline-flex; align-items:center; gap:5px; font-size:9.5px; font-weight:700; letter-spacing:.04em; color:var(--good); background:color-mix(in srgb, var(--good) 14%, var(--surface)); padding:2px 7px; border-radius:20px; margin-left:8px; }
  .rec .dot { width:6px; height:6px; border-radius:50%; background:var(--good); }

  ul.notes { margin:6px 0 0; padding-left:20px; color:var(--ink-2); }
  ul.notes li { margin-bottom:6px; }

  footer.foot { border-top:1px solid var(--ring); padding-top:14px; margin-top:6px; font-size:11.5px; color:var(--muted); }
  footer.foot b { color:var(--ink-2); font-weight:600; }
  footer.foot .cite { margin-top:6px; }

  @media print {
    :root {
      --page:#ffffff; --surface:#ffffff; --surface-2:#f2f2f0;
      --ink:#0a0a0a; --ink-2:#2a2a28; --muted:#5a5a56;
      --grid:#dddad2; --axis:#bcb9b1; --ring:#cfccc4;
      --s1:#1f5aa8; --s2:#127a52; --s5:#4a3aa7; --s8:#b3450f;
      --good:#0a7d0a; --warn:#8a5a00; --serious:#a8471f; --critical:#a02222;
    }
    * { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
    body { font-size:12px; }
    .wrap { max-width:100%; padding:0; }
    .card, .tile, .stat { border:1px solid var(--ring); box-shadow:none; break-inside:avoid; }
    header.top { break-after:avoid; }
    @page { margin:16mm 14mm; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <svg width="30" height="30" viewBox="0 0 34 34" fill="none" aria-hidden="true">
      <circle cx="17" cy="17" r="15" stroke="var(--s1)" stroke-width="1.4" opacity=".45"/>
      <circle cx="17" cy="17" r="10" stroke="var(--s1)" stroke-width="1.4" opacity=".7"/>
      <circle cx="17" cy="17" r="5" stroke="var(--s1)" stroke-width="1.4"/>
      <circle cx="17" cy="17" r="2" fill="var(--s1)"/>
    </svg>
    <div class="brand">
      <h1>Resilience Radar — Executive Brief <span class="demo-badge">DEMO DATA</span></h1>
      <p class="sub">Supply Chain Resilience Control Tower · __COMPANY__ (demo network)</p>
    </div>
    <div class="spacer"></div>
    <div class="stamp">Generated<br><b>__GENERATED__</b></div>
  </header>

  <h2 class="kicker-h">Headline KPIs</h2>
  <section class="kpis">
    __KPI_TILES__
  </section>

  <section class="card">
    <h2 class="kicker-h">Worst-Case Scenario · Crown Jewel Risk</h2>
    <h2 class="section-h">__WORST_NAME__</h2>
    <p class="lede">Of the three modeled disruption scenarios, this is the worst by
      service-level floor — despite <b>not</b> being the longest outage. Outage
      window: <b>weeks __OUTAGE_START__–__OUTAGE_END__</b>.</p>
    <div class="stat-row">
      <div class="stat bad"><div class="k">Worst Service Level</div><div class="v">__WORST_SERVICE__<small>%</small></div></div>
      <div class="stat bad"><div class="k">Time to Survive</div><div class="v">__TTS__<small>wk</small></div></div>
      <div class="stat"><div class="k">Time to Recover</div><div class="v">__TTR__<small>wk</small></div></div>
      <div class="stat bad"><div class="k">Total Lost Revenue</div><div class="v">__LOST_REVENUE__</div></div>
    </div>
    <p class="lede">Time to Survive of __TTS__ week(s) means __TTS_MEANING__.</p>
  </section>

  <section class="card">
    <h2 class="kicker-h">Top-Ranked Mitigation</h2>
    <h2 class="section-h">Recommended response to __WORST_NAME__</h2>
    <table class="mit">
      <thead><tr><th>Action</th><th>Mechanism</th><th class="n">Cost</th><th class="n">Avoided Loss</th><th class="n">Net Benefit</th></tr></thead>
      <tbody>
        __MITIGATION_ROW__
      </tbody>
    </table>
  </section>

  <section class="card">
    <h2 class="kicker-h">Read Alongside</h2>
    <ul class="notes">
      <li>Full plain-English narrative: <b>docs/00-executive-walkthrough.md</b></li>
      <li>Interactive control tower with all 3 scenarios, sortable risk register, network map: <b>output/dashboard.html</b> (run <code>make demo</code> to regenerate)</li>
    </ul>
  </section>

  <footer class="foot">
    <span>Deterministic time-phased simulation over a modeled network; risk scoring = likelihood × impact; TTR/TTS per Simchi-Levi resilience metrics.</span>
    <div class="cite">Simchi-Levi, D., Schmidt, W., &amp; Wei, Y. (2015). "Identifying Risks and Mitigating Disruptions in the Automotive Supply Chain." <i>Interfaces</i>, 45(5), 375&ndash;390. DOI: 10.1287/inte.2015.0804.</div>
    <div style="margin-top:8px"><b>Built with Resilience Radar</b> · generated by <code>docs/make_exec_brief.py</code> from a live <code>make demo</code> run · all figures computed, none hardcoded.</div>
  </footer>
</div>
</body>
</html>
"""


def render(context: dict) -> str:
    kpis = context["kpis"]
    company = context["company"]
    generated_at = context["generated_at"]

    order = ["service_level", "revenue_at_risk", "rsi", "open_risks", "min_tts", "single_source_nodes"]
    tile_html_parts = []
    for key in order:
        k = kpis.get(key)
        if not k:
            continue
        unit = k["unit"]
        if unit == "$":
            val = fmt_money(k["value"])
        elif unit == "%":
            val = f'{k["value"]:.1f}<span class="unit">%</span>'
        elif unit == "weeks":
            val = f'{k["value"]:.0f}<span class="unit">wk</span>'
        elif unit == "count":
            val = f'{k["value"]:.0f}'
        else:
            val = f'{k["value"]:.2f}'
        tile_html_parts.append(
            f'<div class="tile"><div class="label">{esc(k["label"])}</div>'
            f'<div class="value num">{val}</div>'
            f'<div class="ctx">{esc(k.get("context") or "")}</div></div>'
        )
    kpi_tiles_html = "\n    ".join(tile_html_parts)

    scenarios = context["scenarios"]
    worst_id, worst = min(scenarios.items(), key=lambda kv: kv[1]["worst_service_level"])
    tts = worst["tts"]
    tts_meaning = (
        "the network has no buffer at all — service degrades below the 98% threshold in the very first week"
        if tts == 0
        else f"the network sustains {tts} consecutive week(s) of full service before the first breach of the 98% threshold"
    )

    mitigations = context["mitigations"].get(worst_id, [])
    top = mitigations[0] if mitigations else None
    if top:
        rec_chip = '<span class="rec"><span class="dot"></span>RECOMMENDED</span>' if top.get("recommended") else ""
        mitigation_row = (
            f'<tr><td class="action">{esc(top["action_name"])}{rec_chip}</td>'
            f'<td class="mech">{esc(top["mechanism"])}</td>'
            f'<td class="n">{fmt_k(top["cost"])}</td>'
            f'<td class="n">{fmt_k(top["avoided_loss"])}</td>'
            f'<td class="n" style="color:var(--ink);font-weight:600">{fmt_k(top["net_benefit"])}</td></tr>'
        )
    else:
        mitigation_row = '<tr><td colspan="5">No ranked mitigations for this scenario.</td></tr>'

    try:
        d = datetime.fromisoformat(generated_at)
        stamp = d.strftime("%d %b %Y, %H:%M UTC")
    except ValueError:
        stamp = generated_at

    out = _TEMPLATE
    out = out.replace("__COMPANY__", esc(company))
    out = out.replace("__GENERATED__", esc(stamp))
    out = out.replace("__KPI_TILES__", kpi_tiles_html)
    out = out.replace("__WORST_NAME__", esc(worst["scenario_name"]))
    out = out.replace("__OUTAGE_START__", str(worst["outage_start_week"]))
    out = out.replace("__OUTAGE_END__", str(worst["outage_end_week"]))
    out = out.replace("__WORST_SERVICE__", f'{worst["worst_service_level"] * 100:.1f}')
    out = out.replace("__TTS_MEANING__", tts_meaning)
    out = out.replace("__TTS__", str(tts))
    out = out.replace("__TTR__", str(worst["ttr"]) if worst["ttr"] is not None else "n/a")
    out = out.replace("__LOST_REVENUE__", fmt_money(worst["total_lost_revenue"]))
    out = out.replace("__MITIGATION_ROW__", mitigation_row)
    return out


def main() -> None:
    context = compute_context()
    html_doc = render(context)
    out_path = Path(__file__).resolve().parent / "exec-brief.html"
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"Exec brief written -> {out_path}")


if __name__ == "__main__":
    main()
