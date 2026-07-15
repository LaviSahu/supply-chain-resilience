# LLM Integration

## The adapter

`llm.py` defines a minimal `Classifier` protocol — one method,
`classify_event(text) -> dict` returning `{source_category,
consequence_class, confidence, rationale}` — and three implementations:

- **`RuleBasedFallback`** (default) — a thin wrapper around
  `typology.classify_event`'s keyword rules. Fully offline, fully
  deterministic, zero API keys, zero network calls.
- **`AnthropicProvider`** — calls the Anthropic Messages API
  (`ANTHROPIC_API_KEY` from the environment), asks for the same JSON shape
  back.
- **`OpenAIProvider`** — calls OpenAI's Chat Completions API
  (`OPENAI_API_KEY`), same contract.

Both network providers fall back to `RuleBasedFallback` if no key is
present — an `--llm` flag with no key configured degrades gracefully
instead of erroring. Neither provider's network-call code path is
exercised by the test suite or the `demo` command (both are marked
`# pragma: no cover - network` in the source) — this project's test suite
and offline demo genuinely run with zero external calls, not just "zero by
default in the common case."

## Why classification-only, not code generation

`radar.py`'s `build_risk_register()` accepts an optional `classifier`
callable. When present, it can replace the source/consequence *judgment*
call — but node/lane matching always runs through `typology.py`'s
deterministic alias matcher regardless of which classifier is active. That
split is deliberate: which node or lane a headline mentions is a
structural fact about the text (a name either appears or it doesn't); the
severity class an event belongs to is a judgment call, and that's the only
place an LLM is ever invited into the pipeline.

Everything downstream of classification — likelihood/impact scoring,
criticality math, the entire 12-week propagation engine, TTR/TTS,
mitigation ranking — is deterministic Python arithmetic. No LLM ever
touches a number in the simulation.

This is a specific, defensible design position, contrasted with a more
ambitious pattern in the same space: Microsoft's **OptiGuide**
(Li et al., "Large Language Models for Supply Chain Optimization", 2023)
has an LLM read a natural-language question, *generate code* that edits an
optimization model, run that code against a solver, and translate the
solver's output back into natural language. That's a genuinely powerful
pattern for ad-hoc, conversational what-if exploration over an existing
optimization model — but it also means the answer to "what happens if
supplier X fails" depends on whichever code the LLM happened to generate
that call, which is harder to test, harder to reproduce byte-for-byte, and
requires a human (or a second LLM) in the loop to sanity-check the
generated code before trusting the output.

Resilience Radar makes the opposite trade for a different problem: the
simulation core (`simulate.py`) is a fixed, hand-written, unit-tested
deterministic model. The LLM, when enabled at all, only ever narrows down
*which pre-defined category a headline belongs to* — a bounded
classification task with a small, enumerable output space, not open-ended
code synthesis. The cost is flexibility (you can't ask it a free-form
optimization question); the benefit is that every number in the dashboard
is reproducible, testable with a fixed expected output, and safe to run
unattended in a CI pipeline or a nightly batch job with no risk of a
generated-code bug silently corrupting a KPI.

## Where you'd extend it

If you wanted OptiGuide-style conversational exploration on top of this
project, the natural seam is *above* `simulate.py`, not inside it — an LLM
agent that translates a free-form question into a `Scenario` object (using
the schema in [Scenario Guide](04-scenario-guide.md)) and calls
`simulate.run_scenario()` with it, rather than one that writes simulation
code directly. That keeps the deterministic core intact while adding a
natural-language front end.

Next: [Roadmap](06-roadmap.md).
