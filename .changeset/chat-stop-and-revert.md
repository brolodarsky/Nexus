---
type: minor
---

### Added
- **Chat Stop & Revert Action (`gui/src/` & `src/nexus/`):** Added a first-class Stop & Revert capability to Nexus Chat, allowing users to immediately halt in-flight agent execution and cleanly roll back all turn state with zero orphan mutations left behind.
- **FastAPI Stop & Revert Endpoint (`POST /api/agents/stop-and-revert`):** Implemented an atomic route coordinating thread-safe execution cancellation, pending HITL transaction purging, LangGraph checkpointer rollback, and chats.db message removal, returning the user's prompt text and image attachments for composer recovery.
- **Thread Cancellation Registry & Checks (`src/nexus/agent/graph.py`):** Added `_CANCEL_EVENTS` registry and `is_thread_cancelled(thread_id)`. Wrapped `call_model`, `traced_tool_node`, `route_after_agent`, and `spawn_subagent` with cancellation checks raising `InterruptedError` to halt LangGraph cycles immediately without corrupting SQLite handles.
- **Checkpointer Memory Rollback (`src/nexus/agent/graph.py`):** Authored `rollback_checkpoints_for_thread(thread_id, pre_turn_checkpoint_id)` which prunes newer checkpoints and channel writes from `memory.sqlite` back to the pre-turn baseline.
- **HITL Transaction Cancellation (`src/nexus/core/hitl_queue.py`):** Added `cancel_pending_transactions_for_conversation(conversation_id)` to transition all unapproved pending file mutations staged during the aborted turn to status `'cancelled'`.
- **Chat Message Purging & Prompt Extraction (`src/nexus/core/chats_db.py`):** Added `revert_last_turn(conversation_id)` to purge user and assistant messages from `chats.db` in reverse chronological order and extract prompt text and attached images.
- **Dynamic UI Buttons & Keyboard Shortcuts (`ChatInputBar.tsx`, `ChatMessageThread.tsx`, `ChatMessageItem.tsx`, `page.tsx`):**
  - Replaced disabled send button in `ChatInputBar` with a rose-styled `[ ⏹ Stop & Revert ]` button while streaming.
  - Added an inline `[ ⏹ Stop & Revert ]` button to the live thinking banner in `ChatMessageThread`.
  - Added `Escape` key shortcut during streaming to trigger instant stop & revert.
  - Added a `[ ↩ Revert turn ]` pill button to the latest assistant message bubble when idle for post-turn rollback.
  - Restored query text and images into the composer and focused the textarea upon stop or revert.
- **Automated Regression Suite (`tests/test_stop_and_revert.py`):** Added 9 unit and integration tests verifying mid-turn aborts, completed turn rollbacks, HITL cancellation, checkpointer DAG pruning, thread cancellation lifecycles, and FastAPI endpoint handling.
- **Universal Conversation Exporter Modernization (`src/nexus/shared_tools/export_conversation.py`):** Overhauled transcript exporter with Turn Coalescing to aggregate intermediate tool actions into collapsible `<details>` blocks, classify `type: GENERIC` tool stdout accurately, eliminate 12,000-line transcript bloat, and authored unit tests (`tests/test_export_conversation.py`).
