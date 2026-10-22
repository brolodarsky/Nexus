---
type: minor
---
### Added
- **Native Gemini 3+ (`ChatGoogleGenerativeAI`) & Tiered Model Routing (`get_chat_model`):** Added `langchain-google-genai` and `get_chat_model(tier)` in `src/nexus/core/constants.py` with Gemini/tiered configuration in `src/nexus/core/config.py` (`gemini_api_key`, `google_api_key`, `ai_provider`, `nexus_primary_tier`, `nexus_subagent_tier`). Uses Google's native `ChatGoogleGenerativeAI` client so Gemini 3+ `thought_signature` tokens (`__gemini_function_call_thought_signatures__` and structured content block signatures) are automatically preserved across multi-step tool loops and cross-model conversation history.
- **Structured Content Block Text Extractor (`extract_message_text`):** Added `extract_message_text(msg)` in `src/nexus/agent/graph.py` (and wired into `api.py` and `summarizer.py`) so Gemini's structured signature content blocks remain intact in `SqliteSaver` checkpointer state while clean Markdown strings are returned to the GUI and CLI.
- **Live Token & Prompt Cache Telemetry (`_log_token_usage`):** Added automatic logging of input tokens, cached prompt token hits (`cache_read`), and output tokens to the console and SSE trace bus in `src/nexus/agent/graph.py`.

### Changed
- **Subagent Cost Tiering & Parallel Swarming (`spawn_subagent`):** Updated `spawn_subagent(task_prompt: str, model_tier: ModelTier = "low")` to default to the fast, low-cost model tier (`"low"`) while allowing `"medium"` or `"strong"` overrides, and updated `Vault/Master Instructions.md` and tool docstrings to instruct parallel multi-tool/subagent fan-out in a single turn.
- **Prompt Caching Prefix Isolation:** Reordered `Vault/Master Instructions.md` so static constitutional instructions, `{shared_tools}`, and `{vault_structure}` form a contiguous static prefix, and updated `inject_root_instructions(cache_stable=True)` in `src/nexus/core/engine_constitution.py` to align `{current_time}` to the hour boundary (`YYYY-MM-DD HH:00`) at the tail so second-by-second timestamps never invalidate provider KV prompt caches across multi-step tool loops.

### Fixed
- **Gemini Tool Schema Compatibility (`run_shared_tool_cli`):** Renamed parameter `args` $\rightarrow$ `cli_args` on `run_shared_tool_cli` in `src/nexus/shared_tools/shared.py` to prevent Pydantic v2 from emitting an untyped `v__args` property that caused Gemini `GenerateContentRequest` schema validation errors.
