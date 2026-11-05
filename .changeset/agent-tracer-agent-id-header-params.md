---
type: patch
---
### Changed
- **AgentTracer Telemetry Window Headers: Renamed Commander to Head Agent & Inline Tool Call Parameters (`src/nexus/agent/`, `gui/src/`):**
  - Renamed the root commander agent from generic `"nexus"` / `"NexusAgent"` to **`"Head Agent"`** across console tracer (`nexus_tracer = AgentTracer("Head Agent", ...)`), HITL execution context roles (`Head Agent (<tier>)`), and UI step card badges (`TraceStepCard`).
  - Child subagents retain their clean thread-safe serial IDs (`subagent-1`, `subagent-2`, ...), creating an intuitive visual hierarchy: `Head Agent` $\to$ `subagent-1`, `subagent-2`.
  - Promoted tool call parameters directly into window headers next to the tool name (`tool_name(k1=v1, k2=v2)`), formatted cleanly via `formatHeaderArgValue` with newline sanitization, key-value highlighting, and full tooltip previews.
  - Eliminated the redundant collapsed preview body underneath `tool_call` windows (`evt.type !== "tool_call"`), keeping collapsed tool cards as a single, clean, high-density line.
  - Synchronized DAG node cards in `AgentGraphView` to display explicit `Head Agent (Root)` and `sub.id` badges alongside display labels.
  - Updated `ChatMessageItem.tsx` and `AuditPage` (`gui/src/app/audit/page.tsx`) to display `Head Agent` and inline tool call parameters consistently across chat bubbles and the Subagent Fleet inspector.
