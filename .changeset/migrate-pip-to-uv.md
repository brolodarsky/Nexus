---
type: patch
---
### Changed
- Migrated python environment management from `pip` and `python -m venv` to Astral's `uv` for improved speed and determinism.
- Updated `AGENTS.md`, `README.md`, and `maintain_project_docs` skill to enforce `uv pip` usage.
