"""
cli.py — the `python -m resilience_radar` command-line interface.

Four subcommands, each a thin wrapper over the engine modules:

    scan                      events.json -> risk register (console + JSON)
    simulate --scenario ID    run one preset what-if scenario
    demo                      scan + all 3 scenarios + mitigations + dashboard
    dashboard                 rebuild output/dashboard.html from last outputs

Console tables are hand-rolled (aligned, ANSI tier-colored) rather than
pulling in a table-formatting dependency, in keeping with the
stdlib-only constraint.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import dashboard, graph, kpi, mitigate, radar, simulate
from .models import Network, Risk, SimResult, jsonable

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # src/resilience_radar/.. -> repo root


def _resolve(path_str: str, fallback_under_root: str) -> Path:
    """Prefer a path relative to cwd; fall back to the repo root so the
    CLI works whether invoked from the repo root or elsewhere."""
    p = Path(path_str)
    if p.exists():
        return p
    fallback = _PACKAGE_ROOT / fallback_under_root
    return fallback if fallback.exists() else p


def _default_network_path() -> str:
    return str(_resolve("data/network.json", "data/network.json"))


def _default_events_path() -> str:
    return str(_resolve("data/events.json", "data/events.json"))


def _default_output_dir() -> str:
    p = Path("output")
    if p.exists():
        return str(p)
    return str(_PACKAGE_ROOT / "output")


# --------------------------------------------------------------------------
# ANSI console table helpers
# --------------------------------------------------------------------------

_RESET = "\033[0m"
_TIER_COLORS = {
    "CRITICAL": "\033[1;31m",  # bold red
    "HIGH": "\033[0;33m",  # amber
    "MEDIUM": "\033[0;34m",  # blue
    "LOW": "\033[0;32m",  # green
}


def _use_color() -> bool:
    return sys.stdout.isatty()


def _colorize(text: str, code: Optional[str]) -> str:
    if not code or not _use_color():
        return text
    return f"{code}{text}{_RESET}"


def _print_table(headers: list[str], rows: list[list[str]], color_col: Optional[int] = None) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: list[str], colorize: bool) -> str:
        parts = []
        for i, cell in enumerate(cells):
            padded = cell.ljust(widths[i])
            if colorize and color_col is not None and i == color_col:
                padded = _colorize(padded, _TIER_COLORS.get(cell.strip()))
            parts.append(padded)
        return "  ".join(parts)

    print(fmt(headers, colorize=False))
    print(fmt(["-" * w for w in widths], colorize=False))
    for row in rows:
        print(fmt(row, colorize=True))


def _print_risk_table(risks: list[Risk], limit: int = 15) -> None:
    headers = ["ID", "TIER", "SCORE", "L", "I", "CATEGORY", "ELEMENT", "VAR($k)", "EXP(d)", "HEADLINE"]
    rows = []
    for r in risks[:limit]:
        element = ", ".join(r.affected_node_ids + r.affected_lane_ids) or "-"
        rows.append(
            [
                r.id,
                r.tier.value,
                str(r.risk_score),
                str(r.likelihood),
                str(r.impact),
                r.source_category.value,
                element[:28],
                f"{r.value_at_risk / 1000:,.1f}",
                f"{r.exposure_days:.0f}",
                r.headline[:44],
            ]
        )
    _print_table(headers, rows, color_col=1)
    if len(risks) > limit:
        print(f"... and {len(risks) - limit} more (see risk_register.json)")


def _print_scenario_summary(result: SimResult) -> None:
    print(f"\nScenario: {result.scenario_name} [{result.scenario_id}]")
    print(
        f"  outage weeks {result.outage_start_week}-{result.outage_end_week}  "
        f"baseline service {result.baseline_service_level * 100:.1f}%  "
        f"worst service {result.worst_service_level * 100:.1f}%"
    )
    ttr_str = f"{result.ttr}w" if result.ttr is not None else "does not recover in horizon"
    print(f"  TTS (time to survive): {result.tts}w   TTR (time to recover): {ttr_str}")
    print(f"  total lost revenue: ${result.total_lost_revenue:,.0f}")
    headers = ["WEEK", "SERVICE%", "LOST_REV($)", "INVENTORY($)"]
    rows = [
        [str(w.week), f"{w.service_level * 100:.1f}", f"{w.lost_revenue:,.0f}", f"{w.inventory_position:,.0f}"]
        for w in result.scenario_weeks
    ]
    _print_table(headers, rows)


def _print_mitigation_table(results: list[mitigate.MitigationResult]) -> None:
    headers = ["ACTION", "COST($k)", "AVOIDED($k)", "NET($k)", "REC"]
    rows = [
        [
            r.action_name,
            f"{r.cost / 1000:,.1f}",
            f"{r.avoided_loss / 1000:,.1f}",
            f"{r.net_benefit / 1000:,.1f}",
            "RECOMMENDED" if r.recommended else "",
        ]
        for r in results
    ]
    _print_table(headers, rows)


def _print_kpi_summary(kpis: dict[str, kpi.Kpi]) -> None:
    headers = ["KPI", "VALUE", "UNIT", "CONTEXT"]
    rows = [[k.label, f"{k.value:,.2f}", k.unit, k.context] for k in kpis.values()]
    _print_table(headers, rows)


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------


def cmd_scan(args: argparse.Namespace) -> None:
    network = graph.load_network(args.network)
    out_path = Path(args.output) / "risk_register.json"
    risks = radar.scan(args.events, network, out_path)
    print(f"Scanned {len(risks)} events -> {len(risks)} risks -> {out_path}\n")
    _print_risk_table(risks)


def cmd_simulate(args: argparse.Namespace) -> None:
    network = graph.load_network(args.network)
    scenario = simulate.get_preset(args.scenario)
    result = simulate.run_scenario(network, scenario)
    _print_scenario_summary(result)

    mitigations = mitigate.rank_mitigations(network, scenario, result)
    print("\nTop mitigations:")
    _print_mitigation_table(mitigations)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"simulation_{scenario.id}.json"
    out_path.write_text(json.dumps(jsonable(result), indent=2))
    print(f"\nWritten -> {out_path}")


def _run_full_pipeline(network: Network, events_path: str, output_dir: str, verbose: bool = True) -> dict:
    out_dir = Path(output_dir)
    risks = radar.scan(events_path, network, out_dir / "risk_register.json")
    if verbose:
        print(f"Scanned -> {len(risks)} risks\n")
        _print_risk_table(risks)

    sim_results = simulate.run_all_presets(network)
    mitigations: dict[str, list[mitigate.MitigationResult]] = {}
    for scenario_id, result in sim_results.items():
        if verbose:
            _print_scenario_summary(result)
        mitigations[scenario_id] = mitigate.rank_mitigations(
            network, simulate.PRESET_SCENARIOS[scenario_id], result
        )
        if verbose:
            print("  Top mitigations:")
            _print_mitigation_table(mitigations[scenario_id])

    kpis = kpi.compute_kpis(network, risks, sim_results)
    if verbose:
        print("\nKPI summary:")
        _print_kpi_summary(kpis)

    generated_at = datetime.now(timezone.utc).isoformat()
    context = dashboard.build_context(network, risks, kpis, sim_results, mitigations, generated_at)
    dashboard_path = out_dir / "dashboard.html"
    dashboard.render_dashboard(context, dashboard_path)
    if verbose:
        print(f"\nDashboard written -> {dashboard_path}")
    return context


def cmd_demo(args: argparse.Namespace) -> None:
    network = graph.load_network(args.network)
    _run_full_pipeline(network, args.events, args.output)


def cmd_dashboard(args: argparse.Namespace) -> None:
    network = graph.load_network(args.network)
    register_path = Path(args.output) / "risk_register.json"
    if register_path.exists():
        risks = radar.load_risk_register(register_path)
        print(f"Loaded {len(risks)} risks from {register_path}")
    else:
        print("No prior risk_register.json found, running scan first...")
        risks = radar.scan(args.events, network, register_path)

    sim_results = simulate.run_all_presets(network)
    mitigations = {
        sid: mitigate.rank_mitigations(network, simulate.PRESET_SCENARIOS[sid], result)
        for sid, result in sim_results.items()
    }
    kpis = kpi.compute_kpis(network, risks, sim_results)
    generated_at = datetime.now(timezone.utc).isoformat()
    context = dashboard.build_context(network, risks, kpis, sim_results, mitigations, generated_at)
    out_path = Path(args.output) / "dashboard.html"
    dashboard.render_dashboard(context, out_path)
    print(f"Dashboard rebuilt -> {out_path}")


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resilience_radar", description="Supply chain resilience control tower")
    parser.add_argument("--network", default=None, help="path to network.json")
    parser.add_argument("--events", default=None, help="path to events.json")
    parser.add_argument("--output", default=None, help="output directory")

    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="events -> risk register")
    p_scan.set_defaults(func=cmd_scan)

    p_sim = sub.add_parser("simulate", help="run one preset scenario")
    p_sim.add_argument("--scenario", required=True, choices=sorted(simulate.PRESET_SCENARIOS))
    p_sim.set_defaults(func=cmd_simulate)

    p_demo = sub.add_parser("demo", help="scan + all scenarios + mitigations + dashboard")
    p_demo.set_defaults(func=cmd_demo)

    p_dash = sub.add_parser("dashboard", help="rebuild dashboard.html from last outputs")
    p_dash.set_defaults(func=cmd_dashboard)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    args.network = args.network or _default_network_path()
    args.events = args.events or _default_events_path()
    args.output = args.output or _default_output_dir()

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
