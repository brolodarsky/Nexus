---
type: minor
---

- **Persistent Server-Side Trace Buffer & SSE Stream Re-Attachment (`src/nexus/api/routers/agents.py`):**
  - Expanded `ActiveRun` with model metadata (`model_tier`, `model_name`, `model_label`), `user_message_id`, thread-safe buffered `trace_events` replay backlog, multi-subscriber fan-out queues (`publish_trace`, `publish_terminal`, `subscribe`, `unsubscribe`), and status snapshots while retaining `event_queue` compatibility.
  - Added `GET /api/agents/ask/active`, `GET /api/agents/ask/active/{conversation_id}`, and `GET /api/agents/ask/stream/{conversation_id}` using a shared `_stream_active_run` SSE generator that atomically replays prior execution steps and continues streaming live events (or emits `sync_required` if the turn finished right before attachment).
  - Guarded `POST /api/agents/ask/stream` with an `HTTP 409` duplicate-run check per conversation and unified active-run cancellation across `POST /api/agents/stop-and-revert` and `DELETE /api/agents/ask/conversations/{conversation_id}` (`_cancel_active_run_record`).
  - Added `_sanitize_for_json` and `_safe_json_dumps` across SSE stream emission (`_stream_active_run` and `reattach_brain_stream` `sync_required`) so non-finite floats (`NaN`, `Infinity`) and non-JSON objects serialize safely instead of breaking browser `JSON.parse()` or aborting streams before `"done"`.
- **Chat GUI Active-Run Discovery, Re-Attachment, Live Indicators & Auto-Completion Recovery (`gui/`):**
  - Extended `gui/src/lib/api/stream.ts` (`attachBrainStream`, shared `consumeBrainSseStream`, `"sync_required"` event, `onActivity` callback, `/\r?\n\r?\n/` SSE block framing, and a 35s `SSE_HEARTBEAT_TIMEOUT_MS` inactivity watchdog so silent/half-open sockets trigger recovery instead of hanging indefinitely) and `gui/src/lib/api/agents.ts` (`getActiveRuns`, `getActiveRunStatus`, `ActiveRunStatus`).
  - Updated `gui/src/app/chat/page.tsx` to detect active background runs when opening/switching chats, returning to `/chat`, or regaining focus/visibility/network (`visibilitychange`, `window.focus`, `window.online`), restore the live thinking banner + `Stop & Revert` + replayed steps seamlessly, auto-reattach on transient disconnects with 12-attempt bounded exponential backoff and `getActiveRunStatus` probe retries, reconcile finished turns via a 3s loading/active-run watchdog (`historyMatchesMessages`, `minReplyHistoryLength`) even when a `done` frame is missed, and show sidebar active badges.
  - Updated `gui/src/components/chat/ChatMessageThread.tsx` (conversation-scoped `key` on live `ThinkingPanel`), `gui/src/components/chat/ChatSidebar.tsx` (`activeRunConvIds` pulsing cyan dots), and `gui/src/components/AgentTraceVisualizer.tsx` (React 19 state derivation cleanup).
- **Automated Verification (`tests/test_chat_stream_reattach.py`):**
  - Added tests covering mid-turn trace backlog replay + live continuation, inactive-thread `sync_required`, `409 Conflict` duplicate run rejection, active-run cancellation on conversation deletion, and `_safe_json_dumps` sanitization of non-finite floats and `Path` objects.

