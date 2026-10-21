---
type: minor
---
### Added
- **Multi-Provider & Tiered Model Routing (`get_chat_model`):** Added `get_chat_model(tier)` in `src/nexus/core/constants.py` and Gemini/tiered configuration in `src/nexus/core/config.py` (`gemini_api_key`, `google_api_key`, `ai_provider`, `nexus_primary_tier`, `nexus_subagent_tier`). Automatically routes to Google's OpenAI-compatible Gemini Flash endpoint when a Gemini key is configured, or falls back to tiered OpenAI models (`AI_MODEL_LOW`, `AI_MODEL_MEDIUM`, `AI_MODEL_STRONG`).
- **Live Token & Prompt Cache Telemetry (`_log_token_usage`):** Added automatic logging of input tokens, cached prompt token hits (`cache_read`), and output tokens to the console and SSE trace bus in `src/nexus/agent/graph.py`.

### Changed
- **Subagent Cost Tiering & Parallel Swarming (`spawn_subagent`):** Updated `spawn_subagent(task_prompt: str, model_tier: ModelTier = "low")` to default to the fast, low-cost model tier (`"low"`) while allowing `"medium"` or `"strong"` overrides, and updated `Vault/Master Instructions.md` and tool docstrings to instruct parallel multi-tool/subagent fan-out in a single turn.
- **Prompt Caching Prefix Isolation:** Reordered `Vault/Master Instructions.md` so static constitutional instructions, `{shared_tools}`, and `{vault_structure}` form a contiguous static prefix, and updated `inject_root_instructions(cache_stable=True)` in `src/nexus/core/engine_constitution.py` to align `{current_time}` to the hour boundary (`YYYY-MM-DD HH:00`) at the tail so second-by-second timestamps never invalidate provider KV prompt caches across multi-step tool loops.
