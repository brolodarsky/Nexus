---
type: minor
---
### Added
- Added `get_recent_modifications` to `src/nexus/shared_tools/vault_reader.py` along with a `[CLI]` entrypoint (`python -m nexus.shared_tools.vault_reader --today` / `--hours` / `--since` / `--path` / `--tree` / `--read` / `--search`) to deterministically list Vault documents created or edited within a time window.
- Added `@tool def get_recent_modifications` wrapper in `src/nexus/shared_tools/shared.py` and bound it to the Librarian agent (`src/nexus/agents/librarian/tools.py` & `graph.py`).
