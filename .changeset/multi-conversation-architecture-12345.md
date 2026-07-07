---
type: minor
---
### Added
- Multi-Conversation Chat Architecture: The Ask Brain UI now supports multiple parallel conversation threads decoupled from eternal agent memory.
- Added CRUD API endpoints for conversations under `/api/agents/ask/conversations`.

### Changed
- Refactored `chats_db.py` to use a `conversations` table instead of a single `sessions` table.
- Career Agent now receives Domain Boundary instructions and emits `[HANDOFF]` to release sticky routing locks.
- Frontend AskBrainPage updated with a two-pane layout featuring a conversation sidebar and "Reset Routing" control.
