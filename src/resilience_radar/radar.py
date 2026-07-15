"""
radar.py — the event feed -> risk register pipeline.

This is the orchestration layer that ties `typology.py` (classify) and
`scoring.py` (score) together into the thing a resilience desk actually
looks at every morning: a ranked risk register.

    events.json --load--> [Event] --classify+score--> [Risk] --sort--> register

Classification is offline/rule-based by default. Passing a `Classifier`
(see `llm.py`) swaps in an LLM-backed source/consequence call while
node/lane alias matching (a structural fact about the text, not a
judgment call) always runs through `typology.py`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from . import scoring, typology
from .models import ConsequenceClass, Event, FrequencyClass, Network, Risk, RiskTier, SourceCategory, jsonable
from .typology import Classification


def load_events(path: Path | str) -> list[Event]:
    """Load `events.json` into a list of `Event`."""
    raw = json.loads(Path(path).read_text())
    events: list[Event] = []
    for item in raw:
        item = dict(item)
        item["date"] = date.fromisoformat(item["date"])
        events.append(Event(**item))
    return events


ClassifierFn = Callable[[Event, Network], Classification]


def build_risk_register(
    events: list[Event],
    network: Network,
    classifier: Optional[ClassifierFn] = None,
) -> list[Risk]:
    """
    Classify + score every event into a risk register, sorted by
    `risk_score` descending (ties broken by event date, most recent first).
    """
    classify = classifier or typology.classify_event

    # Precompute criticality once — it's the same for every event in a run.
    from . import graph

    node_crit = graph.node_criticality(network)
    lane_crit = graph.lane_criticality(network)

    risks: list[Risk] = []
    for event in events:
        classification = classify(event, network)
        risk = scoring.score_event(event, classification, network, node_crit, lane_crit)
        risks.append(risk)

    risks.sort(key=lambda r: (r.risk_score, r.event_date), reverse=True)
    return risks


def write_risk_register(risks: list[Risk], out_path: Path | str) -> None:
    """Write the risk register to JSON, ready for the dashboard or CLI to consume."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([jsonable(r) for r in risks], indent=2))


def load_risk_register(path: Path | str) -> list[Risk]:
    """Read back a risk register previously written by `write_risk_register`."""
    raw = json.loads(Path(path).read_text())
    risks: list[Risk] = []
    for item in raw:
        item = dict(item)
        item["source_category"] = SourceCategory(item["source_category"])
        item["consequence_class"] = ConsequenceClass(item["consequence_class"])
        item["frequency_class"] = FrequencyClass(item["frequency_class"])
        item["tier"] = RiskTier(item["tier"])
        item["event_date"] = date.fromisoformat(item["event_date"])
        risks.append(Risk(**item))
    return risks


def scan(
    events_path: Path | str,
    network: Network,
    out_path: Path | str,
    classifier: Optional[ClassifierFn] = None,
) -> list[Risk]:
    """Full scan pipeline: load events, build the register, write it out."""
    events = load_events(events_path)
    risks = build_risk_register(events, network, classifier)
    write_risk_register(risks, out_path)
    return risks
