"""
llm.py — optional LLM-backed classification, never required.

`typology.classify_event` is fully deterministic and is the default for
everything in this project, including the test suite and `demo`. This
module exists to show how a real deployment could optionally swap in an
LLM for the *judgment* half of classification (source category,
consequence severity) while node/lane matching stays the deterministic
alias matcher in typology.py — that part is a structural fact about the
text, not a judgment call.

Providers read credentials from the environment and are never invoked
unless `--llm` is passed on the CLI *and* a key is present; otherwise
`RuleBasedFallback` (a thin wrapper around `typology.classify_event`)
is used. No provider call happens during the test suite or offline demo.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Protocol

from .models import Event


class Classifier(Protocol):
    def classify_event(self, text: str) -> dict:
        ...


class RuleBasedFallback:
    """Default, offline classifier — delegates to typology.py's keyword rules."""

    def classify_event(self, text: str) -> dict:
        from . import typology
        from .models import Network

        # A minimal stand-in Event/Network pair just to reuse the keyword
        # rules on raw text without requiring a full network context.
        source, _ = typology.classify_source(_TextEvent(text))
        consequence, _ = typology.classify_consequence(_TextEvent(text))
        return {
            "source_category": source.value,
            "consequence_class": consequence.value,
            "confidence": 0.5,
            "rationale": "offline rule-based fallback",
        }


class _TextEvent:
    """Adapter so typology's text-only helpers can run without a full Event."""

    def __init__(self, text: str) -> None:
        self.headline = text
        self.body = ""


class AnthropicProvider:
    """Classifies via the Anthropic Messages API. Requires ANTHROPIC_API_KEY."""

    def __init__(self, model: str = "claude-3-5-haiku-latest") -> None:
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.model = model

    def classify_event(self, text: str) -> dict:
        if not self.api_key:
            return RuleBasedFallback().classify_event(text)
        prompt = (
            "Classify this supply-chain disruption event. Respond ONLY with JSON: "
            '{"source_category": "...", "consequence_class": "...", "confidence": 0.0, "rationale": "..."}\n\n'
            f"Event: {text}"
        )
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": 256,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # pragma: no cover - network
            payload = json.loads(resp.read())
        return json.loads(payload["content"][0]["text"])


class OpenAIProvider:
    """Classifies via the OpenAI Chat Completions API. Requires OPENAI_API_KEY."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.model = model

    def classify_event(self, text: str) -> dict:
        if not self.api_key:
            return RuleBasedFallback().classify_event(text)
        prompt = (
            "Classify this supply-chain disruption event. Respond ONLY with JSON: "
            '{"source_category": "...", "consequence_class": "...", "confidence": 0.0, "rationale": "..."}\n\n'
            f"Event: {text}"
        )
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            }
        ).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # pragma: no cover - network
            payload = json.loads(resp.read())
        return json.loads(payload["choices"][0]["message"]["content"])


def get_classifier(provider: str = "none") -> Classifier:
    """provider: 'anthropic' | 'openai' | 'none' (default, offline)."""
    if provider == "anthropic":
        return AnthropicProvider()
    if provider == "openai":
        return OpenAIProvider()
    return RuleBasedFallback()
