---
type: patch
---
### Fixed
- Preserved Windows NTFS creation timestamps (`CreationTime` / `st_birthtime`) across HITL `_atomic_write` replacements and atomic file moves/rollbacks in `src/nexus/core/hitl_queue.py` via `_get_creation_time_ns()` and Win32 `SetFileTime` (`_set_windows_creation_time_ns()`), preventing `os.replace()` from resetting `st_ctime` on edited notes.
- Cross-checked `hitl.db` non-rolled-back `revisions` (`_find_preexisting_files_from_hitl()`) inside `get_recent_modifications()` in `src/nexus/shared_tools/vault_reader.py` so pre-existing notes edited within the query window are accurately badged `[EDITED]` instead of `[NEW]`.
