---
type: minor
---
### Added
- `src/nexus/shared_tools/gmail_engine.py`: Gmail REST API v1 data layer + CLI (native Gmail search, read/thread as markdown, labels, archive, trash, drafts). Scope `gmail.modify`; token isolated in `.secrets/token_gmail.json`. No send function by design.
- `src/nexus/core/tool_catalog.py`: static `ast`-based catalog of `src/nexus/shared_tools/` for prompt hydration.
- `{shared_tools}` placeholder and `## Shared Tools` section in `Vault/Playbook.md`, hydrated by `engine_constitution.py`.
- `python -m nexus.core.engine_constitution` entrypoint that prints the fully hydrated Playbook.
- Module docstrings for `summarizer.py`, `generate_podcast.py`, `medical_xml_parser.py`.
### Changed
- Router `fetch_emails` now calls `gmail_engine` directly (Gmail search syntax, optional `count`, bodies capped at 4,000 chars) instead of delegating to an Email Agent subgraph.
- `AGENTS.md`: Resident agents inject the hydrated Playbook via the engine instead of reading the raw template.
### Removed
- Email Agent subgraph (`src/nexus/agents/email/`, including its evals).
- IMAP/XOAUTH2 email client and `src/nexus/shared_tools/read_email.py`.
- `email_address` / `imap_*` settings from `core/config.py`.
