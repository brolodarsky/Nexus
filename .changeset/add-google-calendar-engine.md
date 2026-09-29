---
type: minor
---

### Added
- Created `src/nexus/shared_tools/calendar_engine.py` providing deterministic Google Calendar API integration (`list_events`, `create_event`, `update_event`, `delete_event`, `clean_html_description`, and CLI commands) with UTF-8 Windows terminal support.
- Added agentic shared LangChain `@tool` wrappers in `src/nexus/shared_tools/shared.py` (`get_calendar_schedule`, `create_calendar_event`, `update_calendar_event`).
- Documented `calendar_engine.py` in `README.md` under Deterministic Tools.

### Changed
- Extended `src/nexus/core/google_auth.py` with `token_filename` parameter to enable isolated OAuth tokens per service (`token_calendar.json` vs `token.json`).
