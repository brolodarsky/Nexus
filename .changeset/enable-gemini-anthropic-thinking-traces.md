---
type: minor
---
### Added
- Enabled visible thinking/reasoning summaries for Google Gemini (`include_thoughts=True`) and Anthropic Claude 4.6+/5.x adaptive models (`thinking={"type": "adaptive", "display": "summarized"}`, `max_tokens` floor `16384` without conflicting `temperature`) in `src/nexus/core/constants.py` and `src/nexus/core/config.py` (`ai_include_thoughts`, `anthropic_thinking_max_tokens`), while opting background chat titling (`src/nexus/core/chat_titles.py`) out via `include_thoughts=False`.
- Added `AgentTracer.llm_thinking()` in `src/nexus/core/trace.py`, read-only `extract_message_thinking()` and reactive `thinking`-parameter self-healing in `src/nexus/agent/graph.py`, and per-step `llm_thinking` emission plus `reasoning_tokens` telemetry (logged without double-counting output token costs) across `call_model()`, `spawn_subagent()`, and `src/nexus/core/run_logger.py`.
- Added `llm_thinking` rendering in `gui/src/lib/api/stream.ts`, `gui/src/components/AgentTraceVisualizer.tsx` (`🧠` step icon + expandable `Model Reasoning` panel), and `gui/src/app/audit/page.tsx` (`Subagent Reasoning` section in the Subagent Swarm tab).
- Added unit tests in `tests/test_model_config_and_resilience.py` and `tests/test_agent_tracking_and_graph.py`.
