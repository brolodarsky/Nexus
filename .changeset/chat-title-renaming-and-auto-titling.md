---
type: minor
---
### Added
- **Chat Title Renaming & Inline Editing in Next.js GUI (`gui/`):** Added inline conversation title editing in both `ChatSidebar.tsx` (via hover pencil button or double-click on thread items) and `ChatHeader.tsx` (via click-to-edit or hover pencil button) with keyboard shortcuts (Enter to save, Escape to cancel) and optimistic UI synchronization.
- **AI Auto-Titling Endpoint & UI Action:** Added `POST /api/agents/ask/conversations/{conversation_id}/auto-title` in `src/nexus/api/routers/agents.py` using fast low-tier models (`gemini-3.8-flash` / `claude-sonnet-4-5`) to summarize the opening turn into a concise 3–6 word topic title. Connected to a dedicated "✨" sparkle action button in `ChatHeader.tsx` and automated background auto-titling after the initial turn of newly started chats.
- **Validation & Safe Error Handling:** Enhanced `PATCH /api/agents/ask/conversations/{conversation_id}` in `src/nexus/api/routers/agents.py` to reject blank/whitespace-only titles with HTTP 400 Bad Request and verify thread existence in SQLite `chats.db` before writing.
- **Unit Test Coverage (`tests/test_chat_titles.py`):** Added 6 unit tests covering manual title updates, validation guards, 404 handling, mock LLM auto-titling, and fallback title generation on LLM timeout/quota exceptions.
