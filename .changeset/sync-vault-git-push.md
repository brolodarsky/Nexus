---
type: patch
---
### Changed
- `scripts/sync_vault.py`: Automatically runs `git push` after committing changes (and pushes pre-existing unpushed commits if working tree is clean). Added cross-platform UTF-8 stream handling.
- `scripts/backup_vault.py`: Updated targets and usage comments to reflect current project structure (`src`, `scripts`, `gui`, `pyproject.toml`) and added cross-platform UTF-8 stream handling.
- `README.md`: Updated description of `sync_vault.py` and `backup_vault.py`.
