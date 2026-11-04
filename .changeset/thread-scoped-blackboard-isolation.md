---
type: minor
---

### Added
- **Thread-Scoped Shared Agent Blackboard (`src/nexus/core/blackboard.py`, `src/nexus/agent/graph.py`, `src/nexus/shared_tools/shared.py`, `src/nexus/api/routers/board.py`):** Added `thread_id TEXT` column, automatic schema migration in `init_board_db()`, and SQLite index `idx_bulletins_thread_id` to isolate subagent bulletins to active conversation threads.
- **Ambient Execution Context Propagation:** Subagents spawned in parallel or tools calling `post_to_board` / `read_board` automatically inherit and normalize their parent thread ID via ambient HITL execution context (`_resolve_effective_thread_id`), preventing point-in-time sweeps (Gmail, Calendar, Vault scans) from leaking into unrelated conversations.
- **Thread-Scoped Bulletin Deletion & REST API:** Added `thread_id` query filtering to `GET /api/board` and thread-specific unpinned deletion in `DELETE /api/board` (`clear_bulletins(thread_id=...)`), leaving bulletins in other sessions intact.
- **Dynamic Next.js Blackboard Feed (`gui/src/components/chat/BlackboardDrawer.tsx`, `gui/src/app/chat/page.tsx`, `gui/src/lib/api/board.ts`):** Wired `BlackboardDrawer` to track `activeConvId` in the Next.js Chat interface, showing thread-scoped bulletins, clearing only within the active session, and presenting an empty-state card for fresh conversations.
- **Unit Test Suite (`tests/test_blackboard.py`):** Added 4 test suites verifying thread filtering, cross-thread isolation during clear, ambient execution context inheritance, and idempotent schema migration adding `thread_id` to legacy un-scoped tables (11 total passing tests).

