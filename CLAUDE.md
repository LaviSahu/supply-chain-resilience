# supply-chain-resilience

**Resilience Radar, built and tested end to end:** disruption feed → risk register → time-phased what-if simulation → ranked mitigations → self-contained HTML dashboard.

- `DESIGN.md` is the contract — read before changing behaviour. `implementation-notes.md` logs deviations.
- Pure Python stdlib, zero dependencies, zero API keys. Build via `Makefile`; outputs in `output/`.
- Note: `../resilience-radar` is a closely related sibling — check which one is canonical before editing.

Generic coding-behaviour guidance lives once at `~/.claude/reference/coding-guidelines.md` — read it for heavy refactors, not routine edits.
