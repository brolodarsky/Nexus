---
type: minor
---
### Changed
- Refactored entire agent swarm architecture (Router, Email, Career, Librarian) into modular `api.py`, `graph.py`, `tools.py` structure.
- Globalized pure Python vault filesystem I/O operations into `engine/shared_tools/vault_reader.py`.
- Extracted shared cross-agent @tool wrappers (e.g. `ask_librarian_escalation`, `propose_write`) into `engine/shared_tools/shared.py`.
- Updated all API routes and CLI tools to consume agents strictly via their public `api.py` boundaries.
### Removed
- Deleted legacy monolithic `engine/tools/vault_tools.py` and `engine/tools/` directory.
