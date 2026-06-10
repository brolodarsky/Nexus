---
type: patch
---
### Changed
- Migrated default package management workflow from `uv pip install` & `requirements.txt` to `uv add` and `uv.lock`.
- Updated `AGENTS.md` and `maintain_project_docs` skill to formally deprecate `requirements.txt` in favor of `pyproject.toml`.
### Removed
- Deleted legacy `requirements.txt`.
