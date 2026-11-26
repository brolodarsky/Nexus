---
type: minor
---
### Added
- Added cache-preserving hard-cap synthesis (`_build_budget_refusal_tool_messages()`) in `src/nexus/agent/graph.py` that appends synthetic refusal `ToolMessage` stubs and invokes bound `sub_llm` first (preserving ~85–90% KV prompt-cache hits instead of dropping to 0%), keeping `_build_tool_free_synthesis_messages()` + `sub_base_llm` as a stubborn-model fallback.
- Added a one-shot soft-landing warning on the brand-new tail `ToolMessage` at `max_turns - 2` or 80% uncached token budget without mutating earlier prefix messages.
- Emitted structured `event_kind` telemetry (`subagent_soft_warning`, `subagent_budget_cap`, `subagent_budget_cap_fallback`) plus `cumulative_uncached_input_tokens` and `peak_context_tokens` metadata in `spawn_subagent()`.
- Created `scripts/audit_agent_health.py` (with unit tests in `tests/test_audit_agent_health.py`) for deterministic auditing of subagent breaker rates, cache integrity, truncation/rework signals, and percentile distributions (`--days`, `--since`, `--compare-since`, `--json`).

### Changed
- Raised `subagent_max_turns` from `12` to `25` and replaced `subagent_max_input_tokens = 400_000` with `subagent_max_uncached_input_tokens = 450_000` in `src/nexus/core/config.py` (`EngineSettings`, overridable via `.env`), gating subagent token budgets on uncached prompt tokens (`input_tokens - cached_tokens`) rather than penalizing KV-cached turns and `context_files` pre-hydration.
- Updated `tests/test_agent_tracking_and_graph.py` to cover uncached token budgeting, soft-landing prefix stability, cache-preserving synthesis, stubborn-model fallback, and `run_logger.log_run()` compatibility.
