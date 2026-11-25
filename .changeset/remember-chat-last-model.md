---
type: minor
---
### Added
- Persisted `last_model_tier` and `last_model_name` on `conversations` in `src/nexus/core/chats_db.py` with automatic schema migration, `idx_messages_conv_id` indexing, and one-time backfill from existing attributed messages.
- Propagated per-conversation remembered model metadata across conversation creation (`POST /api/agents/ask/conversations`), sync/streaming turns (`src/nexus/api/routers/agents.py`), `revert_last_turn` rollbacks, and child branches/nested spawns (`src/nexus/core/chat_branching.py`) while preventing metadata-less synthetic messages (`branch_context`, `branch_merge`) and error logs from clobbering remembered models.
- Added centralized `RETIRED_MODEL_REPLACEMENTS`, `resolveConversationModelSelection`, and `extractLastUsedModelFromHistory` helpers in `gui/src/components/chat/types.ts` (`gui/src/lib/api/agents.ts`) and wired `gui/src/app/chat/page.tsx` to automatically switch the shared model selector (`ChatSidebar` + `ChatInputBar`) to each conversation's last-used model on load, thread switch, and deletion fallback without overriding manual selections or polluting global `localStorage` defaults.
- Added backend and frontend regression coverage in `tests/test_chats_db_telemetry.py`, `tests/test_chat_branching.py`, and `tests/test_chat_model_memory.js`.
