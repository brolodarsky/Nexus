---
type: minor
---
### Added
- **Relational Telemetry Decoupling (`message_traces` table in `chats_db.py`):** Separated heavy diagnostic JSON trace arrays out of the primary `messages` table into a dedicated `message_traces (message_id INTEGER PRIMARY KEY, trace TEXT, FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE)` table.
- **Message Metadata Columns (`messages` table):** Added `model_tier TEXT`, `model_name TEXT`, `cost_usd REAL`, and `has_trace INTEGER DEFAULT 0` to `messages` for fast scalar indexing without needing to parse multi-megabyte trace JSON arrays.
- **On-Demand Lazy Telemetry Endpoint (`GET /api/agents/messages/{message_id}/trace`):** Mounted a dedicated FastAPI route in `src/nexus/api/routers/agents.py` fetching untruncated trace arrays on demand for a single message row.
- **Next.js Lazy ThinkingPanel Disclosure (`AgentTraceVisualizer.tsx`, `ChatMessageItem.tsx`, `types.ts`):** Enhanced `ThinkingPanel` to accept `messageId?: number`. When expanding a historical message with `hasTrace=true`, it displays an interactive loading spinner and fetches `getMessageTrace(messageId)` on demand. Active streaming turns retain instant zero-network inspection from client memory (`liveTraceRef.current`).
- **Comprehensive Unit Test Suite (`tests/test_chats_db_telemetry.py`):** Authored 8 unit tests validating schema isolation, lean history retrieval, cascade deletion, lazy endpoint responses, and bounded summary previews.

### Changed
- **Ultra-Lean Chat History Retrieval (`get_chat_history`):** Updated `get_chat_history()` to default to `include_trace=False`, selecting only lightweight message metadata and returning `trace: []`. Reduced standard chat history HTTP payloads from multi-megabytes down to ~13 KB for a 50-turn conversation (a 99.5% reduction).
- **Trace Event String Duplication Elimination (`AgentTracer` in `trace.py`):** Formatted bounded summary previews in `tool_call` and `tool_result` string messages and terminal prints, while preserving 100% untruncated arguments and results in `event.data` for the DAG visualizer.
- **Automatic Migration & SQLite Vacuum:** `init_db()` automatically migrates legacy `messages.trace` blobs into `message_traces`, populates scalar metadata columns, sets `messages.trace = NULL`, and executes SQLite `VACUUM;` to reclaim disk space.
