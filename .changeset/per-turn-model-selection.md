---
type: minor
---
### Added
- **Per-Turn Model Selection in Nexus Chat UI (`gui/src/app/ask/page.tsx` & `gui/src/lib/api.ts`):** Added a segmented model selector directly inside the `/ask` chat input bar (`Strong (gemini-4-argon)` vs. `Fast (gemini-3.8-flash)`), quick-start model buttons under `+ New Chat`, `localStorage` persistence (`nexus_chat_model_tier`), live streaming status indicators, and model execution badges on assistant message bubbles.
- **Model Catalog Endpoint & Dynamic Tier Resolution (`src/nexus/core/constants.py` & `src/nexus/api/routers/agents.py`):** Added `resolve_model_config()`, `get_available_models()`, and `GET /api/agents/models` to expose configured model tiers and active provider identifiers to the frontend.
- **Per-Turn `RunnableConfig` Model Routing (`src/nexus/agent/graph.py` & `src/nexus/agent/api.py`):** Updated `call_model(state, config)` and `run_nexus_agent_with_trace(..., model_tier=...)` to pass `model_tier` via LangGraph `RunnableConfig` (`configurable.model_tier`), enabling per-turn model switching without mutating checkpointed message history or invalidating KV prompt caches.
