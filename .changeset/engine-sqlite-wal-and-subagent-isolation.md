---
type: patch
---

### Fixed
- **Thread-Scoped Subagent Swarms & Active Turn Provider Isolation (`src/nexus/agent/graph.py`, `src/nexus/agent/api.py`):** Eliminated process-level race conditions where concurrent conversations executing subagents clobbered each other's state. Replaced global `_subagent_serial_counter` and `_active_turn_provider` with thread-safe registries (`_thread_subagent_counters`, `_thread_active_providers`), scoped `reset_subagent_counter(active_thread)` strictly to the active turn's conversation, and ensured spawned subagents resolve their model provider family from their parent conversation context.
- **SQLite Concurrency & WAL Hardening (`src/nexus/core/chats_db.py`, `src/nexus/core/blackboard.py`, `src/nexus/core/hitl_queue.py`, `src/nexus/agent/graph.py`):** Enabled Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and 30-second engine busy timeouts (`PRAGMA busy_timeout = 30000;`, `timeout=30.0`) across all SQLite databases (`memory.sqlite`, `chats.db`, `blackboard.db`, `hitl.db`). Prevents `sqlite3.OperationalError: database is locked` during concurrent chat logging, subagent bulletin posting, or checkpoint updates.
- **Automated Regression Suite (`tests/test_sqlite_concurrency.py`, `tests/test_agent_tracking_and_graph.py`):** Authored 6 unit and multi-threaded integration tests verifying WAL mode, busy timeouts, concurrent chat logging (10 parallel workers), concurrent blackboard bulletin posting (8 parallel workers), and thread-isolated subagent counter allocation (164 total pytest tests passing, 0 failures).
