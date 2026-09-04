# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [2.12.0] - 2026-09-04

### Added
- Implemented structured JSON execution run logger in `src/nexus/core/run_logger.py` persisting complete agent snapshots to `logs/runs/`.
- Integrated `loguru` structured logging in `src/nexus/core/logger.py` with colorized stdout and rotated file persistence at `logs/engine.log`.
- Created unified engine telemetry and health aggregator in `src/nexus/core/dashboard.py` with Markdown summary generator.
- Added `/api/agents/runs`, `/api/agents/runs/{run_id}`, and `/api/agents/dashboard` REST endpoints in FastAPI router.
- Embedded SOTA agentic engineering standards into `AGENTS.md` and `src/nexus/core/engine_constitution.py`: Pydantic-first structured outputs, deterministic AST/YAML pre-commit lint gates, native LangGraph `interrupt()` & `Command` HITL state pausing/resumption, prompt caching prefix isolation, loop circuit breakers, and Sub-Brain living state with atomic conversation archiving (`Archive/Conversations/`).
- Updated master scope doc `Project - Nexus Agentic Engine.md` and all child docs (`Project - Career Agent.md`, `Project - Health Agent.md`, `Project - Forge Agent.md`, `Project - Librarian Agent.md`, `Project - Content Router Agent.md`, `Project - Basic Engine Control Panel.md`) with modern Sub-Brain architectural blueprints, universal shared tooling (`search_my_domain`), and logged architectural evolution to `Log - LLM Conversations.md`.

### Changed
- Clarified `log_llm_conversation` skill trigger and execution boundary to focus exclusively on macro architectural decisions and cognitive idea forging, excluding tactical life task minutiae.
- Architectural paradigm shift: Dynamic Section Subagent Factory & Meta-Orchestration.
- Evolved from static N-agent swarm (one hardcoded Python package per domain) to a Unified Dynamic Section Subagent Factory where one generic SectionSubagent LangGraph engine is parameterized by standardized Vault directory modules (Section Profile.yaml, Playbook.md, Lessons Learned.md, Section Map.md, Tasks.md, Archive/, Logs/).
- Upgraded memory architecture from 3-tier to 5-tier (Working → Session → Procedural → Semantic → Episodic) with Cognitive Inheritance (CI) across parent-child sections.
- Content Router evolved into dual-mode Meta-Orchestrator (Sticky Handoff + Supervisor Worker Spawning).
- Updated all project scope docs, AGENTS.md, engine_constitution.py, and README.md to reflect new architecture.
- Created Glossary - Nexus Engine Terminology note and conversation archive.
- Standardized Section Anatomy in `AGENTS.md` (Standard 18) and `Glossary - Nexus Engine Terminology.md` to formally codify `Log.md` (Operational Rep Log / Event Journal) and `Framework.md` (Permanent Architecture & Living Baseline) per section.
- Migrated technical architecture dialogue records to `Vault/6. Forge/Log.md` and operational cognitive engineering reps to `Vault/2. Health/2.3. Psych/Log.md`.

### Fixed
- Resolved split-brain thread ID isolation bug by propagating UI `conversation_id` down to LangGraph `thread_id` checkpointers across Router, Career, and Librarian agents.

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
