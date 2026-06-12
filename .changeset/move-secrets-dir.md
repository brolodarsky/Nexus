---
type: patch
---
### Changed
- Moved the `.secrets` directory from `tools/.secrets` to the project root `.secrets` to align with the new `src/nexus` engine architecture and industry standards for credential management.
- Updated `.gitignore` and `src/nexus/agents/email/tools.py` to reflect the new root `.secrets` location.
