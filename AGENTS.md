# AGENTS.md

> This file tells any AI agent how to work in this repository. The Agentic Constitution.

## Project Overview

This is a personal "second brain"/knowledge management system that stores/uses markdown notes, images, pdfs and other files in a Vault as thoughts & memories.

It's read and tinkered with in Obsidian and tinkered with in agentic IDEs, version-controlled with Git, and synced to mobile via Syncthing. 

Notes follow the Zettelkasten methodology. Vault folder structure is defined in `Table of Contents.md`. Audio files are frequently generated for on the go listening to "thoughts". Several tools are available to help with "brain automation".

**Vault path:** `Vault/` (not the repo root)

## Repository Layout

| Path | Purpose |
|---|---|
| `Vault/` | All Obsidian content/second brain "thoughts" — notes, images, audio, pdfs, external links, etc. |
| `Vault/Table of Contents.md` | Master index; source of truth for folder structure/brain structure |
| `Vault/Audio/` | Generated MP3s (gitignored, synced via Syncthing) |
| `tools/` | Python scripts for brain automation |
| `engine/` | Agent engine in development - modular architecture (`main.py`, `core/`, `interfaces/`, `agents/`, `evals/`) |
| `engine/api/` | FastAPI backend — HTTP bridge between the GUI Control Panel and the Python engine |
| `gui/` | Next.js + Tailwind CSS frontend — Engine Control Panel (Mission Control dashboard, HITL review surface, Monaco diff viewer) |
| `requirements.txt` | Python dependencies |
| `.venv/` | Virtual environment (gitignored) |
| `.agents/skills/` | AI agent skill definitions |
| `.agents/workflows/` | AI agent workflows/tools to invoke |

## Skills (Mandatory Behaviours)

These are located in `.agents/skills/` and define rules you **must** follow.

<!-- AUTO-COMPILED BY maintain_project_docs. DO NOT EDIT DESCRIPTIONS MANUALLY -->

### `generate_obsidian_note`
**Trigger:** How to generate, move, format, or import Obsidian notes into the Vault. Always use this skill whenever saving any content to Vault/ — whether creating a new note, reformatting an existing one, moving a file to a new location, or importing external content. You MUST use this skill before writing or moving any .md file into the Vault. Make sure to list_dir on the target folder first to mimic existing naming patterns and respect physical folder structures.

### `maintain_project_docs`
**Trigger:** After `pip install`/`pip uninstall`, after adding/changing/removing tools, skills or rules.

### `conventional_commits`
**Trigger:** On every `git commit`

### `log_llm_conversation`
**Trigger:** Log design discussions, brainstorming sessions, and key technical decisions at the end of a conversation or pair programming session. Make sure to trigger this skill whenever the user mentions saving a chat log, logging a conversation, journaling a decision, or at the end of any complex session where important architectural, project, or code decisions were made, even if the user does not explicitly request it.

### `cleanup_orphans`
**Trigger:** When asked to "clean the vault", "find orphans", or perform Zettelkasten maintenance

### `analyze_health`
**Trigger:** Act as a specialized doctor and diagnose health issues safely with properly caveated language. Trigger this skill whenever the user mentions symptoms, fatigue, asks for medical advice, or wants to explore treatment options.

### `analyze_psych`
**Trigger:** Provide safely-caveated, science-based, non-sycophantic psychological support and cognitive architecture analysis. Trigger this skill whenever the user mentions depression, anxiety, decision fatigue, context switching, or any emotional processing.

### `archive_project`
**Trigger:** Use this skill whenever the user asks to archive a project, mark a project as done, complete a project, or move a finished project out of an active folder.

### `career_counselor`
**Trigger:** Act as a high-stakes career architect and strategic advisor. Provide advice on job hunt strategy, interview prep, compensation negotiation, and professional portfolio development. Trigger this skill whenever the user mentions job searching, career pivots, networking, resume updates, or professional growth.

### `project_work`
**Trigger:** Keep active project documents inside the Vault up to date whenever changes are planned, implemented, completed, or conceptually modified. Make sure to use this skill whenever you complete a task related to a project, plan modifications, create a new sub-project, or add/remove tasks conceptually from any Project - *.md file, even if the user does not explicitly request it.

### `skill_creator`
**Trigger:** When asked to create a new skill from scratch, edit or optimize an existing skill, run evals to test a skill, benchmark skill performance, or improve a skill's triggering description.

