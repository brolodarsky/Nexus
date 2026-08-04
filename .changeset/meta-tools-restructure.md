---
type: minor
---
### Added
- Created `scripts/` directory to separate meta/maintenance scripts from engine runtime tools.
- New `/release` slash command workflow added in `.agents/workflows/release.md`.
- `release.py` now explicitly handles text encoding `errors='replace'` to avoid crashing on non-UTF-8 changeset fragments.

### Changed
- Moved meta scripts `release.py`, `backup_vault.py`, `check_folders.py`, `create_folders.py`, `sync_vault.py`, and `add_gitkeeps.py` from `tools/` to the new `scripts/` directory.
- Updated `AGENTS.md` and `README.md` to reflect the new `scripts/` directory and `/release` workflow integration.
