---
type: minor
---
### Added
- Implemented structured JSON execution run logger in `src/nexus/core/run_logger.py` persisting complete agent snapshots to `logs/runs/`.
- Integrated `loguru` structured logging in `src/nexus/core/logger.py` with colorized stdout and rotated file persistence at `logs/engine.log`.
- Created unified engine telemetry and health aggregator in `src/nexus/core/dashboard.py` with Markdown summary generator.
- Added `/api/agents/runs`, `/api/agents/runs/{run_id}`, and `/api/agents/dashboard` REST endpoints in FastAPI router.

### Fixed
- Resolved split-brain thread ID isolation bug by propagating UI `conversation_id` down to LangGraph `thread_id` checkpointers across Router, Career, and Librarian agents.
