---
type: patch
---
### Changed
- **AgentTracer Telemetry Window Headers: Unique Agent ID Display & Inline Tool Call Parameters (`gui/src/components/AgentTraceVisualizer.tsx`):**
  - Replaced the generic `NexusAgent` display badge in `TraceStepCard` with the agent's unique machine/DAG identifier (`evt.agent_id` e.g. `nexus`, `subagent-1`, `subagent-2`), styled in `font-mono` with tooltip provenance metadata, resolving ambiguous duplicate agent labeling across telemetry tiles.
  - Promoted tool call parameters directly into the window headers next to the tool name (`tool_name(k1=v1, k2=v2)`), formatted cleanly via new exported `formatHeaderArgValue` helper with newline sanitization, key-value highlighting, and full tooltip previews.
  - Eliminated the redundant collapsed preview body underneath `tool_call` windows (`evt.type !== "tool_call"`), keeping collapsed tool cards as a single, clean, high-density line.
  - Synchronized DAG node cards in `AgentGraphView` to display explicit `rootNode.id` (`nexus`) and `sub.id` (`subagent-1`) badges alongside display labels.
  - Updated `ChatMessageItem.tsx` and `AuditPage` (`gui/src/app/audit/page.tsx`) to display `message.agent || "nexus"` and inline tool call parameters consistently across chat bubbles and the Subagent Fleet inspector.
