---
type: patch
---
### Changed
- `scripts/sync_vault.py`: Automatically runs `git push` after committing changes (and pushes pre-existing unpushed commits if working tree is clean). Added cross-platform UTF-8 stream handling.
- `README.md`: Updated description of `sync_vault.py` and removed `backup_vault.py`.

### Removed
- `scripts/backup_vault.py`: Removed obsolete backup script in favor of direct external backup tools.
