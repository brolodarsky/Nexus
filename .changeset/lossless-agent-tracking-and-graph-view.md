---
type: minor
---
### Added
- **DAG Execution Graph View (`AgentGraphView`)**: Visual topology canvas reconstructing parent-child execution graphs from trace telemetry, linking Commander (`NexusAgent`) to parallel subagent swarms (`Subagent #1`, `Subagent #2`) with status badges, tool call counts, token meters, and an interactive node inspector showing full untruncated prompts, step logs, and returned syntheses.
- **Agent Audit Log Cockpit (`gui/src/app/audit/page.tsx`)**: Full-screen observability surface accessible via the primary sidebar and Mission Control quick actions, featuring live search across historical run snapshots in `logs/runs/`, complete untruncated query and response inspection, subagent fleet breakdowns, and execution DAG visualization.
- **Hierarchical Agent Telemetry**: Added `agent_id` and `parent_id` tracking to `AgentTracer` and trace events, plus thread-safe subagent serial numbering (`subagent-1`, `subagent-2`, ...) and `reset_subagent_counter()`.
- **Lossless Subagent Fleet Logging**: `log_run` in `src/nexus/core/run_logger.py` now groups subagent steps, prompts, tool calls, and syntheses into structured `subagents` arrays and persists aggregated token metrics.

### Changed
- **Thinking Panel (`ThinkingPanel`)**: Replaced truncated single-line trace log with an interactive 3-mode visualizer supporting Graph View, All Steps (with expandable uncut tool arguments & results), and Raw JSON, with toggles for compact scroll vs. full uncut height.
- **Lossless Telemetry Across Backends**: Eliminated character truncation across `src/nexus/core/trace.py`, `src/nexus/agent/graph.py`, `src/nexus/agent/api.py`, and `src/nexus/core/run_logger.py`, ensuring subagent prompts, tool payloads, and intermediate reasoning are captured without cutoff.
- **Synchronous Trace Capture**: `POST /api/agents/ask` now subscribes to `trace_bus` to persist complete trace events into `chats.db` and `logs/runs/`.
