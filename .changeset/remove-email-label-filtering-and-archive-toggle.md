---
type: minor
---
### Changed
- Removed manual `label:Jobs`/`label:Industry` sweep rules from Career `Section Instructions.md` and simplified `fetch_emails(count=10, include_archived=False, query="", ...)` in `src/nexus/shared_tools/shared.py` and `list_messages()` in `src/nexus/shared_tools/gmail_engine.py` to sweep `in:inbox` regardless of labels by default.
### Added
- Added `include_archived: bool = False` option to `gmail_engine.list_messages()` and `shared.fetch_emails()`, plus `--include-archived` CLI flag on `nexus.shared_tools.gmail_engine`.
