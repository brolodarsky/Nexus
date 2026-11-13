---
type: patch
---

### Added
- Created `src/nexus/core/chat_titles.py` as a centralized, thread-safe conversation auto-titling service with per-conversation in-flight coalescing (`_inflight_titles`), a bounded background `ThreadPoolExecutor` (`schedule_auto_title`), non-blocking `asyncio.to_thread` + `chat_model.ainvoke` coroutine execution (`auto_generate_title_async`), and atomic Compare-and-Swap (`_commit_title_result`) protection.
- Added `title_source` column (`placeholder` | `auto` | `manual` | `legacy`) and idempotent schema migration to `chats_db.conversations`, plus atomic `expected_title` and `only_if_placeholder` predicates on `update_conversation_title()`.
- Added comprehensive auto-titling concurrency, CAS race, branch-titling, and legacy migration tests in `tests/test_chat_titles.py`.

### Changed
- Triggered automatic server-side Turn-1 auto-titling (`schedule_auto_title`) directly in both `/api/agents/ask/stream` (`_run_pipeline`) and `/api/agents/ask` (`ask_brain`), plus failed-first-turn fallback titling and continued-thread title recovery in `telegram_bridge.py`.
- Updated `POST /api/agents/ask/conversations/{id}/auto-title` with `?force=true|false` (`force=true` default for manual regeneration, `force=false` for non-destructive automatic UI reconciliation) and offloaded `PATCH /api/agents/ask/conversations/{id}` SQLite calls via `asyncio.to_thread`.
- Updated `gui/src/app/chat/page.tsx` and `gui/src/lib/api/agents.ts` with `refreshConversationsAndSyncTitles()` across `onDone`, `onError` DB recovery, `pollActiveRuns`, `recoverActiveView`, and `reconcileHistoryFromServer`, while preserving manual renames (`title_source="manual"`).

### Fixed
- Wrapped `chats_db._get_conn()` in `@contextlib.contextmanager` so SQLite connections are always committed/rolled back and explicitly closed in `finally` instead of relying on Python's context-manager behavior (which only committed/rolled back transactions and leaked open file descriptors).
- Fixed new branched conversations without user-supplied titles (`fork_conversation`) staying permanently stuck on `🌿 ...` placeholders instead of auto-titling on their first branch turn.
