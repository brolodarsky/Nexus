---
type: minor
---
### Changed
- Restructured `engine/` directory into a standard `src/nexus/` Python package layout.
- Replaced `requirements.txt` with `pyproject.toml` (using `uv` and `hatchling` backend).
- Updated all internal imports to absolute imports under the `nexus.*` namespace.
- Replaced the standalone `python engine/main.py` command with a managed `nexus` CLI executable.
- Updated `start.ps1` to use absolute imports (`nexus.api.main:app`) and project-root working directory.
### Removed
- Deleted `requirements.txt` in favor of PEP-621 `pyproject.toml` management.
- Removed legacy `sys.path.insert()` and `sys.path.append()` hacks used for standalone script execution.
