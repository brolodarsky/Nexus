---
type: patch
---
### Added
- Split `src/nexus/agent/graph.py` into a strictly acyclic four-module package layout:
  - `src/nexus/agent/sanitization.py`: pure leaf message extractors (`extract_message_text`, `extract_message_thinking`) and cross-provider history/signature sanitizers (`_sanitize_messages`, `_sanitize_messages_for_provider`).
  - `src/nexus/agent/runtime.py`: shared execution runtime (`CORE_TOOLS`, `nexus_tracer`, thread-scoped subagent serial/provider tracking, Stop & Revert cancellation registry, `_build_system_message`, `_log_token_usage`, `_invoke_llm_with_resilience`, `_invoke_tool_node_resilient`).
  - `src/nexus/agent/subagent.py`: isolated dynamic subagent worker (`spawn_subagent`) and budget synthesis helpers (`_build_budget_refusal_tool_messages`, `_build_tool_free_synthesis_messages`).

### Changed
- Slimmed `src/nexus/agent/graph.py` to LangGraph `StateGraph` topology, `TOOLS` binding, `call_model`, `traced_tool_node`, and `route_after_agent`.
- Updated all production callers (`nexus/agent/__init__.py`, `nexus/agent/api.py`, `nexus/api/routers/agents.py`, `nexus/core/chat_branching.py`, `nexus/core/chat_titles.py`, `nexus/shared_tools/telegram_bridge.py`, `nexus/core/config.py`) and test imports/monkeypatches directly with no re-export shims.

### Removed
- Pruned vestigial `subagent_tracer` global, dead module-level `_primary_tier` / `llm` / `llm_with_tools` client instantiations in `graph.py`, redundant `global _active_turn_provider` assignment in `call_model`, and unused imports (`json`, `Path`, `ChatOpenAI`, `AI_MODEL_LOW`, `AI_MODEL_MEDIUM`, `VAULT_PATH`, `RESULT_TRUNCATE_LEN`, `_truncate`).
