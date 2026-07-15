"""
dashboard.py — the self-contained HTML control tower.

`build_context(...)` assembles the exact JSON-serializable dict the
dashboard's `<script>const DATA = {...}</script>` blob embeds: KPI tiles,
the risk register, the network (coordinates + computed criticality /
single-source flags for the map), every preset scenario's baseline-vs-
scenario weekly series, and ranked mitigations per scenario.

`render_dashboard(context, out_path)` renders a single, zero-CDN
`output/dashboard.html` — inline CSS (dual theme), vanilla JS, inline SVG —
following DESIGN.md exactly. The context JSON is embedded once as
`const DATA = {...}` and every section is drawn client-side by a small
pure JS function.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import graph
from .kpi import Kpi
from .mitigate import MitigationResult
from .models import Network, Risk, SimResult, jsonable


def _network_context(network: Network) -> dict:
    node_crit = graph.node_criticality(network)
    lane_crit = graph.lane_criticality(network)
    single_source = graph.single_source_map(network)
    # The dashed "single-source" halo marks the sole-source supplier itself —
    # the node whose failure stops a SKU — not the plant it feeds.
    single_source_node_ids = {f.supplier_id for f in single_source}

    nodes = []
    for n in network.nodes:
        nodes.append(
            {
                "id": n.id,
                "name": n.name,
                "type": n.type.value,
                "region": n.region,
                "country": n.country,
                "x": n.x,
                "y": n.y,
                "port_dependency": n.port_dependency,
                "criticality": round(node_crit.get(n.id, 0.0), 4),
                "single_source": n.id in single_source_node_ids,
                "inventory_days_of_cover": dict(n.inventory_days_of_cover),
                "weekly_demand": dict(n.weekly_demand),
            }
        )

    lanes = []
    for l in network.lanes:
        lanes.append(
            {
                "id": l.id,
                "source": l.source,
                "target": l.target,
                "mode": l.mode.value,
                "lead_time_days": l.lead_time_days,
                "capacity_units_per_week": l.capacity_units_per_week,
                "skus": list(l.skus),
                "primary": l.primary,
                "switch_lag_weeks": l.switch_lag_weeks,
                "criticality": round(lane_crit.get(l.id, 0.0), 4),
                "flow_units": graph.lane_flow_units(l),
            }
        )

    return {
        "company": network.company,
        "nodes": nodes,
        "lanes": lanes,
        "skus": [jsonable(s) for s in network.skus],
        "single_source_flags": [jsonable(f) for f in single_source],
        "hhi_by_category": graph.hhi_by_category(network),
        "total_weekly_revenue": round(graph.total_weekly_revenue(network), 2),
    }


def build_context(
    network: Network,
    risks: list[Risk],
    kpis: dict[str, Kpi],
    sim_results: dict[str, SimResult],
    mitigations: dict[str, list[MitigationResult]],
    generated_at: str,
) -> dict:
    """
    Assemble everything the dashboard needs into one JSON-serializable dict.
    This is the contract between the engine and the renderer — designed so
    the renderer never recomputes anything, only formats what's here.
    """
    return {
        "generated_at": generated_at,
        "company": network.company,
        "kpis": {key: jsonable(kpi) for key, kpi in kpis.items()},
        "network": _network_context(network),
        "risk_register": [jsonable(r) for r in risks],
        "scenarios": {
            scenario_id: jsonable(result) for scenario_id, result in sim_results.items()
        },
        "mitigations": {
            scenario_id: [jsonable(m) for m in results]
            for scenario_id, results in mitigations.items()
        },
    }


# --------------------------------------------------------------------------
# The dashboard template. Built with a __DATA_JSON__ sentinel (not str.format)
# so every literal { } in the CSS/JS stays literal. The context JSON is
# embedded once; </ is escaped to <\/ so an embedded string can never close
# the <script> element early.
# --------------------------------------------------------------------------

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Resilience Radar — Control Tower</title>
<style>
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
    --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --critical:#d03b3b;
  }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme]) {
      --page:#f9f9f7; --surface:#fcfcfb; --surface-2:#f0efec;
      --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
      --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
      --s1:#2a78d6; --s2:#1baf7a; --s3:#eda100; --s4:#008300;
      --s5:#4a3aa7; --s6:#e34948; --s7:#e87ba4; --s8:#eb6834;
    }
  }

  * { box-sizing:border-box; }
  html, body { margin:0; padding:0; }
  body {
    background:var(--page); color:var(--ink-2);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size:14px; line-height:1.45;
    -webkit-font-smoothing:antialiased;
  }
  .wrap { max-width:1280px; margin:0 auto; padding:24px; }
  .num { font-variant-numeric: tabular-nums; }

  /* ---- header ---- */
  header.top {
    display:flex; align-items:center; gap:16px;
    padding-bottom:20px; margin-bottom:24px;
    border-bottom:1px solid var(--ring);
  }
  .brand { display:flex; align-items:center; gap:12px; }
  .brand svg { display:block; }
  .brand h1 { margin:0; font-size:19px; font-weight:700; color:var(--ink); letter-spacing:-.01em; display:flex; align-items:center; gap:8px; }
  .brand .sub { margin:2px 0 0; font-size:12px; color:var(--muted); }
  .brand .demo { font-size:9px; font-weight:700; letter-spacing:.1em; color:var(--muted); border:1px solid var(--ring); border-radius:20px; padding:2px 8px; position:relative; top:-1px; }
  .brand .sweep { transform-origin:17px 17px; animation:sweep 6s linear infinite; }
  @keyframes sweep { to { transform:rotate(360deg); } }
  @media (prefers-reduced-motion: reduce){ .brand .sweep { animation:none; } }
  .top .spacer { flex:1; }
  .stamp { font-size:12px; color:var(--muted); text-align:right; }
  .stamp b { color:var(--ink-2); font-weight:600; }
  .themebtn {
    display:flex; align-items:center; justify-content:center;
    width:38px; height:38px; border-radius:9px;
    background:var(--surface); border:1px solid var(--ring);
    color:var(--ink-2); cursor:pointer; padding:0;
  }
  .themebtn:hover { background:var(--surface-2); color:var(--ink); }
  .themebtn .moon { display:none; }
  :root[data-theme="dark"] .themebtn .sun { display:none; }
  :root[data-theme="dark"] .themebtn .moon { display:block; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme]) .themebtn .sun { display:none; }
    :root:not([data-theme]) .themebtn .moon { display:block; }
  }

  /* ---- KPI tiles ---- */
  .kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px,1fr)); gap:16px; margin-bottom:24px; }
  .tile { background:var(--surface); border:1px solid var(--ring); border-radius:10px; padding:16px; transition:border-color .15s; }
  .tile:hover { border-color:color-mix(in srgb, var(--s1) 35%, var(--ring)); }
  .tile .label { font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
  .tile .value { font-size:30px; font-weight:700; color:var(--ink); margin:8px 0 4px; line-height:1.05; }
  .tile .value .unit { font-size:15px; font-weight:600; color:var(--ink-2); margin-left:2px; }
  .tile .ctx { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--muted); }
  .tile .ctx .dot { width:8px; height:8px; border-radius:50%; flex:none; }
  .tier-chips { display:flex; flex-wrap:wrap; gap:5px; margin-top:8px; }
  .tier-chip { display:inline-flex; align-items:center; gap:4px; font-size:11px; color:var(--ink-2); padding:2px 7px; border-radius:20px; background:var(--surface-2); }
  .tier-chip .dot { width:7px; height:7px; border-radius:50%; }

  /* ---- cards ---- */
  .card { background:var(--surface); border:1px solid var(--ring); border-radius:12px; padding:20px; margin-bottom:24px; }
  .kicker { font-size:12px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
  .card h2 { margin:4px 0 0; font-size:16px; font-weight:600; color:var(--ink); }
  .card .head { display:flex; align-items:flex-end; gap:16px; margin-bottom:16px; flex-wrap:wrap; }
  .card .head .note { font-size:12px; color:var(--muted); margin-left:auto; }

  /* ---- network map ---- */
  .legendrow { display:flex; flex-wrap:wrap; gap:14px; margin-bottom:12px; }
  .legendrow .item { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--ink-2); }
  .netscroll { overflow-x:auto; overflow-y:hidden; border-radius:8px; }
  .netscroll svg { display:block; min-width:1000px; width:100%; height:auto; }
  .nodelabel { font-size:11px; fill:var(--ink-2); }
  .colhead { font-size:10px; font-weight:700; letter-spacing:.14em; fill:var(--muted); }
  .badge-txt { font-size:9px; font-weight:700; }

  /* ---- risk register ---- */
  .filters { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:14px; }
  .chip { font-size:12px; color:var(--ink-2); background:var(--surface-2); border:1px solid transparent; border-radius:20px; padding:4px 11px; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }
  .chip .dot { width:8px; height:8px; border-radius:50%; }
  .chip.active { border-color:var(--s1); color:var(--ink); background:color-mix(in srgb, var(--s1) 14%, var(--surface)); }
  .chip .cnt { color:var(--muted); font-variant-numeric:tabular-nums; }
  select.cat { font-family:inherit; font-size:12px; color:var(--ink-2); background:var(--surface-2); border:1px solid var(--ring); border-radius:8px; padding:5px 9px; cursor:pointer; margin-left:auto; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  thead th { text-align:left; font-size:11px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); padding:0 10px 10px; border-bottom:1px solid var(--ring); cursor:pointer; white-space:nowrap; user-select:none; }
  thead th.n, tbody td.n { text-align:right; }
  thead th .arr { color:var(--s1); font-size:10px; }
  tbody td { padding:10px; border-bottom:1px solid var(--grid); color:var(--ink-2); vertical-align:top; }
  tbody tr:hover td { background:var(--surface-2); }
  tbody td.n { font-variant-numeric:tabular-nums; }
  tbody td.risk { color:var(--ink); max-width:340px; }
  tbody td.risk .rid { display:block; font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums; margin-top:2px; }
  .tierbadge { display:inline-flex; align-items:center; gap:6px; white-space:nowrap; }
  .tierbadge .dot { width:9px; height:9px; border-radius:50%; flex:none; }
  .tierbadge .t { color:var(--ink); font-size:12px; font-weight:600; }
  .showall { margin-top:12px; }
  .showall button { font-family:inherit; font-size:12px; color:var(--s1); background:none; border:none; cursor:pointer; padding:6px 0; font-weight:600; }
  .showall button:hover { text-decoration:underline; }

  /* ---- scenario lab ---- */
  .tabs { display:flex; gap:4px; border-bottom:1px solid var(--ring); margin-bottom:18px; flex-wrap:wrap; }
  .tab { font-family:inherit; font-size:13px; color:var(--ink-2); background:none; border:none; padding:9px 14px; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; }
  .tab:hover { color:var(--ink); }
  .tab.active { color:var(--ink); font-weight:600; border-bottom-color:var(--s1); }
  .lab { display:grid; grid-template-columns:minmax(0,1.55fr) minmax(0,1fr); gap:24px; align-items:start; }
  @media (max-width:820px){ .lab { grid-template-columns:1fr; } }
  .chartwrap { position:relative; }
  .chartwrap svg { display:block; width:100%; height:auto; }
  .legendrow.mini { margin:0 0 6px; }
  .impact .row { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px; }
  .impact .stat { background:var(--surface-2); border-radius:9px; padding:12px 14px; }
  .impact .stat .k { font-size:11px; font-weight:600; letter-spacing:.05em; text-transform:uppercase; color:var(--muted); }
  .impact .stat .v { font-size:22px; font-weight:700; color:var(--ink); margin-top:5px; font-variant-numeric:tabular-nums; }
  .impact .stat .v small { font-size:12px; font-weight:600; color:var(--ink-2); }
  .barlist .brow { display:flex; align-items:center; gap:10px; margin-bottom:9px; }
  .barlist .wk { font-size:11px; color:var(--muted); width:38px; flex:none; font-variant-numeric:tabular-nums; }
  .barlist .track { flex:1; height:16px; background:var(--surface-2); border-radius:4px; overflow:hidden; }
  .barlist .fill { display:block; height:100%; border-radius:4px; cursor:pointer; }
  .barlist .amt { font-size:11px; color:var(--ink-2); width:74px; text-align:right; flex:none; font-variant-numeric:tabular-nums; }
  .subttl { font-size:12px; font-weight:600; color:var(--ink-2); margin:0 0 10px; }

  /* ---- mitigation ---- */
  td.mbar { width:42%; }
  .netbar { display:flex; align-items:center; gap:10px; }
  .netbar .track { flex:1; height:14px; background:var(--surface-2); border-radius:4px; overflow:hidden; }
  .netbar .fill { display:block; height:100%; background:var(--s2); border-radius:4px; }
  .netbar .amt { font-size:12px; color:var(--ink); font-weight:600; width:70px; text-align:right; flex:none; font-variant-numeric:tabular-nums; }
  .rec { display:inline-flex; align-items:center; gap:5px; font-size:10px; font-weight:700; letter-spacing:.04em; color:var(--good); background:color-mix(in srgb, var(--good) 14%, var(--surface)); padding:2px 7px; border-radius:20px; margin-left:8px; }
  .rec .dot { width:7px; height:7px; border-radius:50%; background:var(--good); }
  td.mech { color:var(--muted); font-size:12px; max-width:320px; }

  /* ---- footer ---- */
  footer.foot { border-top:1px solid var(--ring); padding-top:16px; margin-top:8px; font-size:12px; color:var(--muted); }
  footer.foot b { color:var(--ink-2); font-weight:600; }

  /* ---- tooltip ---- */
  #tip { position:fixed; z-index:50; pointer-events:none; background:var(--surface); border:1px solid var(--ring); border-radius:9px; padding:9px 11px; font-size:12px; color:var(--ink-2); box-shadow:0 6px 24px rgba(0,0,0,.28); max-width:260px; opacity:0; transition:opacity .08s; }
  #tip .tt { color:var(--ink); font-weight:600; margin-bottom:3px; }
  #tip .kv { display:flex; justify-content:space-between; gap:14px; }
  #tip .kv b { color:var(--ink); font-weight:600; font-variant-numeric:tabular-nums; }
  #tip .sw { display:inline-block; width:8px; height:8px; border-radius:2px; margin-right:6px; }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand">
      <svg width="34" height="34" viewBox="0 0 34 34" fill="none" aria-hidden="true">
        <circle cx="17" cy="17" r="15" stroke="var(--s1)" stroke-width="1.4" opacity=".45"/>
        <circle cx="17" cy="17" r="10" stroke="var(--s1)" stroke-width="1.4" opacity=".7"/>
        <circle cx="17" cy="17" r="5" stroke="var(--s1)" stroke-width="1.4"/>
        <g class="sweep">
          <line x1="17" y1="17" x2="30" y2="8" stroke="var(--s1)" stroke-width="1.6" stroke-linecap="round"/>
        </g>
        <circle cx="17" cy="17" r="2" fill="var(--s1)"/>
      </svg>
      <div>
        <h1>Resilience Radar <span class="demo">DEMO DATA</span></h1>
        <p class="sub" id="subtitle"></p>
      </div>
    </div>
    <div class="spacer"></div>
    <div class="stamp">Generated<br><b id="genstamp"></b></div>
    <button class="themebtn" id="themebtn" title="Toggle theme" aria-label="Toggle light/dark theme">
      <svg class="sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/></svg>
      <svg class="moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
    </button>
  </header>

  <section class="kpis" id="kpis"></section>

  <section class="card">
    <div class="head">
      <div><div class="kicker">Network</div><h2>Supply Network Map</h2></div>
      <div class="note" id="netnote"></div>
    </div>
    <div class="legendrow" id="netlegend"></div>
    <div class="netscroll"><svg id="netmap" viewBox="-30 -34 1260 452" preserveAspectRatio="xMidYMid meet"></svg></div>
  </section>

  <section class="card">
    <div class="head"><div><div class="kicker">Risk Register</div><h2>Scored Disruption Risks</h2></div></div>
    <div class="filters" id="riskfilters"></div>
    <table id="risktable"><thead></thead><tbody></tbody></table>
    <div class="showall" id="riskshowall"></div>
  </section>

  <section class="card">
    <div class="head"><div><div class="kicker">What-If Lab</div><h2>Scenario Impact Simulation</h2></div></div>
    <div class="tabs" id="scentabs"></div>
    <div class="lab">
      <div>
        <div class="legendrow mini" id="scenlegend"></div>
        <div class="chartwrap"><svg id="scenchart" viewBox="0 0 720 264"></svg></div>
      </div>
      <div class="impact" id="scenimpact"></div>
    </div>
  </section>

  <section class="card">
    <div class="head"><div><div class="kicker">Mitigation</div><h2 id="mittitle">Ranked Response Playbook</h2></div></div>
    <table id="mittable"><thead></thead><tbody></tbody></table>
  </section>

  <footer class="foot">
    <span>Deterministic time-phased simulation over a modeled network; risk scoring = likelihood × impact; TTR/TTS per Simchi-Levi resilience metrics.</span><br>
    <b>Built with Resilience Radar</b> · see <b>docs/</b> for methodology.
  </footer>
</div>

<div id="tip"></div>

<script>
const DATA = __DATA_JSON__;

// ---------- helpers ----------
const $ = (s, r) => (r||document).querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const TIER_COLOR = { CRITICAL:'var(--critical)', HIGH:'var(--serious)', MEDIUM:'var(--warn)', LOW:'var(--good)' };
const TIER_RANK = { CRITICAL:4, HIGH:3, MEDIUM:2, LOW:1 };

function fmtMoney(v){
  const a = Math.abs(v);
  if (a >= 1e9) return '$' + (v/1e9).toFixed(2) + 'B';
  if (a >= 1e6) return '$' + (v/1e6).toFixed(1) + 'M';
  if (a >= 1e3) return '$' + Math.round(v/1e3) + 'K';
  return '$' + Math.round(v);
}
function fmtK(v){ return (Math.round(v/1000*10)/10).toLocaleString(); }   // to $k, 1 decimal
function fmtInt(v){ return Math.round(v).toLocaleString(); }

// ---------- tooltip ----------
const tip = $('#tip');
function showTip(html, x, y){
  tip.innerHTML = html;
  tip.style.opacity = '1';
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let lx = x + pad, ly = y + pad;
  if (lx + w > window.innerWidth - 8) lx = x - w - pad;
  if (ly + h > window.innerHeight - 8) ly = y - h - pad;
  tip.style.left = Math.max(8, lx) + 'px';
  tip.style.top  = Math.max(8, ly) + 'px';
}
function hideTip(){ tip.style.opacity = '0'; }

// ============================================================ HEADER
function renderHeader(){
  $('#subtitle').textContent = 'Supply Chain Resilience Control Tower · ' + DATA.company + ' (demo network)';
  let stamp = DATA.generated_at;
  try {
    const d = new Date(DATA.generated_at);
    if (!isNaN(d)) stamp = d.toLocaleString(undefined, {year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) + ' UTC';
  } catch(e){}
  $('#genstamp').textContent = stamp;
}

// ============================================================ KPIs
function kpiVal(k){
  const u = k.unit;
  if (u === '$') return fmtMoney(k.value);
  if (u === '%') return k.value.toFixed(1) + '<span class="unit">%</span>';
  if (u === 'weeks') return fmtInt(k.value) + '<span class="unit">wk</span>';
  if (u === 'count') return fmtInt(k.value);
  return (Math.round(k.value*100)/100).toLocaleString();
}
function renderKpis(){
  const K = DATA.kpis;
  const order = ['service_level','revenue_at_risk','rsi','open_risks','min_tts','single_source_nodes'];
  // status accent per tile: [color, icon-glyph]
  const accent = {
    service_level:  ['var(--good)','●'],
    revenue_at_risk:['var(--serious)','▲'],
    rsi:            ['var(--warn)','◆'],
    open_risks:     ['var(--critical)','▲'],
    min_tts:        ['var(--critical)','▲'],
    single_source_nodes:['var(--warn)','▲'],
  };
  const host = $('#kpis'); host.innerHTML = '';
  order.forEach(key => {
    const k = K[key]; if (!k) return;
    const [col, ico] = accent[key] || ['var(--muted)','●'];
    let extra = '';
    if (key === 'open_risks'){
      const chips = [];
      (k.context.match(/(CRITICAL|HIGH|MEDIUM|LOW):(\d+)/g) || []).forEach(m => {
        const [t, c] = m.split(':');
        chips.push('<span class="tier-chip"><span class="dot" style="background:'+TIER_COLOR[t]+'"></span>'+t[0]+' '+c+'</span>');
      });
      extra = '<div class="tier-chips">'+chips.join('')+'</div>';
    } else {
      extra = '<div class="ctx"><span style="color:'+col+';font-size:10px">'+ico+'</span> '+esc(k.context||'—')+'</div>';
    }
    const tile = document.createElement('div');
    tile.className = 'tile';
    tile.innerHTML = '<div class="label">'+esc(k.label)+'</div><div class="value num">'+kpiVal(k)+'</div>'+extra;
    host.appendChild(tile);
  });
}

// ============================================================ NETWORK MAP
const NODE_STYLE = {
  supplier: {shape:'circle', fill:'var(--s2)', label:'Supplier'},
  plant:    {shape:'square', fill:'var(--s1)', label:'Plant'},
  dc:       {shape:'diamond', fill:'var(--s5)', label:'Distribution Center'},
  market:   {shape:'circle', fill:'var(--s3)', label:'Market'},
};
function nodeElementRisks(){
  // element id -> highest open CRITICAL/HIGH tier touching it
  const nMap = {}, lMap = {}, nList = {}, lList = {};
  DATA.risk_register.forEach(r => {
    if (r.tier !== 'CRITICAL' && r.tier !== 'HIGH') return;
    (r.affected_node_ids||[]).forEach(id => {
      if (!nMap[id] || TIER_RANK[r.tier] > TIER_RANK[nMap[id]]) nMap[id] = r.tier;
      (nList[id] = nList[id] || []).push(r);
    });
    (r.affected_lane_ids||[]).forEach(id => {
      if (!lMap[id] || TIER_RANK[r.tier] > TIER_RANK[lMap[id]]) lMap[id] = r.tier;
      (lList[id] = lList[id] || []).push(r);
    });
  });
  return {nMap, lMap, nList, lList};
}
function shapeSvg(n, s, fill){
  const x = n.x, y = n.y;
  if (NODE_STYLE[n.type].shape === 'square')
    return '<rect x="'+(x-s)+'" y="'+(y-s)+'" width="'+(2*s)+'" height="'+(2*s)+'" rx="4" style="fill:'+fill+';stroke:var(--surface);stroke-width:2"/>';
  if (NODE_STYLE[n.type].shape === 'diamond')
    return '<polygon points="'+x+','+(y-s-1)+' '+(x+s+1)+','+y+' '+x+','+(y+s+1)+' '+(x-s-1)+','+y+'" style="fill:'+fill+';stroke:var(--surface);stroke-width:2"/>';
  return '<circle cx="'+x+'" cy="'+y+'" r="'+s+'" style="fill:'+fill+';stroke:var(--surface);stroke-width:2"/>';
}
function renderNetLegend(){
  const host = $('#netlegend'); host.innerHTML = '';
  const items = [
    ['supplier','Supplier'], ['plant','Plant'], ['dc','Distribution Center'], ['market','Market'],
  ];
  items.forEach(([t, lbl]) => {
    const st = NODE_STYLE[t];
    let g;
    if (st.shape === 'square') g = '<rect x="2" y="2" width="12" height="12" rx="3" style="fill:'+st.fill+'"/>';
    else if (st.shape === 'diamond') g = '<polygon points="8,1 15,8 8,15 1,8" style="fill:'+st.fill+'"/>';
    else g = '<circle cx="8" cy="8" r="7" style="fill:'+st.fill+'"/>';
    host.insertAdjacentHTML('beforeend',
      '<span class="item"><svg width="16" height="16" viewBox="0 0 16 16">'+g+'</svg>'+lbl+'</span>');
  });
  host.insertAdjacentHTML('beforeend',
    '<span class="item"><svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.4" fill="none" style="stroke:var(--critical);stroke-width:2"/></svg>open critical/high risk</span>');
  host.insertAdjacentHTML('beforeend',
    '<span class="item"><svg width="16" height="16" viewBox="0 0 16 16"><circle cx="8" cy="8" r="6" fill="none" style="stroke:var(--warn);stroke-width:1.6;stroke-dasharray:2.5 2.5"/></svg>single-source</span>');
  host.insertAdjacentHTML('beforeend',
    '<span class="item"><svg width="18" height="16" viewBox="0 0 18 16"><line x1="1" y1="8" x2="17" y2="8" style="stroke:var(--axis);stroke-width:2;stroke-dasharray:4 3"/></svg>backup lane</span>');
}
function renderNetwork(){
  const svg = $('#netmap');
  const {nMap, lMap, nList, lList} = nodeElementRisks();
  const byId = {}; DATA.network.nodes.forEach(n => byId[n.id] = n);
  const flows = DATA.network.lanes.map(l => l.flow_units);
  const minF = Math.min(...flows), maxF = Math.max(...flows);
  const laneW = f => maxF === minF ? 2.5 : 1.5 + (f - minF) / (maxF - minF) * 2.5;

  let defs = '<defs><marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse"><path d="M0,1 L9,5 L0,9" fill="none" style="stroke:var(--axis)" stroke-width="1.5" opacity=".6"/></marker></defs>';
  let lanesSvg = '', haloSvg = '', nodesSvg = '', labelsSvg = '', headSvg = '';

  // echelon column headers, data-driven from node coords
  const COL_LABEL = {supplier:'SUPPLIERS', plant:'PLANTS', dc:'DISTRIBUTION', market:'MARKETS'};
  ['supplier','plant','dc','market'].forEach(t => {
    const xs = DATA.network.nodes.filter(n => n.type === t).map(n => n.x);
    if (!xs.length) return;
    const cx = xs.reduce((a,b)=>a+b,0)/xs.length;
    headSvg += '<text class="colhead" x="'+cx+'" y="-16" text-anchor="middle">'+COL_LABEL[t]+'</text>';
  });

  DATA.network.lanes.forEach(l => {
    const a = byId[l.source], b = byId[l.target]; if (!a || !b) return;
    const mx = (a.x + b.x)/2, my = (a.y + b.y)/2;
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
    const off = l.primary ? 10 : 34;                       // backup lanes arc wider
    const cx = mx - dy/len * off, cy = my + dx/len * off;  // curve control point
    const d = 'M'+a.x+','+a.y+' Q'+cx+','+cy+' '+b.x+','+b.y;
    const tier = lMap[l.id];
    if (tier) haloSvg += '<path d="'+d+'" fill="none" style="stroke:'+TIER_COLOR[tier]+';opacity:.32" stroke-width="'+(laneW(l.flow_units)+5)+'" stroke-linecap="round"/>';
    const dash = l.primary ? '' : ' stroke-dasharray="6 5" opacity=".75"';
    lanesSvg += '<path class="lane" data-lane="'+l.id+'" d="'+d+'" fill="none" style="stroke:var(--axis)" stroke-width="'+laneW(l.flow_units).toFixed(2)+'"'+dash+' marker-end="url(#arw)"/>';
  });

  DATA.network.nodes.forEach(n => {
    const s = Math.round(9 + (n.criticality||0) * 7);
    const fill = NODE_STYLE[n.type].fill;
    const tier = nMap[n.id];
    if (n.single_source) haloSvg += '<circle cx="'+n.x+'" cy="'+n.y+'" r="'+(s+7)+'" fill="none" style="stroke:var(--warn);stroke-width:1.6;stroke-dasharray:3 3"/>';
    if (tier) haloSvg += '<circle cx="'+n.x+'" cy="'+n.y+'" r="'+(s+4)+'" fill="none" style="stroke:'+TIER_COLOR[tier]+';stroke-width:2"/>';
    nodesSvg += '<g class="node" data-node="'+n.id+'" style="cursor:pointer">'+shapeSvg(n, s, fill)+'</g>';
    labelsSvg += '<text class="nodelabel" x="'+n.x+'" y="'+(n.y + s + 15)+'" text-anchor="middle">'+esc(n.name)+'</text>';
    if (tier){
      // compact badge: surface disc, tier-colored ring + letter
      const bx = n.x + s + 8, by = n.y - s - 6;
      labelsSvg += '<g><circle cx="'+bx+'" cy="'+by+'" r="7.5" style="fill:var(--surface);stroke:'+TIER_COLOR[tier]+';stroke-width:1.6"/>' +
        '<text class="badge-txt" x="'+bx+'" y="'+(by+3)+'" text-anchor="middle" style="fill:'+TIER_COLOR[tier]+'">'+tier[0]+'</text></g>';
    }
  });

  svg.innerHTML = defs + headSvg + haloSvg + lanesSvg + nodesSvg + labelsSvg;

  // hover
  svg.querySelectorAll('.node').forEach(g => {
    const n = byId[g.dataset.node];
    const move = e => {
      const cover = Object.values(n.inventory_days_of_cover||{});
      const doc = cover.length ? Math.round(cover.reduce((a,b)=>a+b,0)/cover.length) + 'd' : '—';
      const risks = nList[n.id] || [];
      let html = '<div class="tt"><span class="sw" style="background:'+NODE_STYLE[n.type].fill+'"></span>'+esc(n.name)+'</div>';
      html += '<div class="kv"><span>Type</span><b>'+NODE_STYLE[n.type].label+'</b></div>';
      html += '<div class="kv"><span>Region</span><b>'+esc(n.region)+'</b></div>';
      html += '<div class="kv"><span>Criticality</span><b>'+Math.round((n.criticality||0)*100)+'%</b></div>';
      if (doc !== '—') html += '<div class="kv"><span>Days of cover</span><b>'+doc+'</b></div>';
      html += '<div class="kv"><span>Open C/H risks</span><b>'+risks.length+'</b></div>';
      if (n.single_source) html += '<div class="kv" style="color:var(--warn)"><span>⚠ single-source</span><b></b></div>';
      showTip(html, e.clientX, e.clientY);
    };
    g.addEventListener('mousemove', move);
    g.addEventListener('mouseleave', hideTip);
  });
  const laneById = {}; DATA.network.lanes.forEach(l => laneById[l.id] = l);
  svg.querySelectorAll('.lane').forEach(p => {
    const l = laneById[p.dataset.lane];
    p.style.cursor = 'pointer';
    const move = e => {
      let html = '<div class="tt">'+esc(byId[l.source].name)+' → '+esc(byId[l.target].name)+'</div>';
      html += '<div class="kv"><span>Mode</span><b>'+esc(l.mode)+'</b></div>';
      html += '<div class="kv"><span>Lead time</span><b>'+l.lead_time_days+'d</b></div>';
      html += '<div class="kv"><span>Weekly flow</span><b>'+fmtInt(l.flow_units)+'</b></div>';
      html += '<div class="kv"><span>SKUs</span><b>'+l.skus.length+'</b></div>';
      const rk = lList[l.id]||[];
      if (rk.length) html += '<div class="kv" style="color:'+TIER_COLOR[lMap[l.id]]+'"><span>⚠ open risk</span><b>'+rk.length+'</b></div>';
      showTip(html, e.clientX, e.clientY);
    };
    p.addEventListener('mousemove', move);
    p.addEventListener('mouseleave', hideTip);
  });
  $('#netnote').textContent = DATA.network.nodes.length + ' nodes · ' + DATA.network.lanes.length + ' lanes · flow-weighted lanes';
}

// ============================================================ RISK REGISTER
let riskState = { tier:'ALL', cat:'ALL', sortKey:'risk_score', sortDir:-1, showAll:false };
const RISK_COLS = [
  ['risk','Risk',false], ['source_category','Category',false], ['element','Affected Element',false],
  ['likelihood','L',true], ['impact','I',true], ['risk_score','Score',true],
  ['tier','Tier',false], ['value_at_risk','VaR ($k)',true], ['exposure_days','Exposure (d)',true],
];
function riskElement(r){
  const ids = (r.affected_node_ids||[]).concat(r.affected_lane_ids||[]);
  return ids.length ? ids.join(', ') : '—';
}
function renderRiskFilters(){
  const host = $('#riskfilters'); host.innerHTML = '';
  const counts = { ALL:0, CRITICAL:0, HIGH:0, MEDIUM:0, LOW:0 };
  DATA.risk_register.forEach(r => { counts.ALL++; counts[r.tier]++; });
  [['ALL','All'],['CRITICAL','Critical'],['HIGH','High'],['MEDIUM','Medium'],['LOW','Low']].forEach(([t, lbl]) => {
    const dot = t === 'ALL' ? '' : '<span class="dot" style="background:'+TIER_COLOR[t]+'"></span>';
    const c = document.createElement('button');
    c.className = 'chip' + (riskState.tier === t ? ' active' : '');
    c.innerHTML = dot + lbl + ' <span class="cnt">'+counts[t]+'</span>';
    c.onclick = () => { riskState.tier = t; renderRiskFilters(); renderRiskTable(); };
    host.appendChild(c);
  });
  const cats = Array.from(new Set(DATA.risk_register.map(r => r.source_category))).sort();
  const sel = document.createElement('select');
  sel.className = 'cat';
  sel.innerHTML = '<option value="ALL">All categories</option>' + cats.map(c => '<option value="'+esc(c)+'"'+(riskState.cat===c?' selected':'')+'>'+esc(c)+'</option>').join('');
  sel.onchange = () => { riskState.cat = sel.value; renderRiskTable(); };
  host.appendChild(sel);
}
function renderRiskTable(){
  const thead = $('#risktable thead'), tbody = $('#risktable tbody');
  thead.innerHTML = '<tr>' + RISK_COLS.map(([k, lbl, n]) => {
    const arr = riskState.sortKey === k ? ' <span class="arr">'+(riskState.sortDir<0?'▼':'▲')+'</span>' : '';
    return '<th class="'+(n?'n':'')+'" data-k="'+k+'">'+esc(lbl)+arr+'</th>';
  }).join('') + '</tr>';
  thead.querySelectorAll('th').forEach(th => th.onclick = () => {
    const k = th.dataset.k;
    if (riskState.sortKey === k) riskState.sortDir *= -1;
    else { riskState.sortKey = k; riskState.sortDir = (k==='risk'||k==='source_category'||k==='tier'||k==='element') ? 1 : -1; }
    renderRiskTable();
  });

  let rows = DATA.risk_register.filter(r =>
    (riskState.tier === 'ALL' || r.tier === riskState.tier) &&
    (riskState.cat === 'ALL' || r.source_category === riskState.cat));
  const key = riskState.sortKey;
  const val = r => key === 'risk' ? r.headline.toLowerCase()
    : key === 'element' ? riskElement(r).toLowerCase()
    : key === 'tier' ? TIER_RANK[r.tier]
    : r[key];
  rows.sort((a, b) => { const va = val(a), vb = val(b); return (va < vb ? -1 : va > vb ? 1 : 0) * riskState.sortDir; });

  const cap = 12;
  const total = rows.length;
  if (!riskState.showAll) rows = rows.slice(0, cap);

  tbody.innerHTML = rows.map(r =>
    '<tr>' +
    '<td class="risk">'+esc(r.headline)+'<span class="rid">'+esc(r.id)+'</span></td>' +
    '<td>'+esc(r.source_category)+'</td>' +
    '<td class="num" style="font-size:12px;color:var(--muted)">'+esc(riskElement(r))+'</td>' +
    '<td class="n">'+r.likelihood+'</td>' +
    '<td class="n">'+r.impact+'</td>' +
    '<td class="n" style="color:var(--ink);font-weight:600">'+r.risk_score+'</td>' +
    '<td><span class="tierbadge"><span class="dot" style="background:'+TIER_COLOR[r.tier]+'"></span><span class="t">'+r.tier[0]+r.tier.slice(1).toLowerCase()+'</span></span></td>' +
    '<td class="n">'+fmtK(r.value_at_risk)+'</td>' +
    '<td class="n">'+r.exposure_days+'</td>' +
    '</tr>').join('');

  const sa = $('#riskshowall');
  if (total > cap) {
    sa.innerHTML = '<button>'+(riskState.showAll ? 'Show top 12' : 'Show all '+total+' risks')+'</button>';
    sa.querySelector('button').onclick = () => { riskState.showAll = !riskState.showAll; renderRiskTable(); };
  } else sa.innerHTML = '';
}

// ============================================================ SCENARIO LAB
let activeScenario = null;
const BLUE_STEPS = ['#86b6ef','#5598e7','#3987e5','#256abf','#1c5cab'];
function scenarioIds(){ return Object.keys(DATA.scenarios); }
function renderScenTabs(){
  const host = $('#scentabs'); host.innerHTML = '';
  scenarioIds().forEach(id => {
    const s = DATA.scenarios[id];
    const b = document.createElement('button');
    b.className = 'tab' + (id === activeScenario ? ' active' : '');
    b.textContent = s.scenario_name;
    b.onclick = () => { activeScenario = id; renderScenTabs(); renderScenChart(); renderScenImpact(); renderMitigation(); };
    host.appendChild(b);
  });
}
function renderScenLegend(){
  const s = DATA.scenarios[activeScenario];
  $('#scenlegend').innerHTML =
    '<span class="item"><span class="sw" style="background:var(--s1);width:14px;height:3px;border-radius:2px"></span>Baseline</span>' +
    '<span class="item"><span class="sw" style="background:var(--s8);width:14px;height:3px;border-radius:2px"></span>'+esc(s.scenario_name.split('—')[0].split('(')[0].trim())+'</span>';
}
function renderScenChart(){
  renderScenLegend();
  const s = DATA.scenarios[activeScenario];
  const svg = $('#scenchart');
  const W = 720, H = 264, mL = 44, mR = 118, mT = 16, mB = 34;
  const pw = W - mL - mR, ph = H - mT - mB;
  const weeks = s.baseline_weeks.map(w => w.week);
  const n = weeks.length;
  const xOf = i => mL + (n === 1 ? pw/2 : i/(n-1)*pw);
  const yOf = v => mT + ph - (v/100)*ph;   // v is a percentage 0..100
  const svBase = s.baseline_weeks.map(w => w.service_level*100);
  const svScen = s.scenario_weeks.map(w => w.service_level*100);

  let g = '';
  // outage band
  if (s.outage_start_week && s.outage_end_week){
    const i0 = weeks.indexOf(s.outage_start_week), i1 = weeks.indexOf(s.outage_end_week);
    if (i0 >= 0 && i1 >= 0){
      const x0 = Math.max(mL, xOf(i0) - pw/(n-1)/2), x1 = Math.min(mL+pw, xOf(i1) + pw/(n-1)/2);
      g += '<rect x="'+x0+'" y="'+mT+'" width="'+(x1-x0)+'" height="'+ph+'" style="fill:var(--surface-2)"/>';
      g += '<text x="'+((x0+x1)/2)+'" y="'+(mT+12)+'" text-anchor="middle" style="fill:var(--muted)" font-size="10">outage window</text>';
    }
  }
  // y grid + ticks
  for (let v = 0; v <= 100; v += 20){
    const y = yOf(v);
    g += '<line x1="'+mL+'" y1="'+y+'" x2="'+(mL+pw)+'" y2="'+y+'" style="stroke:var(--grid)" stroke-width="1"/>';
    g += '<text x="'+(mL-8)+'" y="'+(y+3.5)+'" text-anchor="end" class="num" style="fill:var(--muted)" font-size="10">'+v+'%</text>';
  }
  // x ticks
  weeks.forEach((w, i) => {
    if (n > 8 && w % 2 === 0) return;
    g += '<text x="'+xOf(i)+'" y="'+(mT+ph+16)+'" text-anchor="middle" class="num" style="fill:var(--muted)" font-size="10">'+w+'</text>';
  });
  g += '<text x="'+(mL+pw/2)+'" y="'+(H-2)+'" text-anchor="middle" style="fill:var(--muted)" font-size="10">week</text>';

  const path = arr => arr.map((v, i) => (i?'L':'M')+xOf(i).toFixed(1)+','+yOf(v).toFixed(1)).join(' ');
  // shade only the baseline-vs-scenario gap — the service actually lost
  const back = svScen.map((v, i) => 'L'+xOf(n-1-i).toFixed(1)+','+yOf(svScen[n-1-i]).toFixed(1)).join(' ');
  g += '<path d="'+path(svBase)+' '+back+' Z" style="fill:var(--s8);opacity:.14"/>';
  g += '<path d="'+path(svBase)+'" fill="none" style="stroke:var(--s1)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';
  g += '<path d="'+path(svScen)+'" fill="none" style="stroke:var(--s8)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>';
  // direct end labels — nudge apart when the two series end near the same y
  const yb = yOf(svBase[n-1]), ys = yOf(svScen[n-1]);
  let lyb = yb + 3, lys = ys + 3;
  if (Math.abs(yb - ys) < 13){ lyb = Math.min(yb, ys) - 4; lys = Math.max(yb, ys) + 12; }
  g += '<text x="'+(xOf(n-1)+8)+'" y="'+lyb+'" style="fill:var(--s1)" font-size="11" font-weight="600">Baseline</text>';
  g += '<text x="'+(xOf(n-1)+8)+'" y="'+lys+'" style="fill:var(--s8)" font-size="11" font-weight="600">Scenario</text>';

  // crosshair + markers layer (hidden until hover)
  g += '<line id="xhair" x1="0" y1="'+mT+'" x2="0" y2="'+(mT+ph)+'" style="stroke:var(--axis);opacity:0" stroke-width="1" stroke-dasharray="3 3"/>';
  g += '<circle id="mB" r="4.5" style="fill:var(--s1);stroke:var(--surface);stroke-width:2;opacity:0"/>';
  g += '<circle id="mS" r="4.5" style="fill:var(--s8);stroke:var(--surface);stroke-width:2;opacity:0"/>';
  g += '<rect id="hitzone" x="'+mL+'" y="'+mT+'" width="'+pw+'" height="'+ph+'" fill="transparent"/>';
  svg.innerHTML = g;

  const xhair = $('#xhair', svg), mkB = $('#mB', svg), mkS = $('#mS', svg), hit = $('#hitzone', svg);
  const pt = svg.createSVGPoint();
  hit.addEventListener('mousemove', e => {
    pt.x = e.clientX; pt.y = e.clientY;
    const loc = pt.matrixTransform(svg.getScreenCTM().inverse());
    let i = Math.round((loc.x - mL) / (pw/(n-1)));
    i = Math.max(0, Math.min(n-1, i));
    const x = xOf(i);
    xhair.setAttribute('x1', x); xhair.setAttribute('x2', x); xhair.style.opacity = '1';
    mkB.setAttribute('cx', x); mkB.setAttribute('cy', yOf(svBase[i])); mkB.style.opacity = '1';
    mkS.setAttribute('cx', x); mkS.setAttribute('cy', yOf(svScen[i])); mkS.style.opacity = '1';
    const html = '<div class="tt">Week '+weeks[i]+'</div>' +
      '<div class="kv"><span><span class="sw" style="background:var(--s1)"></span>Baseline</span><b>'+svBase[i].toFixed(1)+'%</b></div>' +
      '<div class="kv"><span><span class="sw" style="background:var(--s8)"></span>Scenario</span><b>'+svScen[i].toFixed(1)+'%</b></div>' +
      '<div class="kv"><span>Lost revenue</span><b>'+fmtMoney(s.scenario_weeks[i].lost_revenue)+'</b></div>';
    showTip(html, e.clientX, e.clientY);
  });
  hit.addEventListener('mouseleave', () => {
    xhair.style.opacity = mkB.style.opacity = mkS.style.opacity = '0'; hideTip();
  });
}
function renderScenImpact(){
  const s = DATA.scenarios[activeScenario];
  const host = $('#scenimpact');
  const ttr = s.ttr < 0 ? 'n/a' : s.ttr + 'w';
  const stats = [
    ['Lost Revenue', fmtMoney(s.total_lost_revenue)],
    ['Service Floor', (s.worst_service_level*100).toFixed(1)+'<small>%</small>'],
    ['Time to Survive', s.tts+'<small>w</small>'],
    ['Time to Recover', ttr==='n/a'?ttr:s.ttr+'<small>w</small>'],
  ];
  let html = '<div class="row">' + stats.map(([k, v]) =>
    '<div class="stat"><div class="k">'+k+'</div><div class="v">'+v+'</div></div>').join('') + '</div>';

  // weekly lost-revenue horizontal bars
  const weeks = s.scenario_weeks.filter(w => w.lost_revenue > 0);
  html += '<p class="subttl">Weekly Lost Revenue</p>';
  if (!weeks.length) html += '<p style="font-size:12px;color:var(--muted);margin:0">No revenue loss — buffers fully absorbed the shock.</p>';
  else {
    const max = Math.max(...weeks.map(w => w.lost_revenue));
    html += '<div class="barlist">' + weeks.map(w => {
      const pct = w.lost_revenue/max;
      const step = BLUE_STEPS[Math.min(BLUE_STEPS.length-1, Math.floor(pct*(BLUE_STEPS.length-0.001)))];
      return '<div class="brow"><span class="wk">W'+w.week+'</span>' +
        '<span class="track"><span class="fill" data-wk="'+w.week+'" data-rev="'+w.lost_revenue+'" style="width:'+Math.max(3, pct*100).toFixed(1)+'%;background:'+step+'"></span></span>' +
        '<span class="amt num">'+fmtMoney(w.lost_revenue)+'</span></div>';
    }).join('') + '</div>';
  }
  host.innerHTML = html;
  host.querySelectorAll('.fill').forEach(f => {
    f.addEventListener('mousemove', e => showTip(
      '<div class="tt">Week '+f.dataset.wk+'</div><div class="kv"><span>Lost revenue</span><b>'+fmtMoney(+f.dataset.rev)+'</b></div>',
      e.clientX, e.clientY));
    f.addEventListener('mouseleave', hideTip);
  });
}

// ============================================================ MITIGATION
function renderMitigation(){
  const s = DATA.scenarios[activeScenario];
  $('#mittitle').textContent = 'Ranked Response Playbook · ' + s.scenario_name;
  const list = DATA.mitigations[activeScenario] || [];
  const thead = $('#mittable thead'), tbody = $('#mittable tbody');
  thead.innerHTML = '<tr><th>Action</th><th>Mechanism</th><th class="n">Cost ($k)</th><th class="n">Avoided ($k)</th><th>Net Benefit ($k)</th></tr>';
  const max = Math.max(1, ...list.map(m => m.net_benefit));
  tbody.innerHTML = list.map((m, idx) => {
    // DESIGN: the single top-ranked action carries the RECOMMENDED chip.
    const rec = (idx === 0 && m.recommended) ? '<span class="rec"><span class="dot"></span>RECOMMENDED</span>' : '';
    const pct = m.net_benefit > 0 ? Math.max(2, m.net_benefit/max*100).toFixed(1) : 0;
    return '<tr>' +
      '<td style="color:var(--ink)"><b style="font-weight:600">'+esc(m.action_name)+'</b>'+rec+'</td>' +
      '<td class="mech">'+esc(m.mechanism)+'</td>' +
      '<td class="n">'+fmtK(m.cost)+'</td>' +
      '<td class="n">'+fmtK(m.avoided_loss)+'</td>' +
      '<td class="mbar"><div class="netbar"><span class="track"><span class="fill" style="width:'+pct+'%"></span></span><span class="amt num">'+fmtK(m.net_benefit)+'</span></div></td>' +
      '</tr>';
  }).join('');
}

// ============================================================ THEME
function applyStoredTheme(){
  const t = localStorage.getItem('rr-theme');
  if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
}
function toggleTheme(){
  const cur = document.documentElement.getAttribute('data-theme');
  let next;
  if (cur) next = cur === 'dark' ? 'light' : 'dark';
  else next = matchMedia('(prefers-color-scheme: dark)').matches ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('rr-theme', next);
}

// ============================================================ BOOT
applyStoredTheme();
$('#themebtn').addEventListener('click', toggleTheme);
renderHeader();
renderKpis();
renderNetLegend();
renderNetwork();
renderRiskFilters();
renderRiskTable();
activeScenario = scenarioIds()[0];
renderScenTabs();
renderScenChart();
renderScenImpact();
renderMitigation();
</script>
</body>
</html>
"""


def render_dashboard(context: dict, out_path: Path | str) -> None:
    """Render the self-contained control-tower HTML, embedding `context` once."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Compact JSON; escape </ so an embedded string can't close the <script>.
    data_json = json.dumps(context, ensure_ascii=False).replace("</", "<\\/")
    html_doc = _TEMPLATE.replace("__DATA_JSON__", data_json)
    out_path.write_text(html_doc, encoding="utf-8")
