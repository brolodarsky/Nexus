---
type: patch
---
### Fixed
- Configured LangGraph `ToolNode` instances (`tool_node` for parent agent and `sub_tool_node` for dynamic subagents in `src/nexus/agent/graph.py`) with `handle_tool_errors=True`. Unhandled tool exceptions (such as Google API `HttpError` 404/500, network disconnects, or unexpected tool faults) now convert into structured `ToolMessage(content=..., status="error")` instead of bubbling uncaught through `ToolNode.invoke()` and abruptly terminating the user's turn.
- Patched `update_calendar_event` and `create_calendar_event` in `src/nexus/shared_tools/shared.py` and `calendar_engine.py` with defensive `HttpError` interception so nonexistent event IDs or API errors emit clear, actionable feedback rather than fatal trace crashes.

### Added
- Added event ID exposure (`(id: <event_id>)`) to `format_events_as_markdown` in `src/nexus/shared_tools/calendar_engine.py`, guaranteeing that `get_calendar_schedule` and CLI schedule outputs provide exact Google Calendar event IDs for downstream updates and deletions.
- Added `@tool delete_calendar_event` to `src/nexus/shared_tools/shared.py` and bound it to `CORE_TOOLS` in `src/nexus/agent/graph.py`.
- Added `--json` flag to `src/nexus/shared_tools/calendar_engine.py` CLI for deterministic JSON inspection of calendar events.
- Added 4 unit tests in `tests/test_model_config_and_resilience.py` verifying `ToolNode(handle_tool_errors=True)` error wrapping, event ID formatting in markdown digests, and defensive `HttpError` 404 interception across calendar tools (218/218 total pytest suite passing).
