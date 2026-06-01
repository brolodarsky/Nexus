---
type: minor
---
### Changed
- Unified Nexus entry points (`engine/main.py` and `engine/interfaces/telegram.py`) to use the Content Router (`route_content`) instead of the Librarian directly.
- Updated the Content Router's fallback logic to escalate general knowledge queries to the Librarian Agent rather than returning a placeholder.
- Added `filters` support to the Router to propagate CLI tags/domains to the Librarian subgraph.
### Fixed
- Fixed a `UnicodeEncodeError` on Windows consoles by forcing `sys.stdout` to UTF-8 in `engine/main.py`.
