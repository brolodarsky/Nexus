# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.16.0] - 2026-05-19

### Added
- **New Tool: Phone Chat Ingestion (`ingest_phone.py`):** Universal ADB screen-scraper that captures conversations from any Android app (Google Messages, Tinder, Hinge, WhatsApp, Signal, Bumble, etc.) via `uiautomator dump` and saves structured Markdown notes to `Vault/0. Inbox/`. Features include: auto-scroll to bottom before capture, multi-screen scroll with deduplication, contact name detection from toolbar, sender alignment detection (me vs them), and timestamp divider rendering. Zero dependencies (pure stdlib), zero third-party phone apps required — only USB Debugging.
- **New Skill: Project Work (`project_work`):** Enforces keeping active project notes in the vault up-to-date automatically whenever task lists are completed/modified or conceptual project plans change.


### Fixed
- **Phone Chat Ingestion (`ingest_phone.py`):** Increased empty screen tolerance from 1 to 3 consecutive screens. This prevents the scraper from prematurely terminating when encountering long voice notes or large emoji reactions that register as zero text nodes in the UI hierarchy.

### Changed
- **Analyze Health & Analyze Psych Skills:** Updated `analyze_health` and `analyze_psych` skills to mandate safely caveated, probabilistic language when discussing medical symptoms, diagnoses, or physiological mechanisms (e.g., using "may be a cause" instead of absolute declarations). Updated their descriptions in `AGENTS.md` to reflect this tone adjustment.

## [1.15.1] - 2026-05-16

### Added
- **Structured Run Logs for Librarian:** Implemented a lightweight, append-only JSONL run logger (`engine/logs/run_logs.jsonl`) that captures execution details for every vault reader query (CLI, interactive, voice, Telegram, and evals). Logs include ISO timestamp, raw query, execution status, deduplicated cited sources (extracted from tool calls and final text), errors, and sequential tool calls with arguments.

### Changed
- **Local-First Security Ignore Rules:** Updated `.gitignore` to explicitly exclude `engine/logs/` from version control, preserving the local-only nature of the user's private query history and thoughts.

## [1.15.0] - 2026-05-15

### Added
- **Shared Google Auth Module:** Created `engine/core/google_auth.py` to centralize OAuth2 handling (refreshing, token management, and browser-based auth) for all Google-integrated tools.
- **Agentic Email Tool:** Created `engine/tools/email_tool.py` containing the core IMAP and MIME parsing logic, allowing the AI Agent to import email capabilities directly.

### Fixed
- **Email Tool Imports:** Resolved a `ModuleNotFoundError` where `engine/tools/email_tool.py` could not locate the `core` package when imported from the project root. Improved path injection robustness for standalone tool execution.

### Changed
- **Email Tool Refactor:** Modularized `tools/read_email.py` into a thin CLI wrapper. It now imports its core logic from the engine and stores credentials in a dedicated, gitignored `tools/.secrets/` folder.
- **Improved Security:** Updated `.gitignore` to protect the new `tools/.secrets/` directory and transitioned to the standard `https://mail.google.com/` OAuth scope for more reliable IMAP access.

## [1.14.1] - 2026-05-14

