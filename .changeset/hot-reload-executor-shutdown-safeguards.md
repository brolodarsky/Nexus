---
type: patch
---
### Added
- Added `_invoke_tool_node_resilient()` in `src/nexus/agent/graph.py` to automatically fall back to sequential in-thread tool execution when `ToolNode`'s `ContextThreadPoolExecutor` raises `RuntimeError('cannot schedule new futures after shutdown')` during a `uvicorn --reload` worker restart.
- Added human-readable error translation in `run_nexus_agent_with_trace()` (`src/nexus/agent/api.py`) for `cannot schedule new futures after` and `BrokenThreadPool` exceptions.
- Added 2 unit tests in `tests/test_model_config_and_resilience.py` covering synchronous tool fallback and reload error translation.

### Changed
- Updated `start.ps1` to scope Uvicorn file watching with `--reload-dir src/nexus`, exclude standalone CLI tools and SQLite files (`--reload-exclude export_conversation.py`, `--reload-exclude *.db*`, `--reload-exclude *.sqlite*`), and set `--timeout-graceful-shutdown 30`.

### Removed
- Removed orphaned 0-byte `src/nexus/agent/hitl.db` file.

