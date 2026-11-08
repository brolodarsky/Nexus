---
type: patch
---

### Fixed
- **Multi-Thread Pub/Sub Telemetry Isolation (`src/nexus/core/trace.py`, `src/nexus/api/routers/agents.py`, `src/nexus/agent/`):** Fixed cross-thread trace event pollution where opening multiple agent threads or browser tabs and executing queries concurrently caused telemetry events to leak across streams. Added execution-context-scoped `thread_id` tracking via Python `contextvars`, enhanced `AgentTracer` and subagent constructors with explicit `thread_id`, and updated `TraceEventBus.subscribe()` and `emit()` to enforce strict thread filtering so SSE streams and run logs receive only events belonging to their active conversation.
- **Next.js React Key Collision Prevention (`gui/src/components/AgentTraceVisualizer.tsx`):** Fixed the Next.js runtime error (`Encountered two children with the same key, ead90046`) by replacing raw `key={evt.id ?? idx}` with composite resilient keys `key={evt.id ? `${evt.id}-${idx}` : `step-${idx}`}` across both `AgentGraphView` and `ThinkingPanel`.
- **Chat Stream Abort & State Isolation (`gui/src/app/chat/page.tsx`):** Added automated stream teardown (`abortRef.current?.()`) upon thread switching, new chat creation, or conversation deletion, and added event-ID deduplication and active conversation ownership guards to streaming callbacks (`onTrace`, `onDone`, `onError`) to prevent stale or cross-convo mutations.
- **Automated Regression Suite (`tests/test_agent_tracking_and_graph.py`):** Added unit tests verifying strict pub/sub thread isolation and contextvar/explicit thread inheritance on `AgentTracer`.
