---
type: patch
---
### Security
- Fixed arbitrary-file-read and path traversal vulnerability in `src/nexus/shared_tools/vault_reader.py` (`resolve_vault_note_path`): rejected absolute paths and Windows drive letters upfront, resolved all candidate paths (direct and basename fallback) against `VAULT_PATH.resolve()` (or resolved domain root), and enforced `is_relative_to()` containment before reading or returning paths.
- Hardened path containment across all path-accepting functions in `src/nexus/shared_tools/vault_reader.py` (`get_directory_tree`, `search_within`, `get_recent_modifications`) via `_resolve_vault_dir` and pruned symlinks escaping the Vault.
- Hardened FastAPI Vault routes in `src/nexus/api/routers/vault.py` (`/structure`, `/note`, `/search`, `/list`, `/podcast/generate`, `/podcast/download`) by rejecting absolute/drive-letter inputs and resolving both sides against `VAULT_PATH.resolve()`.
- Hardened `get_run()` in `src/nexus/core/run_logger.py` and `GET /api/agents/runs/{run_id}` in `src/nexus/api/routers/agents.py`: rejected `run_id` inputs containing path separators or `..`.
- Hardened `read_file` and `create_file` LangChain tool wrappers in `src/nexus/shared_tools/shared.py` with strict Vault boundary enforcement.
### Added
- Added automated security test suite in `tests/test_path_safety.py` verifying rejection of traversal payloads (`../.env`, `..\\.env`, `C:\\Windows\\win.ini`, `/etc/passwd`, `3. Operations/../../.env`), escaping symlinks, and successful resolution of valid notes and unique basenames.