### `workflow_creator`
**Trigger:** When asked to create a new slash-command workflow, edit or improve an existing workflow's steps or description, or review a set of workflows for consistency.

## Tools & Workflows

This brain distinguishes between **Active Procedures** (Workflows) and **Deterministic Capabilities** (Tools).

- **Tools (`tools/`)**: Python scripts for deterministic automation (e.g., MP3 generation, folder sync).
- **Workflows (`.agents/workflows/`)**: Structured instructions/recipes for the AI agent to follow (e.g., `/create_new_note`).

### Tools

Deterministic scripts for vault and engine maintenance.

| Tool | Purpose |
|------|---------|
| `youtube_transcript.py` | Downloads transcripts from YouTube videos to text files. |
| `read_webpage.py` | Extracts clean markdown content from single webpages via trafilatura. |
| `read_email.py` | Fetches a single email by IMAP UID and returns it as clean markdown. Supports Google OAuth2. Also lists recent emails with `--list-recent N`. |
| `generate_podcast.py` | Converts a specific markdown note into an MP3 file via edge-tts. |
| `check_folders.py` | Validates that the current Vault structure matches `Table of Contents.md`. |
| `create_folders.py` | Idempotently creates the directory structure defined in the TOC. |
| `add_gitkeeps.py` | Adds `.gitkeep` to all empty folders to ensure tracking (Rule 10). |
| `backup_vault.py` | Creates a timestamped local backup of the `Vault/` directory. |
| `sync_vault.py` | Automatically commits the nested Vault repository (The Nested Heart). |
| `medical_xml_parser.py` | Parses HL7 CDA medical XML files into structured Markdown. |
| `ingest_phone.py` | Universal ADB screen-scraper for Android chat ingestion. Captures conversations from any app (Google Messages, Tinder, Hinge, WhatsApp, Signal, etc.) via `uiautomator dump` and saves structured Markdown to `0. Inbox/`. Supports multi-screen scroll capture. |
| `resume_engine/` | Node.js (Playwright) for PDF rendering + Python (`python-docx`) for DOCX generation. Interactive document picker scans `3.1.3. Professional Portfolio & Evidence/Resumes/` and `Cover Letters/` for renderable markdown documents. Outputs page fill metrics (fill %, verdict, room remaining) after every render so agents can add/trim content to optimize page utilization. Also accepts a CLI path argument for scripted use. |
| `engine/main.py` | Universal entry point & coordinator for the Agentic Engine. Features a persistent mission control menu with background Telegram bot support. |
| `engine/evals/runner.py` | Benchmarks the Librarian against the Golden Dataset using 12 real-world Q&A cases. |
| `engine/agents/librarian/agent.py` | Core ReAct agent execution logic (LangGraph). |
| `engine/tools/vault_tools.py` | Local filesystem LangChain tools for Vault navigation (`read_toc`, `read_note`, `search_vault`, `get_vault_structure`). Supports targeted subtree search and frontmatter tag filtering. |
| `engine/interfaces/cli.py` | CLI interface implementation. |
| `engine/interfaces/voice.py` | Voice interface implementation (Whisper). |
| `engine/interfaces/telegram.py` | Telegram interface implementation. |
| `engine/tools/email_tool.py` | Core email fetching and parsing logic for the agentic engine. |
| `engine/core/google_auth.py` | Centralized Google OAuth2 management (refreshing, token handling). |
| `engine/core/hitl_queue.py` | SQLite-backed HITL transaction queue. Stores pending agent writes with original/proposed content, reasoning, and status for human review. |
| `engine/api/main.py` | FastAPI application entry point for the GUI Control Panel. CORS, health check, router mounts. |
| `engine/api/routers/agents.py` | Agent status registry and `/ask` endpoint bridging the Librarian to the frontend. |
| `engine/api/routers/vault.py` | Vault structure, note reading, and search endpoints for the frontend. |
| `engine/api/routers/hitl.py` | HITL transaction endpoints: list pending, approve (write to disk), reject, and mock seeding for testing. |
| `start.ps1` | Launches the full Control Panel (FastAPI backend + Next.js frontend). Kills the entire uvicorn process tree on exit. |

### Workflows

Agentic protocols for complex knowledge management tasks.

