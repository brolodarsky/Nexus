# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [2.10.0] - 2026-08-20

### Added
- Added `/weekly_review` workflow to systematize Sunday evening weekly review and planning.

### Changed
- `project_work` skill: Added Build Log formatting standards enforcing past-tense action verbs and prohibiting redundant `- **Completed:**` prefixes.
- `/create_project` workflow: Modernized workflow to scaffold the canonical 7-section project note architecture (`Goal`, `Current State`, `Architecture`, `Standing Guidelines`, `Build Log`, `Roadmap`, `Resources`), TOC back-links, and To Do List registration.
- Standardized instruction hierarchy, atomic sub-bullet density, and clean structural anchors across all `.agents/skills/` and `.agents/workflows/`.
- Refactored `skill_creator` and `workflow_creator` meta-standards from first principles to prioritize structural hierarchy and atomic instruction density.
- Extracted shared medical research, citation, and safely caveated tone guidelines into `analyze_health/references/medical_research_protocol.md` to eliminate instruction duplication between `analyze_health` and `analyze_psych`.
- Fixed stale path references in `add_job_requirement.md` (`3.1. Career Strategy & Revenue`) and `AGENTS.md`.
- Synchronized `/create_new_note` and `/release` into `README.md` workflow index.

## [2.9.0] - 2026-08-18

### Added
- Created `src/nexus/shared_tools/export_conversation.py` as a universal JSON/JSONL chat transcript parser and formatter (supporting generic JSON message lists, JSONL streams, ChatGPT exports, stdin piping, and local Antigravity transcripts).
- Added CLI capabilities for direct Markdown export (`-o`), Obsidian Inbox ingestion with YAML frontmatter (`-v` / `--vault-inbox`), thinking blocks accordion (`-t`), and stdout output (`--stdout`).
- Added local conversation transcript discovery helpers (`--list`, `--latest`, UUID prefix matching).
- Documented tool in `README.md` and `Project - Nexus Agentic Engine.md`.
- Created `scripts/` directory to separate meta/maintenance scripts from engine runtime tools.
- New `/release` slash command workflow added in `.agents/workflows/release.md`.
- `release.py` now explicitly handles text encoding `errors='replace'` to avoid crashing on non-UTF-8 changeset fragments.
- Created `src/nexus/shared_tools/` as the new home for all deterministic Python integration scripts (e.g. `read_email.py`, `generate_podcast.py`, `ingest_phone.py`).

### Changed
- Moved meta scripts `release.py`, `backup_vault.py`, `check_folders.py`, `create_folders.py`, `sync_vault.py`, and `add_gitkeeps.py` from `tools/` to the new `scripts/` directory.
- Updated `AGENTS.md` and `README.md` to reflect the new `scripts/` directory and `/release` workflow integration.
- Moved all engine runtime tools from the root `tools/` directory into `src/nexus/shared_tools/`.
- Deleted the root `tools/` directory to enforce a strict boundary between repository maintenance scripts (`scripts/`) and engine components (`src/nexus/`).
- Updated `AGENTS.md` and `README.md` to reflect the new architecture.
- Updated slash command workflows (`/add_job_requirement`, `/capture_content`, `/distill_learning`, `/ingest_medical_record`, `/render_resume`) to point to the new `src/nexus/shared_tools/` paths.
- `scripts/sync_vault.py`: Automatically runs `git push` after committing changes (and pushes pre-existing unpushed commits if working tree is clean). Added cross-platform UTF-8 stream handling.
- `README.md`: Updated maintenance scripts table and sections.

### Removed
- Cleaned up obsolete temporary BLOB inspection scripts (`scripts/inspect_antigravity_db.py`, `scripts/extract_antigravity_preview.py`).
- `scripts/backup_vault.py`: Removed obsolete backup script in favor of direct external backup tools.
- `scripts/create_folders.py`: Removed obsolete initial folder scaffolding script.
- `scripts/check_folders.py`: Removed obsolete dry-run folder checker script.
- `scripts/add_gitkeeps.py`: Removed manual gitkeep script in favor of agentic gitkeep rules.

## [2.8.0] - 2026-08-04

### Added
- Multi-Conversation Chat Architecture: The Ask Brain UI now supports multiple parallel conversation threads decoupled from eternal agent memory.
- Added CRUD API endpoints for conversations under `/api/agents/ask/conversations`.
- `AGENTS.md`: New `Project Scope Docs: Ultimate Authority` section establishing the parent/child project scope hierarchy as the ground truth for all Nexus engine work, with read-before and update-after obligations and conflict resolution rules.
- `project_work` skill: New §5 `Nexus Engine: Parent + Child Project Scope Doc Hierarchy` detailing the exact folder path, doc structure, and mandatory before/after protocol for reading and updating scope docs on every engine task.

### Changed
- Refactored `chats_db.py` to use a `conversations` table instead of a single `sessions` table.
- Career Agent now receives Domain Boundary instructions and emits `[HANDOFF]` to release sticky routing locks.
- Frontend AskBrainPage updated with a two-pane layout featuring a conversation sidebar and "Reset Routing" control.
- Updated model constants in `src/nexus/core/constants.py` by renaming `AI_MODEL` to `AI_MODEL_LOW` and including `AI_MODEL_MEDIUM` and `AI_MODEL_HIGH`. Updated the Career Agent (`src/nexus/agents/career/graph.py`) to use `AI_MODEL_MEDIUM` for main LLM operations and `AI_MODEL_LOW` for conversation summarization, and updated all other model references across router, librarian, email agent, and eval runners to `AI_MODEL_LOW`.
- Updated `/add_job_requirement` workflow to use chronological YYYY-MM-DD naming convention for saved job listings to better track industry trends over time.

### Fixed
- Fixed bug where `RemoveMessage` objects from `summarize_conversation` were incorrectly appended to agent states instead of deleting old messages, causing an OpenAI `BadRequestError` (stringified as `Got unknown type`). Replaced `operator.add` with LangGraph's `add_messages` across career, router, librarian, and email agents.
