# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [2.4.0] - 2026-06-04

### Changed
- Add real-time console tracing to all agents (Router, Career, Librarian, Email) via new `core/trace.py` AgentTracer. Replace interactive 1/2/3 menu in `main.py` with a persistent chat REPL that never clears the console.
- Refactored entire agent swarm architecture (Router, Email, Career, Librarian) into modular `api.py`, `graph.py`, `tools.py` structure.
- Globalized pure Python vault filesystem I/O operations into `engine/shared_tools/vault_reader.py`.
- Extracted shared cross-agent @tool wrappers (e.g. `ask_librarian_escalation`, `propose_write`) into `engine/shared_tools/shared.py`.
- Updated all API routes and CLI tools to consume agents strictly via their public `api.py` boundaries.
- Refactor career agent to move tools from `agent.py` to a dedicated `tools.py` file, matching other agents' structure and improving separation of concerns.
- Updated `generate_obsidian_note` and `project_work` skills to enforce the new canonical project template structure (Overview, Current State, Architecture, Standing Guidelines, Build Log, Roadmap).

### Removed
- Deleted legacy monolithic `engine/tools/vault_tools.py` and `engine/tools/` directory.

## [2.3.0] - 2026-06-01

### Added
- Created the **Email Agent** compiled LangGraph subgraph under `engine/agents/email/` to fetch and search IMAP emails.
- Added `search_emails` tool to `engine/agents/email/tools.py`.
- Established the Email Agent Golden Dataset evaluation suite in `engine/agents/email/evals/`.
- Added 5 new evaluation cases to the Career Agent dataset in `engine/agents/career/evals/dataset.json`.
- Created decentralized `evals` framework for the Content Router and Career Agent.
- Added `dataset.json` and `runner.py` to `engine/agents/router/evals/` and `engine/agents/career/evals/`.
- Configured LangSmith tracing inside `.env`.
- Added high-resolution PNG and Windows multi-resolution ICO icon assets for the sync-vault shortcut button inside the GUI's public directory.
- Installed `pillow` Python package in the project environment for image manipulation.
- `get_master_resume()` tool for the Career Agent — reads `Resume - Master.md` for resume tailoring workflows.
- Resume Tailoring Protocol in the Career Agent system prompt — agent reads master resume, crafts tailored version, and proposes via HITL.
- `run_career_agent_with_trace()` API — returns tool call metadata alongside agent response for eval observability.
- Known Cross-Domain File Paths section in the Career Agent prompt — provides exact vault paths for files outside the career domain (Current Learning, To Do List).

### Changed
- Migrated `engine/tools/email_tool.py` to `engine/agents/email/tools.py`.
- Refactored **Content Router** (`engine/agents/router/agent.py`) into a ReAct agent to support `fetch_emails` tool calling prior to classification.
- Updated `tools/read_email.py` to import from the new agent tools module.
- Hardened Career Agent HITL compliance via mandatory trigger rules in the system prompt (interview status changes, learning completions, skill acquisitions, job applications).
- Upgraded eval runner grader to use actual tool call traces instead of inferring HITL compliance from response prose.
- Renamed "Vault Explorer" to "Brain Explorer" in the GUI Sidebar navigation and Vault page component.
- Unified Nexus entry points (`engine/main.py` and `engine/interfaces/telegram.py`) to use the Content Router (`route_content`) instead of the Librarian directly.
- Updated the Content Router's fallback logic to escalate general knowledge queries to the Librarian Agent rather than returning a placeholder.
- Added `filters` support to the Router to propagate CLI tags/domains to the Librarian subgraph.
- Updated `README.md` Repository Structure to include `capture_content.md`.
- Added `release.py` to the Deterministic Tools table in `README.md`.

### Fixed
- Career Agent HITL compliance: pass rate improved from 33% (1/3) to 100% (3/3), avg score from 5.0 to 8.0.
- Career Agent failing to call `propose_write` for cross-domain files (e.g., `Current Learning.md`) because it couldn't see them in its domain listing.
- Fixed a `UnicodeEncodeError` on Windows consoles by forcing `sys.stdout` to UTF-8 in `engine/main.py`.

## [2.2.0] - 2026-05-28

### Added
- **Changeset Release Compilation System (Agent Context Optimization - Phase 1):**
  - Created `.changeset/` staging directory with `.gitkeep` for storing fragmented change notes.
  - Implemented `tools/release.py` Python compiler script to parse changeset fragments, determine semantic version bumps, update `CHANGELOG.md` and keep a rolling 3-release window in `CHANGELOG-RECENT.md`, and clean up staging.
  - Created `CHANGELOG-RECENT.md` as a low-token active context file for developer agents.

### Changed
- **Changelog Policies & Skills:**
  - Updated `maintain_project_docs` skill (`.agents/skills/maintain_project_docs/SKILL.md`) to instruct agents to write to `.changeset/` instead of directly modifying `CHANGELOG.md`.
  - Updated `AGENTS.md` Git & Changelog Policy rules to mandate changesets for engine changes.
  - Checked off Phase 1 tasks in the `Project - Agent Context Optimization & Changeset Automation.md` project log.
  - **Conversation Logging Optimization:**
  - Updated `log_llm_conversation` skill instructions to prepend entries at the top of `Log - LLM Conversations.md` instead of appending them at the bottom.
  - Re-ordered `Log - LLM Conversations.md` to place newer entries first, enabling future agents to verify duplicates by reading only the first 20 lines of the file.
