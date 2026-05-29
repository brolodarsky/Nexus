# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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

## [2.1.0] - 2026-05-28

### Added
- **Multi-Agent Pipeline (Content Router → Career Agent → Librarian):**
  - **Content Router Agent (`engine/agents/router/`):** LangGraph-based classifier that categorizes incoming content into domain categories (career, health, general) via structured JSON output and routes to the appropriate domain agent using conditional edges. Includes fallback handling for unparseable LLM responses.
  - **Career Agent (`engine/agents/career/`):** Domain-specialized LangGraph ReAct agent for job analysis, skill gap detection, and career strategy. Implements the **Deterministic Pre-flight Hydration (DPFH)** pattern — before each LLM invocation, a pure-Python orchestration node reads the career domain file listing (`os.listdir`), `My Skills.md`, and `Employer Skill Requirements.md` and injects them into the system prompt at zero LLM cost. Includes domain-scoped `search_career_domain` tool, `ask_librarian` escalation tool for cross-domain queries, and `propose_write` tool that submits modifications to the existing HITL transaction queue for human approval.
  - **Librarian Integration:** The existing Librarian Agent (`engine/agents/librarian/`) now serves as the cross-domain search escalation service, callable as a tool by the Career Agent for queries outside its domain folder.
  - **End-to-End Orchestration:** The Router's `career_agent` node invokes the real Career Agent subgraph (replacing the Step 1 placeholder), enabling a full pipeline: raw content → classification → domain-specific analysis with live vault context → optional cross-domain retrieval → structured response.
- **Direct Execution Fix:** Added `sys.path` bootstrapping to both `router/agent.py` and `career/agent.py` so they can be run directly from the project root (`python engine/agents/router/agent.py`) without `ModuleNotFoundError`.
- **Vault Explorer & Podcast Studio:**
  - Implemented `gui/src/app/vault/page.tsx` offering a dual-pane layout with an interactive tree browser and markdown preview.
  - Added visual badges (`🎧`) to markdown files indicating ready-to-play generated audio.
  - Created a 1-click generation Podcast Studio in the frontend with a dark-mode friendly HTML5 audio player for in-browser playback.
- **Podcast Vault Endpoints:** Added `/api/vault/list`, `/api/vault/podcast/generate`, and `/api/vault/podcast/download` endpoints to the FastAPI backend to safely bridge the GUI to the local filesystem.
- **Typed API Client (`gui/src/lib/api.ts`):** Added `VaultEntry` interfaces and methods for the new Vault endpoints.

### Changed
- **Podcast Generation Tool (`tools/generate_podcast.py`):**
  - Refactored to save generated `.mp3` files directly alongside the source `.md` files instead of a central `Audio/` folder.
  - Migrated history tracking to `.podcast_history.json`.
  - Fixed Windows CLI character limits and `edge-tts.exe` crashes by writing text to a temporary file and invoking `python -m edge_tts --file`.
- **Developer Agent Constitution Refactor (`AGENTS.md`):**
  - Slimmed down `AGENTS.md` by >70%, removing redundant verbatim listings of skills, workflows, and tools that are already managed by the platform or documented in `README.md`.
  - Added explicit Meta-Boundary guidelines separating the external Developer Agent from the internal Nexus Agentic Engine.
  - Added explicit authorization for developer agents to read and use `Vault/` files for personal domain context and run `tools/` and `engine/` scripts.
  - Summarized the 4 core engine architectural principles (Agentic File System, Folder-Mapped Swarm, Pre-flight Hydration, and HITL Queue) that developer agents must respect when editing engine code.
  - Simplified the `maintain_project_docs` skill rules to remove the obsolete "Compiler Pattern" for auto-generating `AGENTS.md`.


