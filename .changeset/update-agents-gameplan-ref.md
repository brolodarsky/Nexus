---
type: patch
---
### Changed
- Updated `AGENTS.md` and `.agents/rules/builder_work_tracking.md` to reference `Vault/Gameplan.md` (`# Today` → `## Tasks`) instead of the retired `Vault/1. Core/1.1. Philosophy & Personal North Star/Plan.md` (`## Career & Technical`) path.
- Isolated `chats_db.DB_PATH`, `blackboard.BOARD_DB_PATH`, and `hitl_queue.DB_PATH` to `tmp_path` across conversation and SQLite unit tests so test runs never pollute live databases.
