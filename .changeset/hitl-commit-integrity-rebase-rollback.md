---
type: minor
---
### Added
- Added HITL commit integrity (`commit_transaction`, `rollback_transaction`, `three_way_merge`, `rebase_transaction`, `get_recent_revisions`) and a pre-commit `revisions` snapshot table in `src/nexus/core/hitl_queue.py`.
- Added `POST /api/hitl/{tx_id}/rebase`, `POST /api/hitl/{tx_id}/rollback`, `GET /api/hitl/revisions/recent`, and structured HTTP 409 (`stale_base` / `merge_conflict`) responses in `src/nexus/api/routers/hitl.py`.
- Added Pre-Commit Preview tab, 3-Way Stale-Base Conflict Viewer, Rebase/Force actions, and Recently Applied Undo list in `gui/src/app/hitl/page.tsx` plus shared `gui/src/components/MarkdownMessage.tsx`.
- Added 20 unit and FastAPI integration tests in `tests/test_hitl_commit.py` (`pytest` dev dependency).
### Fixed
- Fixed `src/nexus/core/seed_hitl.py` import path (`nexus.core.hitl_queue`) and post-action selection state in `gui/src/app/hitl/page.tsx`.
