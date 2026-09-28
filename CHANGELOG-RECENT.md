# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [2.13.0] - 2026-09-27

### Added
- Added `cognitive_boundary_flush` skill (`.agents/skills/cognitive_boundary_flush/SKILL.md`) implementing the 4-tier Hippocampal Flush protocol.
- Added `/flush` slash-command workflow (`.agents/workflows/flush.md`) for explicit event boundary execution.
- Added Engine Coding Standard 21 to `AGENTS.md` mandating proactive Hippocampal Flush prompting upon session conclusion or context switches.
- Updated Section 10 of Engine Constitution (`src/nexus/core/engine_constitution.py`) with the formal 5-step Hippocampal Flush protocol.
- Added `/archive_contact` agentic workflow (`.agents/workflows/archive_contact.md`) for systematic pruning of closed, rejected, or stale networking contacts and requisitions.
- Defined formal CRM Archiving Protocol in `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Protocol - Career Maintenance.md` to preserve Tier 3 living state context windows by migrating inactive rows to `Professional CRM - Archive.md`.
- Integrated Standardized Section Anatomy (Section 9) and Event-Driven Cognitive Boundaries (Section 10) into `src/nexus/core/engine_constitution.py`.
- Added FastMCP dependency (`mcp>=1.30.0`) to `pyproject.toml` and `uv.lock`.
- Updated public `Table of Contents.md` with link to `Concept - Cognitive Boundaries & Event-Driven Agent Memory`.
- Added Engine Standard 20 (`Episodic Life Archiving & Anti-Hallucination Grounding`) to `AGENTS.md` and established Section 1.1 `Playbook.md` to ensure agents interactively verify daily events via calendar and user confirmation, reject copy-pasting aspirational container templates or routine habits, and preserve a grounded 4-compartment life/mission record.
- Integrated the rolling working-set sliding envelope protocol into `.agents/workflows/weekly_review.md` and `.agents/skills/career_counselor/SKILL.md` to ensure `Short Term Execution Plan.md` tracks active working sets only (excluding rest days), places today's granular containers at the top for ADHD focus, enforces proactive prior-day reconciliation prompting, and heavily compresses past/future sets.

### Changed
- Clarified the Project Scope Docs hierarchy in `AGENTS.md` to distinguish software infrastructure projects (compiled Python subgraphs in `src/nexus/` and GUI apps) from declarative domain section subagents (governed natively by standardized section files in `Vault/<Section>/`, eliminating duplicate child project docs).

### Deprecated
- Deprecated and removed legacy `log_llm_conversation` skill in favor of localized atomic episodic archiving in `<Section>/Archive/Conversations/` and domain-scoped ADR logging.

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
