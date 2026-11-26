---
type: minor
---
### Added
- **API Bearer Token Auth & Host Validation (`src/nexus/api/security.py`, `main.py`, `start.ps1`, `gui/src/lib/api/`):** Added `.secrets/api_token` auto-generation (`get_or_create_api_token`), constant-time `verify_api_token` across `/api/*` routers (keeping `/api/health` public, scoping `?token=` strictly to GET/HEAD media/upload routes, and validating loopback `chrome-extension://` probes/WS for `/api/browser`), pure-ASGI `HostValidationMiddleware` with `NEXUS_LOCALHOST_ONLY` lockdown support, automatic `start.ps1` sync into `gui/.env.local`, and auth header injection across frontend API/SSE/upload clients and `browser_bridge.py`.
- **Single-Turn Strong Boost (`1× Boost`) Auto-Revert (`gui/src/app/chat/page.tsx`, `ChatInputBar.tsx`, `chats_db.py`, `routers/agents.py`):** Added `⚡ 1× Boost` single-turn escalation auto-revert (with clickable `📌 Sticky Strong` override pill) and `persist_conversation_model` support so boosted turns log true model telemetry without overwriting the thread's baseline model.
- **LangSmith Startup Privacy Guard (`src/nexus/core/config.py`, `agent/api.py`, `api/main.py`):** Added `is_langsmith_tracing_enabled()` and one-time `warn_if_langsmith_enabled()` startup warnings.

### Changed
- **Symmetric Medium-Tier Routing, Per-Tier Timeouts, Subagent Clamp & Dec 1 Argon Cutover (`config.py`, `constants.py`, `cost.py`, `subagent.py`, `graph.py`, `scripts/audit_run_costs.py`, `gui/src/components/chat/types.ts`):** Set `gemini_model_medium = "gemini-4-hydrogen"` and `nexus_primary_tier = "medium"`, split per-tier timeouts (`ai_timeout_strong = 180` / `1` retry vs. `ai_timeout_default = 60` / `2` retries), clamped `spawn_subagent` `"strong"` requests to `"low"` unless `NEXUS_ALLOW_STRONG_SUBAGENTS=true`, defaulted `LANGCHAIN_TRACING_V2=false`, and added date-aware `2026-12-01` Gemini 4 Argon rate cutover (`$4/$0.20/$20`) while preserving historical pre-Dec-1 audit pricing.
- **Documentation & Tests:** Synced `README.md` and added `tests/test_api_security.py` plus coverage in `tests/test_model_config_and_resilience.py`, `tests/test_cost_tracking.py`, and `tests/test_chat_model_memory.js`.

### Fixed
- Renamed `tier_Wait_labels` typo to `tier_labels` in `src/nexus/core/constants.py`.
