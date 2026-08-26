# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [2.11.0] - 2026-08-26

### Added
- Created `scripts/audit_career_drift.py` for deterministic Tier-1 career document drift auditing (timestamp staleness, character bounds, skill coverage, telemetry).
- Created `.agents/workflows/audit_career.md` (`/audit_career` slash command) for running cross-document career audits.
- Added Three-Tier Drift Prevention & Sync Architecture and Phase 2 roadmap milestones to `Project - Career Agent.md`.
- Integrated `/audit_career` checks into `Protocol - Career Maintenance.md`.
- Created `.agents/rules/code_commenting_standards.md` establishing mandatory granular, educational code-commenting standards tailored to the developer's learning style.
- Updated `AGENTS.md` (both in Nexus and Portfolio) and `README.md` with standing directives and architectural documentation requiring line-by-line syntax breakdowns, concrete examples for generics/types, and strict preservation of existing educational comments.
- Implemented `HTMLToMarkdownParser` in tools.py for stream parsing HTML emails into clean Markdown while preserving clickable hyperlinks `[text](url)`, headings, and lists.
- Added `_fetch_headers_batch` to execute single-trip IMAP header queries, eliminating N+1 network latency.
- Added `_build_imap_query` to translate natural-language and freeform search phrases into valid RFC-3501 IMAP query filters.
- Upgraded read_email.py CLI with `--search` flag and formatted tabular display.

### Changed
- Added dense, pedagogical inline and pre-block educational comments across `gui/src/lib/api.ts`, `src/nexus/api/routers/agents.py`, `src/nexus/core/trace.py`, `src/nexus/agents/router/graph.py`, and `src/nexus/agents/career/graph.py` adhering to `.agents/rules/code_commenting_standards.md`.

### Fixed
- Corrected relative path resolution in `src/nexus/shared_tools/resume_engine/render.js`, `render_docx.py`, and `inspect_docx.js` following the engine folder reorganization.
- Fixed relative paths to virtual environment and vault directories in `generate_podcast.py` and `ingest_phone.py`.
- Fixed silent body omission bug in `_extract_body` where empty `text/plain` multipart payloads prevented rich HTML fallback.
- Suppressed non-visual HTML containers (`<style>`, `<script>`, `<head>`, `<svg>`, `<noscript>`) to eliminate stylesheet leakage into parsed emails.

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