<!-- AUTO-COMPILED BY maintain_project_docs. DO NOT EDIT DESCRIPTIONS MANUALLY -->

### `capture_content`
Format, move, or clean up a raw capture note to serve as an inbox item for future knowledge synthesis.

### `add_job_requirement`
Agentic tool. Automates extracting skills from a job description (PDF/URL), appending it to `Employer Skill Requirements.md`, and regenerating the high-level AI Summary for Career Strategy.

### `audit_inbox`
Agentic tool for reading and sorting raw notes and bullet points from the Brain Inbox and Quick Capture into the main Zettelkasten structure. Identifies downstream workflows (e.g., /add_job_requirement, /ingest_medical_record, /distill_learning) and chains their execution. Use during weekly review or when processing captured thoughts.

### `create_project`
Consolidates rough notes or ideas into a structured project note, complete with extracted tasks and materials appended to the bottom of the plan.

### `distill_learning`
Breaks down a dense external source (article, paper, PDF, URL) into atomic, interlinked notes. Prioritizes augmenting existing Vault notes over creating duplicates to ensure knowledge synthesis. For lightweight saving, use /capture_content instead.

### `ingest_medical_record`
Parse and ingest raw medical records (PDF, XML, Images) into the Vault following chronological conventions.

### `plan_activity`
Cross-references Activities List, Date Ideas, and People Data to generate a markdown itinerary.

### `render_resume`
Renders markdown documents (resumes, cover letters) from the Portfolio into professionally-styled PDF and DOCX files. Outputs page fill metrics so agents can determine if content needs to be added or trimmed to fill the page optimally.

### `ask_brain`
Agentic vault search. Uses a LangGraph ReAct agent to dynamically navigate the local filesystem and returns a grounded answer with source citations. Use when you need facts from your notes without reading files manually. No indexing required.

## Rules

1. Never delete user content without explicit confirmation.
2. Always use the .venv — resolve Python tools from .venv/Scripts/, not system PATH. Never install dependencies globally. Always use .venv\Scripts\pip.exe for installations. If a new requirement is added, immediately trigger the maintain_project_docs skill.
3. Commit messages must follow Conventional Commits — see conventional_commits skill. 
4. Git & Changelog Policy. Use this table to determine whether a change requires a git commit and/or a CHANGELOG.md entry:

| What changed? | Commit? | Changelog? | Version bump |
|---|---|---|---|
| Tool, skill, or workflow code | ✅ | ✅ | Minor or patch |
| New H1/H2 *section* in TOC / global structural paradigm change | ✅ | ✅ | Minor or patch |
| Project docs (AGENTS.md, README.md) | ✅ | ✅ | Patch |
| `.gitkeep` additions for new empty folders | ✅ | ❌ | — |
| Note wiki-links added to existing TOC sections | ❌ | ❌ | — |
| Individual note creation, edits, or deletions in `Vault/` | ❌ | ❌ | — |

- Key principles: Git is solely for the Engine (tools, skills, workflows, project docs) and Vault structure (new sections — not individual notes). Individual notes/thoughts are encrypted and backed up locally — avoid micro-commits. If there's an existing changelog version on the same day, update the existing version unless the change is significant.
5. The TOC is the single source of truth for Vault folder structure and the high-level concept of this entire project, but Physical Folder Structure on Disk takes precedence when resolving duplicate/split directory discrepancies to avoid breaking existing paths. Do not clutter the TOC with individual granular notes (e.g. single medical visits, individual articles, daily logs). Those should be linked and organized inside specialized "Hub" or "Map of Content" (MOC) notes (e.g., Health Summary, Auto Knowledge Base).
6. All notes must have YAML frontmatter with aliases, tags, and type fields.
7. Audio files are gitignored — they sync via Syncthing, not Git.
8. Keep AGENTS.md AND README.md updated. If you make fundamental changes to the project/brain functionality, update these files to reflect the changes.
9. Add .gitkeep to empty folders. Whenever creating a new empty directory in the Vault, always create an empty .gitkeep file inside it so it can be tracked by Git.
10. All Project - and Protocol - notes must be registered in To Do List.md. Ensure new projects are added to the Active Projects section of Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md.
11. Do not touch the Vault/.git directory. This is a nested private repository for the user's personal history. It is not part of the engine and should be ignored by all cleanup or auditing tools.