---
type: patch
---
### Added
- Added `subagent_max_turns` (default `12`) and `subagent_max_input_tokens` (default `400_000`) circuit-breaker settings to `EngineSettings` in `src/nexus/core/config.py`.
- Enforced turn and cumulative input-token budget caps inside `spawn_subagent()` (`src/nexus/agent/graph.py`) with `_build_tool_free_synthesis_messages()` to force a single unbound (`sub_base_llm`) synthesis response instead of timing out at 900s.
- Added unit tests `test_subagent_turn_cap_triggers_tool_free_synthesis` and `test_subagent_input_token_budget_triggers_tool_free_synthesis` in `tests/test_agent_tracking_and_graph.py`.

### Changed
- Updated `src/nexus/agent/graph.py` module docstring prompt-cache telemetry claim from `90–97%` to measured rates (`83.5%` across `748` runs; `90–95%` on static prefixes).
