---
type: minor
---
### Added
- **Multi-Account Email Deduplication (`src/nexus/shared_tools/gmail_engine.py`):** Added message-ID deduplication in `list_messages(account="all")` (preferring verified email addresses over fallback aliases such as `"default"`) so aliased OAuth tokens never return duplicate payloads or halve `max_results` depth.
- **Selective Batch Hydration in `fetch_emails` (`src/nexus/shared_tools/shared.py`):** Added `message_ids: Optional[List[str]] = None` (supported by `_hydrate_email_message_entry()`) so agents can batch-hydrate full Markdown bodies (up to 4,000 chars inline + full `cache://email/<id>` captures and non-text notices) strictly for chosen message IDs after scanning.
- **Multi-Keyword Vault Search (`src/nexus/shared_tools/vault_reader.py`, `src/nexus/shared_tools/shared.py`):** Added `keywords: Optional[List[str]] = None` to `search_within()` and `@tool search_vault` (plus multi-arg `vault_reader.py --search kw1 kw2 ...`), performing a single Vault walk and ranking matches by distinct matched term count while keeping single-keyword output formatting backward-compatible.

### Changed
- **Two-Phase Default for `fetch_emails` (`src/nexus/shared_tools/shared.py`):** Changed `fetch_emails` to default `include_body: bool = False`, returning lightweight metadata and snippets (`id`, `account`, `thread_id`, `subject`, `sender`, `date`, `labels`, `snippet`) on search/sweep calls unless `include_body=True` or `message_ids=[...]` is passed.
- **Subagent Batching & Email Hygiene Protocol (`src/nexus/agent/graph.py`, `Vault/1. Core/1.2. Personal Knowledge Management (PKM)/Protocol - Email Triage.md`):** Updated `sub_sys_content` (preserving static KV-cache prefix) and Email Triage protocol to direct parallel tool batching, multi-keyword `search_vault(keywords=[...])`, file slicing, and two-phase `fetch_emails` scanning.
