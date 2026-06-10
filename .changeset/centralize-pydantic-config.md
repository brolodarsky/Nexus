---
type: minor
---
### Added
- Created `src/nexus/core/config.py` using Pydantic `BaseSettings` to serve as the centralized source of truth for environment variables.
- Added dynamic injection of `{datetime}` and `User` to `src/nexus/core/engine_constitution.py`.
- Installed `pydantic-settings` via `uv` and updated `requirements.txt`.
### Changed
- Refactored `src/nexus/core/constants.py`, `src/nexus/interfaces/telegram.py`, and `src/nexus/agents/email/tools.py` to replace scattered `os.getenv` calls with strongly-typed `settings` from `config.py`.
### Removed
- Removed static `ENGINE_CONSTITUTION.md` and replaced it with a dynamic Python module.
