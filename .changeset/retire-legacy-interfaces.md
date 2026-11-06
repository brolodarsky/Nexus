---
type: minor
---
### Removed
- Retired legacy pre-GUI interfaces and audio transcription scaffolding in a Zero-Vestige refactoring:
  - Deleted `src/nexus/interfaces/telegram.py`, `src/nexus/interfaces/voice.py`, `src/nexus/interfaces/cli.py`, `src/nexus/interfaces/__init__.py`, and removed `src/nexus/interfaces/` directory.
  - Deleted `src/nexus/core/audio.py` (Whisper STT helper) and `src/nexus/main.py` (legacy terminal mission control / Telegram runner).
  - Pruned orphaned package dependencies `python-telegram-bot` and `pyaudio` from `pyproject.toml` and `uv.lock` via `uv remove`.
  - Removed obsolete console script entrypoint `[project.scripts]` `nexus = "nexus.main:main"` from `pyproject.toml`.
  - Removed dead config settings `telegram_bot_token` and `allowed_user_ids` from `EngineSettings` in `src/nexus/core/config.py`.

### Changed
- Standardized canonical access on the Next.js + FastAPI Control Panel (`start.ps1`, `gui/`, `src/nexus/api/`) and headless agent execution (`python -m nexus.agent.api`).
- Updated `src/nexus/agent/api.py` docstring to eliminate legacy interface call sites.
- Cleaned `README.md` repository tree and meta-scripts table to remove all references to legacy pre-GUI interfaces and entrypoints.
