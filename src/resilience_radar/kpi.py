"""
kpi.py — the resilience KPI catalog.

Every number here is *computed* from real engine outputs (the network,
the risk register, and a set of simulation results) — nothing is
hardcoded. This is the layer the CLI's `demo` command and the dashboard
both read from, so the console table and the HTML tiles are guaranteed
to agree.

Catalog:
- **RSI** (Risk Severity Index): mean `risk_score` across the open risk
  register — one number for "how hot is the register right now".
- **risk density**: risks per network node — a crude but useful signal
  of whether attention is concentrated or spread thin.
- **TTR / TTS**: pulled straight from simulation results, reported both
  per-scenario and as a "worst case across presets" headline number.
- **service level**: baseline (should read ~100%, confirming the network
  is modeled in equilibrium) and the worst floor hit across scenarios.
- **revenue at risk**: sum of value-at-risk across the open register.
- **single-source count / HHI**: structural concentration numbers from
  `graph.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import graph
from .models import Network, Risk, SimResult


@dataclass
class Kpi:
    key: str
    label: str
    value: float
    unit: str
    context: str = ""


def risk_severity_index(risks: list[Risk]) -> float:
    """Mean risk_score across the register; 0 if the register is empty."""
    if not risks:
        return 0.0
    return round(sum(r.risk_score for r in risks) / len(risks), 2)


def risk_density(network: Network, risks: list[Risk]) -> float:
    """Risks per network node."""
    if not network.nodes:
        return 0.0
    return round(len(risks) / len(network.nodes), 3)


def revenue_at_risk(risks: list[Risk]) -> float:
    """Sum of value_at_risk across the open register."""
    return round(sum(r.value_at_risk for r in risks), 2)


def single_source_count(network: Network) -> int:
    return len(graph.single_source_map(network))


def worst_ttr(sim_results: dict[str, SimResult]) -> Optional[int]:
    """The longest recovery time across all scenarios (None if any scenario never recovers)."""
    values = [r.ttr for r in sim_results.values()]
    if any(v is None for v in values):
        return None
    return max(values) if values else None


def min_tts(sim_results: dict[str, SimResult]) -> int:
    """The shortest survival window across all scenarios — the network's weakest link."""
    values = [r.tts for r in sim_results.values()]
    return min(values) if values else 0


def worst_scenario_name(sim_results: dict[str, SimResult]) -> str:
    """Name of the scenario with the lowest floor service level."""
    if not sim_results:
        return "n/a"
    worst = min(sim_results.values(), key=lambda r: r.worst_service_level)
    return worst.scenario_name


def baseline_service_level(sim_results: dict[str, SimResult]) -> float:
    if not sim_results:
        return 1.0
    return next(iter(sim_results.values())).baseline_service_level


def worst_service_level(sim_results: dict[str, SimResult]) -> float:
    if not sim_results:
        return 1.0
    return min(r.worst_service_level for r in sim_results.values())


def compute_kpis(network: Network, risks: list[Risk], sim_results: dict[str, SimResult]) -> dict[str, Kpi]:
    """Assemble the full KPI catalog used by the CLI and dashboard build_context."""
    hhi = graph.hhi_by_category(network)
    max_hhi_category = max(hhi, key=hhi.get) if hhi else "n/a"

    kpis: dict[str, Kpi] = {
        "service_level": Kpi(
            "service_level", "Service Level (baseline)", baseline_service_level(sim_results) * 100, "%",
            context=f"worst case: {worst_scenario_name(sim_results)}" if sim_results else "",
        ),
        "revenue_at_risk": Kpi(
            "revenue_at_risk", "Revenue at Risk", revenue_at_risk(risks), "$",
            context=f"gross exposure pre-buffer · {len(risks)} open risks",
        ),
        "rsi": Kpi(
            "rsi", "Risk Severity Index", risk_severity_index(risks), "score",
            context="mean risk_score across open register",
        ),
        "open_risks": Kpi(
            "open_risks", "Open Risks", float(len(risks)), "count",
            context=", ".join(
                f"{tier}:{sum(1 for r in risks if r.tier.value == tier)}"
                for tier in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
            ),
        ),
        "min_tts": Kpi(
            "min_tts", "Min TTS", float(min_tts(sim_results)), "weeks",
            context="weakest survival window across scenarios",
        ),
        "single_source_nodes": Kpi(
            "single_source_nodes", "Single-Source Nodes", float(single_source_count(network)), "count",
            context=f"most concentrated category: {max_hhi_category}",
        ),
        "risk_density": Kpi(
            "risk_density", "Risk Density", risk_density(network, risks), "risks/node",
        ),
        "worst_ttr": Kpi(
            "worst_ttr",
            "Worst TTR",
            float(worst_ttr(sim_results)) if worst_ttr(sim_results) is not None else -1.0,
            "weeks",
            context="longest recovery across scenarios (-1 = never recovers in horizon)",
        ),
    }
    return kpis