### Added
- **New Tool: Email Reader:** Created `tools/read_email.py`, a lightweight IMAP email reader analogous to `read_webpage.py`. Fetches a single email by UID and outputs clean markdown (subject, from, date, body). Supports Gmail App Passwords via env vars (`EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `IMAP_SERVER`). Includes a `--list-recent N` flag for browsing the inbox before fetching. No external deps beyond stdlib; `python-dotenv` used optionally for `.env` loading.
- **New Tool: Webpage Reader:** Created `tools/read_webpage.py`, a lightweight, deterministic webpage scraper using `trafilatura`. Designed to provide clean markdown content for the Brain 2 Agentic Engine's content ingestion and career search pipelines.
- **Librarian Eval Framework:** Created `engine/evals/dataset.json` (Golden Dataset) with 12 real-world Q&A cases and `engine/evals/runner.py` for automated agent benchmarking and groundedness grading.
- **Dependency Update:** Added `python-dotenv`, `trafilatura`, and `lxml_html_clean` to the project environment and updated `requirements.txt`.

### Changed
- **Agentic Instructions Enhancement:** Updated `generate_obsidian_note` skill to mandate a `list_dir` pattern check before proposing filenames to prevent hallucinated prefixes. Added physical folder structure priority rules to resolve discrepancies with logical nesting in `Table of Contents.md`. Added mandatory **Localized Synthesis Check** rule instructing agents to scan target folders for local synthesis/hub notes and integrate external article findings into them.
- **Workflow Chaining & Synthesis:** Updated `/audit_inbox` workflow to actively identify and chain specialized downstream workflows (e.g., `/add_job_requirement`, `/ingest_medical_record`, `/distill_learning`), and enforce Localized Synthesis Integration Checks when filing articles or external research.
- **Resume Engine Refactor:** `render.js` now scans `3.1. Career Strategy & Revenue` and `3.1.3. Professional Portfolio & Evidence` for renderable markdown documents (resumes, cover letters, docs) and presents an interactive selection menu. Supports rendering one, multiple, or all documents in a single pass. Also accepts a CLI path argument for scripted/workflow use.
- **DOCX Renderer:** `render_docx.py` now accepts an optional file path argument instead of hardcoding `Resume - Master.md`. Falls back to Master Resume when no argument is given.
- **Obsidian Cleanup:** Both renderers now strip YAML frontmatter and Obsidian navigation links (`Back to:` lines) before rendering to PDF/DOCX.
- **Workflow Integration:** Integrated `read_webpage.py` into `/capture_content`, `/distill_learning`, and `/add_job_requirement` workflows to ensure clean, boilerplate-free text extraction from URLs.
- **Workflow Update:** Updated `/render_resume` workflow to reflect the new interactive document picker and non-interactive CLI mode.
- **Portfolio Restructure:** Created `Resumes/` and `Cover Letters/` subfolders inside `3.1.3. Professional Portfolio & Evidence`. Moved all resume and cover letter files (md, pdf, docx) into their respective folders. Updated `Table of Contents.md`, `render.js`, and `render_docx.py` scan paths accordingly.

---

## [1.14.0] - 2026-05-07

### Added
- **Nested Heart Architecture (Item 23):** Created a private Git repository inside `Vault/` to track personal history without polluting the public engine repository.
- **Nested Heart Tool:** Added `tools/sync_vault.py` to automate the context-switch required to commit to the nested Vault repository.
- Created `Project - Librarian Agent.md` to chart the new Agentic File System (AFS) Navigator architecture, replacing standard ChromaDB RAG.
- **Librarian Agent Implementation:** Built `engine/tools/vault_tools.py` (`read_toc`, `read_note`, `search_vault`) and the LangGraph ReAct agent (`engine/agents/librarian/agent.py`) to actively navigate the local filesystem.

### Changed
- **Agent Rules:** Added Rule 11 to `AGENTS.md` explicitly instructing agents to ignore the `Vault/.git` directory.
- Pivoted `/ask_brain` architecture from Vector RAG to Agentic Librarian to solve Context Fragmentation and preserve Zettelkasten hierarchy.
- Archived `engine/agents/rag/` into `Vault/6. Forge/6.1. Projects/6.1.4. Script Attic/Legacy RAG Engine/`.
- Updated `Project - Brain 2 Agentic Engine.md`, `Table of Contents.md`, and `To Do List.md` to reflect the pivot.
- Updated `engine/main.py` dispatcher to point to the new Librarian agent for CLI text queries.
- Updated `ask_brain` workflow documentation in `AGENTS.md` and `README.md` to reflect removal of vector indexing requirement.
- **Presentation Layer Centralization:** Refactored `engine/main.py` to be the sole presentation layer (using a new `print_agent_response` helper). Stripped execution and printing logic from `engine/interfaces/cli.py` and `engine/interfaces/voice.py`, turning them into pure input parsers (`parse_cli_args`, `capture_voice_query`).

### Removed
- Uninstalled `chromadb` and deleted `.chroma_db/` index and `.rag_index_manifest.json` as part of the pivot.
- Removed `engine/agents/rag/ingest_vault.py` and `engine/agents/rag/eval_rag.py` from tool index.

## [1.13.0] - 2026-05-07

### Added
- **Engine Coordinator Mode:** Upgraded `engine/main.py` from a one-off dispatcher to a persistent "Mission Control" coordinator.
  - Launches the Telegram Bot in a background thread by default for "always-on" remote access.
  - Implements an interactive CLI menu with numbered options for Text Query, Voice Query, Ingestion, and Maintenance.
- **Shared Audio Utility:** Created `engine/core/audio.py` to centralize Whisper transcription logic.

### Changed
- **Interface Refactor:** Updated `engine/interfaces/voice.py` (Local) and `engine/interfaces/telegram.py` (Remote) to use the new shared `transcribe_audio` service, eliminating redundant transcription code.
- **Improved CLI UX:** Suppressed verbose library logs (`httpx`, `telegram`) to keep the Mission Control interface clean and focused.

## [1.12.1] - 2026-05-07

### Added
- **Unified Engine Dispatcher:** Refactored `engine/main.py` into a central dispatcher that handles CLI, Voice, Telegram, and Ingestion via flags (`--voice`, `--telegram`, `--ingest`).
- **Engine Interfaces Layer:** Created `engine/interfaces/` to isolate entry-point logic (`cli.py`, `voice.py`, `telegram.py`) from core agent logic.
- **PowerShell Command Sync:** Added `brain-telegram` function and updated `ask-brain`, `brain-voice`, and `ingest-vault` in the Windows PowerShell profile to use the unified `main.py` entry point.

### Changed
- **Architectural Cleanup:** Deleted redundant root-level wrappers (`engine/ask_brain.py`, `engine/brain_voice.py`, `engine/brain_telegram.py`) in favor of the unified dispatcher.
- **Agent Modularity:** Moved `execute_rag_query` and `ask_librarian` from `engine/main.py` to `engine/agents/rag/agent.py`.
- **Ingestion Refinement:** Updated `engine/agents/rag/ingest_vault.py` with a proper `main()` entry point and fixed internal module pathing for the new architecture.

### Fixed
- Corrected a module import shadowing issue in `ingest_vault.py` by using absolute package imports for RAG tools.

## [1.12.0] - 2026-05-07

### Added
- **Incremental Indexing (Phase 8):** `engine/ingest_vault.py` now tracks file modification times via a JSON manifest (`.rag_index_manifest.json`) and only re-embeds files that have changed since the last run. Added `--force` flag for full re-indexing.
- **Orphan Cleanup (Phase 8):** After each ingestion run, the system queries ChromaDB for entries whose source files no longer exist on disk and purges them automatically.
- **Frontmatter Metadata Extraction (Phase 8):** Ingestion now parses YAML frontmatter (`tags`, `type`) and derives a `domain` category (health, career, tech, etc.) stored as ChromaDB filterable metadata on every chunk.
- **Filtered Search (Phase 8):** `engine/main.py` now accepts `--domain`, `--tag`, and `--type` CLI flags that generate ChromaDB `where` clauses to constrain retrieval by metadata.
- **Schema Foresight Audit (Phase 8):** Documented current metadata distribution (1,577 chunks, 60% domain-tagged) and evaluated future fields (`word_count`, `date_created`, `confidence`) with accept/defer/reject decisions.
- **Phase 8.5 Tech Debt Tracked:** Flagged that ~60% of `engine/core/` and `engine/tools/` is RAG-specific code that should be scoped to `engine/agents/rag/` before building domain agent #2.
- **RAG Module Consolidation:** Moved RAG-specific utilities (`ingest_vault.py`, `eval_rag.py`, `eval_dataset.json`) from `engine/` root to `engine/agents/rag/` to ensure a clean boundary between the dispatcher and domain-specific RAG logic. Updated all internal paths and added `sys.path` bootstrapping to maintain CLI script functionality.

### Changed
- Replaced raw `sys.argv` parsing in `engine/main.py` with `argparse` for structured CLI flag support.
- Moved index manifest logic to `engine/agents/rag/index_manifest.py` (RAG-scoped, not shared core).
- **Module Ownership Cleanup (Phase 8.5):** Refactored the engine's internal structure to improve modularity and prepare for multi-agent support.
  - Moved RAG-specific constants from `engine/core/constants.py` to `engine/agents/rag/constants.py`.
  - Moved `AgentState` from `engine/core/state.py` to `engine/agents/rag/state.py`.
  - Relocated RAG-specific tools (`chroma_tool.py`, `text_utils.py`) from `engine/tools/` to `engine/agents/rag/tools/`.
  - Updated all internal imports across the engine (`main.py`, `ingest_vault.py`, `nodes.py`, `graph.py`, `eval_rag.py`) to reflect the new scoped architecture.

---

## [1.11.4] - 2026-05-06

### Added
- **Domain-specific Sources Architecture:** Created `Sources/` subfolders in all 14 subsections of `6.2. Library & Learning` to separate raw captures from synthesized concept notes.

### Changed
- **Library Organization:** Relocated technical articles (IBM Granite, VALID Framework, TRIBE v2) from domain roots into specialized `Sources/` subfolders.
- **TOC Refinement:** Standardized the Table of Contents with `📁 Sources` headers for all technical domains.
- **Workflow Refinement:** Updated `/audit_inbox` to avoid adding granular inbox items directly to the Table of Contents and to use existing hubs, MOCs, project notes, logs, or folders for routine filing.
- **Documentation Sync:** Refreshed `/audit_inbox` descriptions in `AGENTS.md` and `README.md` to reference the current Brain Inbox and Quick Capture paths.

---

## [1.11.3] - 2026-05-06

### Added
- **Telegram Bot Integration:** Created `engine/brain_telegram.py` to provide a remote, smartphone-friendly interface to the RAG Agent.
- **Voice-first RAG Query:** Implemented `engine/brain_voice.py` to capture microphone input via OpenAI Whisper.
- **Enhanced YouTube Transcripts:** Updated `tools/youtube_transcript.py` to save Obsidian-ready markdown notes directly to `Vault/Inbox` with YAML frontmatter and video title fetching.
- **Workflow Refinement:** Updated `/distill_learning` to include a mandatory redundancy check, prioritizing the augmentation of existing notes over creating duplicates.

### Changed
- **Architectural Refactor:** Extracted core LangGraph execution into `execute_rag_query` in `engine/main.py` to unify the RAG pipeline across CLI, Voice, and Telegram interfaces.
- **Podcast Generation Tool:** Refactored `tools/generate_podcast.py` to process a single markdown file specified via command-line argument instead of scanning the entire Vault. Added a `--force` flag to bypass modification time checks.
- **Telegram UX Refinement:** Removed source citations from Telegram responses to optimize for mobile display and avoid broken `obsidian://` deep links on mobile clients.
- **Voice Note Support:** Added secure `.ogg` voice note transcription for the Telegram bot, bridging the Phase 6A Whisper logic to mobile.
- **RAG Retrieval Quality Enhancements (Phase 7):**
  - **Eval Framework:** Created `engine/eval_rag.py` using an LLM-as-a-judge approach and `engine/eval_dataset.json` to systematically test the agent's accuracy against a golden dataset.
  - **Similarity Threshold:** Added a cosine distance filter (`SIMILARITY_THRESHOLD = 0.7`) to drop low-quality retrieval chunks before they pollute the context window.
  - **HyDE (Hypothetical Document Embedding):** Modified the `retrieve` node in `engine/agents/rag/nodes.py` to generate a hypothetical perfect answer using GPT-4o before vector search, bridging the vocabulary gap between short user queries and dense markdown notes.
  - **LLM Re-Ranking:** Added an LLM-based re-ranker step to score and sort the top retrieved chunks from ChromaDB, drastically improving the signal-to-noise ratio.


## [1.11.2] - 2026-05-05

### Changed
- **RAG Engine Modularization:** Completed the architectural refactor of the RAG system from flat scripts into a scalable, modular engine:
  - `engine/core/`: Shared constants and state definitions.
  - `engine/agents/rag/`: Isolated RAG nodes and LangGraph definitions.
  - `engine/tools/`: Atomic utilities for ChromaDB, text splitting, and vault crawling.
  - `engine/main.py`: New universal dispatcher for multi-agent support.

### Fixed
- **RAG Engine:** Corrected import path errors in modularized components to ensure reliable execution from the project root.

---

## [1.11.1] - 2026-05-04

### Changed
- **Resume Engine:** Integrated `tools/resume_engine/render_docx.py` into `render.js`. Running the Node.js renderer now automatically triggers the Python DOCX renderer using the project's virtual environment, ensuring both PDF and DOCX formats are generated in a single pass.
- **Workflow:** Updated `/render_resume` to consolidate PDF and DOCX rendering into a single step, reflecting the tool integration.

---

## [1.11.0] - 2026-04-28

### Added
- Created the `archive_project` agentic skill to systematically manage and archive completed projects while maintaining contextual Vault architecture.

### Changed
- Executed **Radical Transparency Public Release Strategy**:
  - Restructured `.gitignore` to use a robust wildcard approach (`Vault/**`) to untrack all vault content files while retaining folder structure and `.gitkeep` files.
  - Added `.gitattributes` rule to explicitly exempt `Vault/Table of Contents.md` from `git-crypt` encryption, establishing it as the public-facing cognitive map.
  - Untracked 200+ personal vault files from the repository via `git rm --cached` while preserving local copies.
  - Rewrote `README.md` to articulate the "Human Context Statement" and document architectural methods (Engine/Vault separation, Agentic Config mirror).
  - Verified `AGENTS.md` as public-facing agentic constitution.
  - Formally licensed the repository under AGPL-3.0.

---

## [1.10.2] - 2026-04-27

### Added
- Added `ipython` and `langchain-tavily` to `requirements.txt` for agent development and updated Tavily integration.

---

## [1.10.1] - 2026-04-23

### Changed
- **Resume Engine:** Updated `render.js` to automatically save a copy of the generated PDF to the user's `Downloads` folder for easier access.
- **Generalization:** Removed hardcoded names from the resume engine and workflow. The output PDF filename is now dynamically extracted from the first H1 header in the Markdown source.

---

## [1.10.0] - 2026-04-22

### Added
- **Career Counselor Skill:** Implemented `career_counselor` agentic skill to act as a high-stakes career architect.
  - Mandates synthesis of three pillars: Career Strategy (3.1), Technical Evidence (6.1), and Cognitive Architecture (2.3).
  - Integrated `search_web` for real-time market alignment and compensation benchmarking.
  - Enforces non-sycophantic, analytical advice grounded in the "AI Superagency" and "Proof of Work" frameworks.

---

## [1.9.0] - 2026-04-21

### Added
- **RAG Engine Integration:** Implemented a Retrieval-Augmented Generation (RAG) system for semantic search across the entire Vault.
  - Added `engine/ingest_vault.py` for indexing markdown notes into a local ChromaDB vector store.
  - Added `engine/ask_brain.py` as a RAG query agent to provide grounded answers with citations.
  - Added `/ask_brain` agentic workflow to allow natural language vault queries via slash command.

---

## [1.8.4] - 2026-04-16

### Added
- **LangGraph Integration:** Formally integrated `langgraph` and `langchain-openai` into the development stack to start development of AI agent orchestration.
- **Vault Restructure:** Created new `6.2.12. AI for Science & Healthcare` section to un-clutter Agent frameworks. Shifted `Robotics` (now 6.2.13) and `AI Ethics` (now 6.2.14) down.

### Changed
- **Environment Management:** Updated `requirements.txt` with new dependencies for stateful agent development.
- **Hygiene:** Verified global Python 3.12 install remains pristine (pip-only) while project environment manages 60+ specialized libraries.

---

## [1.8.3] - 2026-04-14

### Changed
- Upgraded `analyze_health` skill (Step 9 & 10: Update the Vault) to explicitly mandate active narrative restructuring and visual re-weighting of `Health Summary.md`. Added strict requirements for table hygiene (re-sorting, consolidation) and mandatory syncing of medical action items to the master `To Do List.md`.

---

## [1.8.2] - 2026-04-13

### Changed
- Promoted **Career Strategy & Revenue** from `3.3` to `3.1` to align with priority and daily usage.
- Re-ordered Section 3 (Operations & Wealth) folders: Wealth & Asset Management shifted to `3.2`, Infrastructure & Logistics shifted to `3.3`.
- Updated `Table of Contents.md` and `README.md` to map to the new hierarchy.
- **Fixed:** Reconstructed broken `.venv` configuration caused by absolute path fragmentation (moved from `Knowledge Base`).
- **Added:** Integrated `openai`, `langgraph`, `httpx`, and `python-dotenv` into `requirements.txt` for agentic development.
- **Added:** Created `sandbox_langgraph.py` in `Vault/6. Forge/6.1. Projects/6.1.2. Agentic R&D/` for isolated state machine testing.

---

## [1.8.1] - 2026-04-12

### Added
- In `generate_obsidian_note` skill (Formatting and Structure section), mandated the use of synchronized horizontal navigation bars for "tight clusters" of notes (e.g., Auto, Health, Career) to allow lateral movement between related Map of Content (MOC) notes.

### Changed
- Refactored **Rules 4 & 5** in `AGENTS.md` into a single unified **Git & Changelog Policy** with a structured decision table to eliminate model ambiguity at rule execution time. Previously, two prose rules with overlapping scope caused false-positive commits for routine note/TOC-link additions.
- Implemented **Compiled Portability Architecture** across core skills:
  - Added strict Compiler Rules to `maintain_project_docs` to force verbatim YAML transcription into `AGENTS.md` to prevent context drift.
  - Refactored `skill_creator` and `workflow_creator` to delegate `AGENTS.md` updates to `maintain_project_docs`.
  - Wrapped `AGENTS.md` lists in strict `<!-- AUTO-COMPILED -->` warnings to preserve system portability.
  
---

## [1.8.0] - 2026-04-11

### Changed
- Executed **Vault Structural Refactor & Friction Reduction** (Roadmap Item #5):
  - Moved **`Inbox/`** and **`Quick Capture.md`** out of deep nesting into the Vault root (`0. Inbox/`, `0. Quick Capture.md`) to eliminate capture friction.
  - Re-allocated **`Memories`** and Journaling into **`1.1. Philosophy & Personal North Star / Personal Logs`**, rather than creating an unnecessary extra section format.
  - Split Personal Logs into `Daily Notes (Journal)` for stream-of-consciousness, and `Memories/` for curated milestones and Trophy Case.
  - Renamed `5. Capture & Archive` subsections to reflect the removal of the Brain Dump.
- Updated `audit_inbox` and `capture_content` workflows to use the new zero-friction paths.
- Updated `Table of Contents.md` and `README.md` to reflect the new architecture.

---

## [1.7.0] - 2026-04-11

### Added
- Created new educational sections in **6.2 Library & Learning**:
  - **6.2.3. Algorithms & Data Structures**: Core CS fundamentals for technical depth and interview preparation.
  - **6.2.4. System Design & Distributed Systems**: Architectural principles for scaling complex systems.
  - **6.2.11. Knowledge Graphs & GraphRAG**: Integrated graph theory and applied graph-based retrieval into the NLP and Math domains.
- Added boilerplate study frameworks for all new sections to facilitate future knowledge synthesis.
- Added `.gitkeep` to new empty folders to ensure structural tracking in Git.

### Changed
- Re-architected Section **6.2 Library & Learning** for optimal pedagogical flow:
  - Moved **Data Engineering (6.2.5)** before Machine Learning to treat it as a prerequisite.
  - Grouped all Deep Learning application domains (NLP, Computer Vision, Reinforcement Learning) into a continuous sequence (6.2.8 - 6.2.10).
  - Promoted **Intelligent Agents (6.2.11)** as the culmination of the Deep Learning sequence.
- Renamed the master index alias from "Table of Contents" to include "Map of Content" (MOC) to reflect the Zettelkasten organizational paradigm.
- Updated `README.md` directory tree to reflect the deep restructure of the Forge.

---

## [1.6.2] - 2026-04-07

### Added
- Created new Vault section **2.5. Mom's Health Tracking** in the TOC and filesystem.
- Implemented **Mom's Health Summary** dashboard for centralized symptom, medication, and visit tracking.
- Created `Mom_Health_Logs` and `Mom_Lab_Work` folder structure for clinical record organization.
- Added `2.5. Mom's Health Tracking/` to the `README.md` directory tree.
- Created `tools/medical_xml_parser.py` script to parse complex HL7 CDA medical XML files into structured Markdown.
- Added `/ingest_medical_record` workflow to automate standardizing and importing raw patient records.

### Changed
- Upgraded `analyze_health` skill to optionally integrate checking Section 2.2 Medical insurance coverage documents for realistic financial/logistical medical planning.
- Standardized `analyze_health` skill to support multi-profile diagnostics (handling multiple health summaries like Mom's vs. Primary) via patient-context switching.

## [1.6.1] - 2026-04-05

### Changed
- Upgraded `analyze_health` skill with mandatory `search_web` step before forming any diagnostic hypothesis or treatment recommendation:
  - Open-ended recency queries (no year pinning — uses "latest", "current guidelines" language)
  - Evidence quality hierarchy: meta-analyses > RCTs > guidelines > case reports
  - Explicit instruction to surface conflicting evidence rather than defaulting to most recent
- Upgraded `analyze_psych` skill with the same web research step:
  - Open-ended recency queries; vigilance flags for psychedelic-assisted therapy, sleep science, neuroinflammation, gut-brain axis
  - Same evidence quality hierarchy and conflict-surfacing rule
- Added mandatory **Source Citation** rule (step 7) to both `analyze_health` and `analyze_psych` skills:
  - Preferred source hierarchy defined per skill (PubMed/NCBI, Cochrane, domain-specific clinical guidelines, Mayo Clinic, Cleveland Clinic, JAMA/NEJM/Lancet, NIH)
  - Blocklist: wellness blogs, product sites, Reddit, non-peer-reviewed sources
  - Mandatory inline markdown link format beside each claim
  - Fallback: cite institution + document name if direct URL unavailable
  - Links must be written into Vault note updates for persistent reference

## [1.6.0] - 2026-04-05

### Added
- New meta-skill `skill_creator` — moved from `Vault/SKILL.md` into `.agents/skills/skill_creator/SKILL.md`. Covers full skill anatomy, progressive disclosure, writing patterns, and eval guidance.
- New meta-skill `workflow_creator` — `.agents/skills/workflow_creator/SKILL.md`. Covers workflow anatomy, format rules, overlap resolution, sharp descriptions, and registration checklist. Mirrors `skill_creator` for the workflow domain.
- Both new skills registered in `AGENTS.md`, `README.md`, and `List - Agentic Instructions.md`.

### Changed
- Standardized all 6 existing skills against the `skill_creator` spec:
  - Added missing `name:` frontmatter field to `cleanup_orphans`, `conventional_commits`, `generate_obsidian_note`, `maintain_project_docs`.
  - Upgraded all weak descriptions to "pushy" triggering language (explicit context cues and imperative phrasing).
  - Fixed typo in `maintain_project_docs` description ("warrent" → "warrant").
  - Removed redundant `## Trigger` body sections from `analyze_health` and `analyze_psych` — trigger logic consolidated into `description:` only.
- Standardized all 8 workflows:
  - Removed redundant `## Trigger` body sections from `add_job_requirement`, `audit_inbox`, `create_project`, `distill_learning`, `plan_activity`, `render_resume`.
  - Sharpened overlapping descriptions on `capture_content`, `distill_learning`, and `create_new_note` — each now explicitly cross-references the other two to prevent agent confusion.

## [1.5.1] - 2026-04-01

### Added
- Implemented `/capture_content` workflow and agentic scaffolding (Template, SKILL updates) for logging videos, articles, and raw snippets.
- Created `tools/youtube_transcript.py` script to extract YouTube video transcripts directly to text files.
- Added `youtube-transcript-api` to `requirements.txt`.

## [1.5.0] - 2026-03-31

### Added
- Added `analyze_psych` agentic skill to provide science-based, non-sycophantic psychological support and cognitive architecture analysis.
- Mandatory context check of Section 2.3 ("Psych") in the TOC before providing emotional or mental health support.
- Updated `AGENTS.md`, `README.md`, and `Workshop - Agentic Instructions.md` to register the new skill.
- New Vault subsections under `2.2. Medical/`: `Health Logs/` (doctor visit notes) and `Lab Work/` (bloodwork results).
- New Vault subsections under `3.3. Career Strategy & Revenue/`: `3.3.2` through `3.3.6` (Interview Prep, Portfolio, Networking CRM, Income Streams, Compensation).
- Updated `README.md` directory tree to reflect all new subsections.
- Updated `Table of Contents.md` with wiki-links for all new Health Logs and Lab Work notes.

### Fixed
- Fixed stale references in `audit_inbox.md`, `add_job_requirement.md`, and `create_project.md`.
- Updated `create_project.md` to include mandatory registration in the `To Do List`.
- Updated `distill_learning.md` to optionally update `Current Learning.md` with new study materials.
- Significant improvements to `AGENTS.md`: fixed Rule 4 typo, added deterministic Tools documentation (Python scripts and Resume Engine), and added Rule 11 for mandatory `To Do List` registration for projects/protocols.

## [1.4.0] - 2026-03-30

### Added
- Added `analyze_health` agentic skill to enforce reading Section 2 of the TOC and performing comprehensive context checks before analyzing user health issues.
- Updated `AGENTS.md` to register `analyze_health` as a mandatory behavior skill.

## [1.3.0] - 2026-03-21

### Added
- Implemented `resume-engine` tool for generating professional PDF resumes from Markdown sources.
- Added `tools/resume_engine/` directory with `render.js` script and `style.css`.
- Updated `AGENTS.md` to include `resume-engine` as a deterministic capability for generating resumes.
- Added `tools/resume_engine/package-lock.json` for dependency management.

### Changed
- Deepened `README.md` repository structure to show one more header level (H2 equivalent) for all primary Vault sections.
- Added concise descriptive comments to all Vault and Agent Workflow files in the `README.md` directory tree for improved clarity.

## [1.2.0] - 2026-03-20

### Added
- Implemented `git-crypt` for transparent, local-only encryption of all Vault contents (`Vault/**`) before syncing to GitHub.
- Added strict ignore rules to `.gitignore` to prevent committing the `git-crypt` master key and other sensitive credential files.
- Updated `AGENTS.md` and `conventional_commits` skill to explicitly enforce batching of commits and pushes (forbid micro-commits).
- Added Production Engineering - Meta job listing to `Employer Skill Requirements.md` and refreshed the AI summary.
- Transitioned to an "Engine-only" Git policy: AI agents will no longer commit individual notes or "thoughts" in the `Vault/` directory, focusing Git operations on tools, skills, workflows, and project structure.

## [1.1.0] - 2026-03-19

### Added
- Four new Agentic Workflows to simplify knowledge management and cognitive load:
  - `/audit_inbox` — Zettelkasten maintenance and raw note structuring.
  - `/create_project` — Task extraction and project planning from raw notes.
  - `/distill_learning` — Concept extraction and atomic note generation from complex papers/articles.
  - `/plan_activity` — Intelligent itinerary generation using relationship/activity data.
- Updated `Protocol - System Maintenance.md` to include running `/audit_inbox`.

## [1.0.4] - 2026-03-19

### Added
- `Vault/Sensitive/` folder for sensitive notes/files gitignored

### Changed
- Renamed `scripts/` to `tools/`.
- Updated `AGENTS.md` and `README.md` to reflect the new unified "Tools & Workflows" structure.
- Updated `conventional_commits` skill and `AGENTS.md` to require TOC section references for Vault changes in git commit messages.
- Updated `maintain_project_docs` skill and `AGENTS.md` to require README, CHANGELOG and AGENTS.md updates when needed & to maintain README's vault structure diagram.
- Put section 3.Forge at the end of the TOC b/c it's so big. Changed TOC & folder structure.
- Added "Brain Functions & Automation" conceptual framework to `README.md` and `AGENTS.md` to clarify the use of Active Procedures (Workflows) vs. Deterministic Capabilities (Tools).

### Removed
- Section 3.2.12 - "Career" - moved to section 4.3

## [1.0.3] - 2026-03-18

### Added
- Note generation rules enforcing prefixed filenames (`Project -`, `Protocol -`, etc), banning redundant H1 headers, and moving the Table of Contents link to the top of the file
- Rule 10 in `AGENTS.md` enforcing `.gitkeep` files for empty directories.
- Folder maintenance scripts: `scripts/create_folders.py`, `scripts/check_folders.py`, and `scripts/add_gitkeeps.py`.
- `/add_job_requirement` workflow for automated PDF/URL job criteria extraction.

### Changed
- Moved all python scripts into the `scripts/` root directory.
- Updated all script references across `README.md`, `CHANGELOG.md`, and `AGENTS.md`.
- Readjusted relative paths in `scripts/generate_podcast.py`.

## [1.0.2] - 2026-03-17

### Changed
- Updated documentation to use conventional "Affirm Vault Structure" language instead of deprecated sync_vault.py
- Updated `AGENTS.md` rules to require `CHANGELOG.md` updates and `git push` on every commit.

### Removed
- All active references to `sync_vault.py` from `AGENTS.md` and `README.md`


## [1.0.1] - 2026-03-16

### Added
- "Middle ground" TOC header structure in section 3.2 (3.2.x numbered, children unnumbered)
- Top-level files in `Vault/` created to match full TOC structure
- Added new category files and documentation
- New CSS snippet `headers.css` for custom header styling in Obsidian

### Changed
- Relocated Library & Learning resources from `Vault/` root to `Vault/3. Forge/`

### Removed
- `sync_vault.py` — script deleted in favor of direct agentic structure management

## [1.0.0] - 2026-03-14

### Added
- `scripts/generate_podcast.py` — converts all Vault notes to MP3 via edge-tts
- `sync_vault.py` — syncs Vault folder structure with Table of Contents H1 sections
- `AGENTS.md` — central AI agent constitution for the repository
- `README.md` — project documentation with setup, scripts, and structure
- `requirements.txt` — pinned Python dependencies
- `.agents/skills/generate_obsidian_note` — skill for creating Zettelkasten-formatted notes
- `.agents/skills/sync_vault_structure` — mandatory skill for folder/TOC sync
- `.agents/skills/maintain_project_docs` — mandatory skill for requirements.txt and README updates
- `.agents/skills/conventional_commits` — mandatory skill for commit message format
- `.agents/workflows/create_new_note` — end-to-end note creation workflow
- Vault folder structure created for all 12 TOC sections
- `.gitkeep` normalisation across all empty Vault folders

### Changed
- Reorganised repo: moved all Obsidian content into `Vault/` subfolder
- `scripts/generate_podcast.py` resolves edge-tts from `.venv` automatically
- `.gitignore` updated to exclude `.venv/`, `Vault/Audio/`, and `podcast_history.json`
