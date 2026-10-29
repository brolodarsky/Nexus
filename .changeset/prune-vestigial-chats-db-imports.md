---
type: patch
---
### Removed
- **Decommissioned Sticky Routing Residue (`src/nexus/api/routers/agents.py`, `src/nexus/core/chats_db.py`, `gui/`):** Purged vestigial sticky agent session tracking from the codebase. Removed `set_active_agent` and `get_active_agent` database helpers, removed `active_agent` from new conversation creation in SQLite, deleted `POST /api/agents/ask/conversations/{id}/reset` route, removed unused `get_conversation` import, and purged `resetConversationRouting()` API helper, dead "Reset Routing" button, and static `"Auto-Routing"` label from the frontend chat UI.
