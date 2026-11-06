---
type: patch
---

### Fixed
- **Unbounded SQLite Chat History Retrieval (`chats_db.py`, `agents.py`):** Fixed long-thread message truncation where `get_chat_history()` defaulted to `limit=50`, causing conversation threads exceeding 50 turns to omit newer messages and visual image attachments when fetching history or re-syncing on tab focus.
- **FastAPI Endpoint History Limit Parameter (`/api/agents/ask/history`):** Added optional `limit: Optional[int] = None` query parameter defaulting to unbounded chronological retrieval (`ORDER BY id ASC`), ensuring full fidelity for long-running chat sessions while preserving limit functionality for specialized callers (e.g. title generation).
- **Regression Unit Tests:** Added unit test coverage verifying that conversation threads with >50 turns and image attachments are retrieved in full without message truncation.
