---
type: minor
---

### Added
- Multi-account support in `src/nexus/shared_tools/gmail_engine.py`:
  - Dynamic token filename resolution (`token_gmail.json` for default backward compatibility, `token_gmail_<alias>.json` for named accounts).
  - Configured account discovery via `list_available_accounts()`.
  - New `--account <alias|all>` and `--accounts` CLI flags for inspecting and targeting specific or all accounts.
  - Cross-inbox search, listing, and threading aggregation (`--account all`).

### Changed
- `fetch_emails` tool in `src/nexus/shared_tools/shared.py`: added `account: str = "all"` argument to support querying across all authenticated Gmail accounts by default or filtering to a specific alias.
- Updated `README.md` and `Vault/6. Engineering/6.1. Projects/6.1.2. Agentic R&D/Project - Nexus Agentic Engine/Project - Nexus Agentic Engine.md` with multi-account documentation and build logs.
