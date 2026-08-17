---
type: minor
---
### Added
- Created `src/nexus/shared_tools/export_conversation.py` as a universal JSON/JSONL chat transcript parser and formatter (supporting generic JSON message lists, JSONL streams, ChatGPT exports, stdin piping, and local Antigravity transcripts).
- Added CLI capabilities for direct Markdown export (`-o`), Obsidian Inbox ingestion with YAML frontmatter (`-v` / `--vault-inbox`), thinking blocks accordion (`-t`), and stdout output (`--stdout`).
- Added local conversation transcript discovery helpers (`--list`, `--latest`, UUID prefix matching).
- Documented tool in `README.md` and `Project - Nexus Agentic Engine.md`.

### Removed
- Cleaned up obsolete temporary BLOB inspection scripts (`scripts/inspect_antigravity_db.py`, `scripts/extract_antigravity_preview.py`).
