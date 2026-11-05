---
type: minor
---

### Added
- **Atomic File Move & Delete Tools (`src/nexus/shared_tools/shared.py`):** Added `@tool move_file(source_path, destination_path, reasoning, overwrite=False)` and `@tool delete_file(file_path, reasoning)` to the core tool library, enabling clean note relocation and archival (e.g. concluded Missions from `Campaign - */` to `Archive/YYYY/`) without leaving orphaned active documents on disk.
- **Core Tool Binding (`src/nexus/agent/graph.py`):** Bound `move_file` and `delete_file` into `CORE_TOOLS`, granting direct access to both the primary orchestrator (`NexusAgent` / Astra) and parallel subagents spawned via `spawn_subagent`.
- **HITL Two-Phase Commit Schema & Handlers (`src/nexus/core/hitl_queue.py`):**
  - Added `destination_file TEXT` column to `transactions` and `revisions` with automatic idempotent schema migrations in `init_db()`.
  - Added atomic commit and rollback support for `action_type="move"` and `action_type="delete"`:
    - Pre-commit stale-base verification ensuring source files have not drifted on disk in Obsidian.
    - Destination collision guards preventing un-flagged overwrites.
    - Pre-commit snapshots in `revisions` enabling 100% reversible rollbacks (re-linking deleted files or moving files back to source).
    - Updated `get_pending_for_file` to match across both `target_file` and `destination_file`.
    - Updated `read_file` to surface staged relocation and deletion warning banners.
- **FastAPI Endpoints (`src/nexus/api/routers/hitl.py`):** Added `destination_file` to `TransactionResponse` and `MockTransactionRequest`.
- **Next.js Control Panel Integration (`gui/src/app/hitl/page.tsx`, `gui/src/lib/api/hitl.ts`):** Updated HITL UI to display `source → destination` relocation arrows across ticket items and headers, render pre-commit deletion warnings, and preview destination relocation badges.
- **Unit Test Suite (`tests/test_hitl_commit.py`):** Added test coverage for `commit_transaction` and `rollback_transaction` on moves and deletions, stale-base detection on human edits, collision detection, and tool invocation guards (112 passing pytest tests).
