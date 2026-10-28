---
type: minor
---
### Changed
- **Unified Shared Agent Blackboard (`src/nexus/core/blackboard.py`):** Eliminated artificial agent channel tagging and channel inference (`infer_channel`) in favor of a single, unified situational bulletin stream. Added automatic SQLite schema migration in `init_board_db()` using native `ALTER TABLE bulletins DROP COLUMN channel` while safely absorbing deprecated kwargs for backward compatibility.
- **Agent Orchestrator & Tool Signatures (`src/nexus/agent/graph.py` & `src/nexus/shared_tools/shared.py`):** Updated `spawn_subagent` auto-publishing to post directly to the unified blackboard without channel tagging or channel inference. Simplified `post_to_board` and `read_board` tool signatures and docstrings, removing channel arguments.
- **FastAPI Router & Control Panel UI (`src/nexus/api/routers/board.py`, `gui/src/lib/api.ts`, & `gui/src/app/ask/page.tsx`):** Streamlined `/api/board` REST endpoints, removed channel filter tabs from the `/ask` right drawer, and pruned channel badges from bulletin feed cards in favor of author, ID, and pin status indicators.
### Added
- **Blackboard Unit Test Suite (`tests/test_blackboard.py`):** Added 7 comprehensive unit tests covering bulletin posting, pinned-first retrieval, Markdown digest formatting, deletion, clear-all, legacy kwargs tolerance, and schema migration.
