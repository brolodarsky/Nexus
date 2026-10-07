# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [2.14.0] - 2026-10-07

### Added
- Added rule 22 to `AGENTS.md` (Self-Managing Documents): Establishing the `# Document Playbook` architecture for complex living state documents, encapsulating maintenance/archival logic directly inside the data layer.
- Created `src/nexus/shared_tools/calendar_engine.py` providing deterministic Google Calendar API integration (`list_events`, `create_event`, `update_event`, `delete_event`, `clean_html_description`, and CLI commands) with UTF-8 Windows terminal support.
- Added agentic shared LangChain `@tool` wrappers in `src/nexus/shared_tools/shared.py` (`get_calendar_schedule`, `create_calendar_event`, `update_calendar_event`).
- Documented `calendar_engine.py` in `README.md` under Deterministic Tools.
- Standardized first-class `Events/` directory (`<Section>/Events/YYYY/`) for Tier 4 Episodic Memory across all universal section sub-brains, housing discrete historical records (`YYYY-MM-DD - <Topic>.md`: networking exchanges, screens, interviews, agent sessions).
- Added Rule 12 (`Zero Sycophancy & Grounded Reality`) and `.agents/rules/zero_sycophancy.md` enforcing absolute anti-sycophancy and fact-grounded communication across all agent interactions.

### Changed
- Refactored `Protocol - Career Maintenance.md` cadences to natively trigger the `Employer Skill Requirements.md` document playbook rather than duplicating logic.
- Extended `src/nexus/core/google_auth.py` with `token_filename` parameter to enable isolated OAuth tokens per service (`token_calendar.json` vs `token.json`).
- Updated AGENTS.md, README.md, and Glossary to reference the new Concept - The Nexus Execution Lifecycle SSOT, removing duplicated anatomy schemas and formalizing the Operational vs. Conceptual section classification rule.
- Refactor and condense Section 6.2 (`Library & Learning`) from 14 sprawling academic sub-sections into a focused 4-part AI Engineering Core (`6.2.1. Intelligent Agents & Autonomy`, `6.2.2. Language Models & Production RAG`, `6.2.3. Programming & Software Engineering`, `6.2.4. Data Engineering & MLOps`).
- Consolidate foundational mathematics, classical machine learning, deep learning theory, and biomedical AI into `Technical Reference Archive.md` (MOC) under `Archive/`, eliminating 166 lines of syllabus clutter from `Table of Contents.md` while preserving 100% of user notes. Prune 6 empty stub directories.
- Moved the engine constitution to `src/nexus/core/ENGINE_CONSTITUTION.md`, loaded by `engine_constitution.py`, so internal agents and IDE agents (Resident + Builder) read one shared rule file. Slimmed AGENTS.md to a boot sequence plus Builder coding standards. The resident behaviors (life archiving, flush trigger, Document Playbooks, grounding) moved into the constitution, and the section anatomy now points to the Execution Lifecycle SSOT (Operational vs. Conceptual).
- Decoupled Cold Storage (`<Section>/Archive/`) from Episodic Neocortex (`<Section>/Events/`), clarifying `Archive/` strictly as cold storage for retired Tier 3 Living State (superseded documents, completed projects, closed CRM contacts) rather than burying active life history.
- Migrated legacy `Archive/Conversations/` to `Events/2026/` across `3.1. Career Strategy & Revenue`, `6. Forge`, and `2. Health/2.3. Psych`.
- Updated engine specifications, section building protocols, and agent instructions in `AGENTS.md`, `src/nexus/core/engine_constitution.py`, `Project - Nexus Agentic Engine.md`, and `Glossary - Nexus Engine Terminology.md`.
- Reworded AGENTS.md standards 2 and 19 and the README headline to mark the SubagentFactory and Cognitive Inheritance as planned architecture, since `src/nexus/` has no agent-spawning tooling and all agents are hardcoded LangGraph graphs.
- Moved the documented location of Section 1.1 daily execution logs from `Archive/YYYY/MM/` to `Events/YYYY/` (AGENTS.md standard 20, Table of Contents) for consistency with the universal section anatomy.
- Executed top-level Vault taxonomy refactor to establish single-word, sovereign life domains:
  - `1. The Core` $\to$ `1. Core`
  - `3. Operations & Wealth` $\to$ `3. Operations`
  - `4. Playground` $\to$ `4. Life`
  - `5. Capture & Archive` $\to$ `5. Reference`
  - `6. Forge` $\to$ `6. Engineering`
- Cleaned Vault root: moved loose `0. Quick Capture.md` into `0. Inbox/`, loose psychology guide into `2. Health/2.3. Psych/`, `Movies/` into `4. Life/4.3. Culture & Inspiration/`, and `Project Helix Instructions/` into `6. Engineering/6.1. Projects/`.
- Updated `Table of Contents.md` section headers and deprecated fragile `obsidian://search` URI links in favor of clean, sovereign Markdown structure.
- Updated path references across all engine agents (`src/nexus/agents/career/`), resume engines (`render.js`, `render_docx.py`, `inspect_docx.js`), maintenance scripts (`scripts/audit_career_drift.py`), `.agents/skills/`, and `.agents/workflows/`.
- Updated `AGENTS.md` and `README.md` to reflect the new taxonomy.

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
