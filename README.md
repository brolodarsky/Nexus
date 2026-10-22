# Nexus: Agent-Integrated Knowledge OS & Cognitive Engine

Nexus is a agent-orchestrated knowledge engine designed to bridge unstructured markdown notes (Zettelkasten) with autonomous agentic workflows, deterministic tools, and dynamic subagent delegation. Its core architecture is a **Single Universal Agent (`NexusAgent`)** that boots with `Vault/Master Instructions.md`, navigates your knowledge Vault directly, reads domain-specific `Section Instructions.md` on demand, dynamically loads tools from `src/nexus/shared_tools/` based on lightweight catalog descriptions, and spawns isolated subagents hydrated for parallel or deep subtasks.

Rather than a static archive or a generic note template, Nexus acts as a cognitive framework. It couples a structured knowledge vault with a backend agent engine to ingest, search, process, and output real-world information.

## Key Technical Pillars

*   **Single Universal Agent + Dynamic Subagents (`src/nexus/`):** Instead of hardcoded domain agent packages or rigid YAML manifests per folder, one brand new universal agent boots with `Vault/Master Instructions.md` (hydrated with `{vault_structure}` and `{shared_tools}`), reads `<Section>/Section Instructions.md` when entering a domain, dynamically loads required tools on demand, and spawns subagents hydrated with subject-specific instructions and context files.
*   **Agentic File System (AFS):** Deterministic Python filesystem utilities (`vault_reader.py`) navigate the local Vault to locate, read, and cross-reference documents without requiring pre-indexing or external vector databases.
*   **Plain-English Instructions Hierarchy (`Master Instructions.md` $\to$ `Section Instructions.md` $\to$ YAML `instructions:`):** Universal Vault integrity gates, domain SOPs, and note-level maintenance contracts live natively inside the Vault in plain Markdown/YAML.
*   **Deterministic Automation Layer (`src/nexus/shared_tools/`):** Python and Node.js integrations for Gmail work, Google Calendar work, webpage text extraction, YouTube transcripts, HL7 medical XML parsing, ADB phone chat scraping, edge-TTS audio podcast generation, PDF/DOCX resume rendering, etc.

## Production Case Study: Radical Transparency

To demonstrate real-world utility and verify agent performance under complex, non-trivial conditions, this repository is configured as a live, production deployment. 

*   **Public Engine Layer:** The entire agent architecture, tools, evaluations, and directory structures are public to serve as a reference implementation.
*   **Private Data Layer (Gitignored):** The actual markdown content, files, and personal databases are kept strictly local (synced via Syncthing and encrypted/gitignored), preserving privacy while showing the system's structural schema in action.

## Repository Structure

```
Nexus/
├── .agents/                    # AI agent instructions
│   ├── rules/                  # Builder coding constraints
│   │   └── code_commenting_standards.md # Learning-first educational commenting
│   ├── skills/                 # Builder mandatory behaviors (repo/git/docs)
│   │   ├── conventional_commits/     # Commit message format rules
│   │   ├── maintain_project_docs/    # Keep README & changesets in sync
│   │   ├── skill_creator/            # Create & improve Builder skills
│   │   └── workflow_creator/         # Create & improve Builder workflows
│   └── workflows/              # Builder procedures (slash commands)
│       └── release.md                # Release compilation & changelog bump
├── .changeset/                 # Release fragments
├── .venv/                      # Python virtual environment (not committed)
├── scripts/                    # Maintenance & release utilities
│   ├── audit_career_drift.py   # Tier-1 career document drift auditor
│   ├── release.py              # Changeset compiler & release automation
│   └── sync_vault.py           # Nested Vault repository git synchronization
├── Vault/                      # All Brain content lives here
├── AGENTS.md                   # AI agent constitution
├── CHANGELOG.md                # Running log of notable changes
├── src/nexus/                      # Agentic search & coordinator engine
│   ├── main.py                  # Universal coordinator & mission control
│   ├── agent/                   # Single Universal Agent (NexusAgent)
│   │   ├── api.py               # Public entrypoints (run_nexus_agent, route_content, execute_vault_query)
│   │   └── graph.py             # LangGraph StateGraph (inject_root_instructions, core tools, spawn_subagent, <=5 circuit breaker)
│   ├── core/                    # Shared engine configuration
│   │   ├── audio.py             # Whisper transcription service
│   │   ├── constants.py         # Global constants
│   │   ├── engine_constitution.py # Loader for Vault/Master Instructions.md (inject_root_instructions())
│   │   ├── google_auth.py       # Reusable OAuth2 manager
│   │   └── hitl_queue.py        # SQLite HITL transaction queue
│   ├── evals/                   # Benchmarking & Golden Dataset
│   │   ├── dataset.json         # 12 real-world Q&A cases
│   │   ├── runner.py            # Automated eval script
│   │   └── results/             # Structured eval reports
│   ├── interfaces/              # Entry-point implementations (cli, voice, telegram)
│   └── shared_tools/            # Shared engine utilities & deterministic CLI tools
│       ├── vault_reader.py      # Pure-Python Vault navigation & search functions
│       ├── shared.py            # Shared LangChain @tool wrappers (read_file, modify_file, create_file, get_directory_structure, search_vault)
│       └── summarizer.py        # Conversation window compression & archiving node
├── start.ps1                   # Launches backend + frontend Control Panel
├── pyproject.toml              # UV dependency configuration
└── uv.lock                     # Reproducible dependency lock
```

---

## Setup

First time on a new machine:

```powershell
uv venv
.venv\Scripts\Activate.ps1
uv sync
```

> The `.venv/` folder is excluded from Git. `pyproject.toml` and `uv.lock` are the source of truth for dependencies.

### Phone Chat Ingestion Setup (`ingest_phone.py`)
To use the universal chat scraper, you must have ADB (Android Debug Bridge) installed and your phone configured:
1. **Install ADB**: On Windows, you can use Winget: `winget install Google.PlatformTools --accept-source-agreements`. Ensure the installation directory is in your system `PATH`.
2. **Enable USB Debugging**: On your Android phone, go to Settings → Developer Options → Enable "USB Debugging".
3. **Connect**: Connect via USB (or wireless ADB) and tap "Allow" on the phone's authorization dialog.
4. **Run**: Open the chat you want to save on your phone's screen and run `python src/nexus/shared_tools/ingest_phone.py --screens <N>`.

## The Engine (Skills, Workflows & Tools)

This repository distinguishes between capabilities and constraints that define how the Brain automation works. It is critical to understand the distinction between Rules, Skills, Workflows, and Tools:

1. **Vault Instructions (`Vault/Master Instructions.md` & `Vault/<Section>/Section Instructions.md`)**: **Resident Agent Constitution, Domain Laws & Vault SOPs**. Universal Vault note standards, inbox triage, augment-first distillation, project lifecycle/archiving, orphan audits, Cognitive Boundary Flushes, weekly reviews, medical record ingestion, career counseling, JD ingestion, and resume rendering live natively inside the Vault so both LangGraph runtime agents and IDE Resident agents inherit them with zero drift.
2. **Rules (`.agents/rules/`)**: **Builder Coding Standards**. Developer guidelines (e.g., granular educational commenting requirements) loaded automatically across IDE sessions.
3. **Builder Skills (`.agents/skills/`)**: **Developer & Repo Mandatory Behaviors**. Rules that an IDE Builder Agent must follow when modifying engine code, git history, or `.agents/` definitions.
4. **Builder Workflows (`.agents/workflows/`)**: **Developer Release & Repo Procedures**. Explicit slash-command recipes for repository releases (`/release`).
5. **Engine Runtime Tools (`src/nexus/shared_tools/`)**: **Deterministic Capabilities**. Python scripts for domain-specific automation (Gmail, Calendar, webpage extraction, TTS, medical XML parsing) used by agents.
6. **Meta Scripts (`scripts/`)**: **Repository Maintenance**. Dev/CI tools used for career drift validation, releases, and backups.

### Builder Agent Skills (`.agents/skills/`)

| Skill | Trigger |
|---|---|
| `conventional_commits` | On every `git commit` |
| `maintain_project_docs` | Keep README.md, AGENTS.md, and changesets up to date after engine/tool/skill changes |
| `skill_creator` | When asked to create, edit, evaluate, or optimize a Builder skill |
| `workflow_creator` | When asked to create, edit, or improve a Builder workflow |

### Builder Workflows (`.agents/workflows/`)

- `/release`: Automates the release process by compiling `.changeset/` fragments into the changelog, bumping the version, and committing/pushing the release.

### Deterministic Tools (Scripts)

| Tool | Purpose | Usage |
|---|---|---|
| `youtube_transcript.py` | Downloads YouTube transcripts to text files. | `python src/nexus/shared_tools/youtube_transcript.py <url>` |
| `read_webpage.py` | Extracts clean markdown content from single webpages via trafilatura. | `python src/nexus/shared_tools/read_webpage.py <url> [-o output.md]` |
| `gmail_engine.py` | Gmail REST API v1 multi-account integration: search (native Gmail syntax), read/thread as markdown, labels, archive, trash, drafts (never sends). Supports `--accounts`, `--auth --account <name>`, and `--account all` multi-inbox aggregation with isolated OAuth tokens at `.secrets/token_gmail*.json`. | `python -m nexus.shared_tools.gmail_engine --accounts` / `--auth --account <name>` / `--list 10 [--account all]` / `--search "from:x newer_than:7d"` / `--read <id>` / `--draft TO SUBJ BODY` |
| `calendar_engine.py` | Deterministic Google Calendar integration for listing, creating, and updating events with local OAuth token isolation. | `python src/nexus/shared_tools/calendar_engine.py --today` |
| `generate_podcast.py` | Converts a specific markdown note to MP3 via edge-tts. | `python src/nexus/shared_tools/generate_podcast.py <path> [--force]` |
| `medical_xml_parser.py` | Parses HL7 CDA medical XML files to structured Markdown. | `python src/nexus/shared_tools/medical_xml_parser.py <path> <output_dir>` |
| `ingest_phone.py` | Universal ADB screen-scraper for Android chat ingestion. Captures any app on screen. | `python src/nexus/shared_tools/ingest_phone.py --screens 50` |
| `export_conversation.py` | Universal JSON/JSONL chat transcript parser and formatter (supports JSON arrays, JSONL streams, ChatGPT exports, stdin piping, and local Antigravity transcripts). | `python src/nexus/shared_tools/export_conversation.py <file_or_id> [-o out.md] [-v]` |
| `vault_reader.py` | Deterministic Vault filesystem inspector: lists documents created or edited today (`--today`), within the last N hours (`--hours`), or since a date (`--since`), plus folder tree browsing (`--tree`), note reading (`--read`), and keyword search (`--search`). | `python -m nexus.shared_tools.vault_reader --today` / `--hours 6` / `--since YYYY-MM-DD` / `--path "<section>"` / `--tree` |

### Meta Scripts (`scripts/`)

| Script | Purpose | Usage |
|---|---|---|
| `audit_career_drift.py` | Performs deterministic Tier-1 drift audit across the 3.1 career cluster. | `python scripts/audit_career_drift.py` |
| `release.py` | Compiles `.changeset/*.md` fragments into the changelog and bumps version. | `python scripts/release.py` |
| `sync_vault.py` | Automatically commits and pushes the nested Vault repository (The Nested Heart). | `python scripts/sync_vault.py` |
| `src/nexus/main.py` | Universal coordinator for the Nexus Engine. Features a persistent mission control menu and background Telegram bot. | `nexus` |
| `src/nexus/evals/runner.py` | Benchmarks `NexusAgent` against the Golden Dataset. | `python -m nexus.evals.runner` |
| `src/nexus/agent/graph.py` | Single Universal Agent (`NexusAgent`). Boots with prompt-cache-isolated `inject_root_instructions()`, routes across Gemini Flash / OpenAI tiers (`get_chat_model`), binds core Vault/HITL tools, spawns parallel isolated subagents (`spawn_subagent(task_prompt, model_tier="low")`), and enforces the $\le 5$ tool-iteration circuit breaker. | `python -m nexus.agent.api` |
| `src/nexus/shared_tools/vault_reader.py` | Pure-Python filesystem utilities for Vault navigation and recent modification queries (`get_recent_modifications`, `get_directory_tree`, `resolve_vault_note_path`, `read_note_content`, `search_within`). | `python -m nexus.shared_tools.vault_reader --today` |
| `src/nexus/shared_tools/shared.py` | Shared LangChain `@tool` wrappers (`get_directory_structure`, `read_file`, `modify_file`, `create_file`, `search_vault`, `get_recent_modifications`, `fetch_emails`, calendar tools, `run_shared_tool_cli`). | N/A (library module) |
| `src/nexus/shared_tools/summarizer.py` | Shared LangGraph node function for compressing conversation history into Short-Term Recall and Deep Recall archives. | N/A (library module) |
| `src/nexus/core/engine_constitution.py` | Hydrates `Vault/Master Instructions.md` via `inject_root_instructions()` (`{current_time}`, `{user_name}`, `{vault_structure}`, `{shared_tools}`). IDE Resident agents and `NexusAgent` inject its output at boot. | `python -m nexus.core.engine_constitution` |
| `src/nexus/core/tool_catalog.py` | Static (`ast`, no imports) catalog of `src/nexus/shared_tools/` modules for the `{shared_tools}` placeholder. | `python -m nexus.core.tool_catalog` |
| `src/nexus/core/hitl_queue.py` | SQLite-backed HITL transaction queue for pending agent writes. | N/A (library module) |
| `src/nexus/core/chats_db.py` | SQLite-backed persistent UI chat history and sticky session state. | N/A (library module) |
| `src/nexus/api/routers/hitl.py` | HITL transaction endpoints: list pending, approve (write to disk), reject. | Via GUI or API |
| `resume_engine/` | PDF and DOCX rendering with page fill metrics. Outputs fill %, verdict, and room remaining after every render. | `node src/nexus/shared_tools/resume_engine/render.js` |
| `start.ps1` | Launches the full Nexus Control Panel (FastAPI + Next.js). | `.\start.ps1` |

## Architectural Methods

Nexus relies on several specific architectural patterns to maintain a clean boundary between the "Engine" (public) and the "Vault" (private).

### 1. Engine + Vault Separation
The repository is split into two layers:
- The **Engine** (`scripts/`, `src/nexus/`, `.agents/`, root docs) is the public portfolio—tracked, readable, and version-controlled.
- The **Vault** (`Vault/`) is the private content layer—mostly gitignored, synced locally via Syncthing.

### 2. Git-Crypt Defense-in-Depth
While all vault content is intentionally gitignored so it never enters the repository, I use **`git-crypt`** as a transparent layer of defense-in-depth for anything that *is* tracked inside the Vault (like folder structures).
- If a file inside the Vault accidentally gets tracked, its contents appear as binary gibberish on GitHub without the master key.
- The `.gitattributes` file defines this encryption scope; the TOC and `.gitkeep` files are explicitly excluded so they remain readable.

### 3. Syncthing + Git Dual Sync
- **Git** handles the Engine (code, skills, workflows).
- **Syncthing** handles the Vault content (notes, audio, large binaries) across my personal devices.
- For example, large MP3 files generated by the podcast tools are gitignored and sync via Syncthing only, avoiding repo bloat while maintaining mobile access.

### 4. Learning-First Codebase (Granular Educational Commenting)
Both the Python engine (`src/nexus/`) and the TypeScript frontend (`gui/`) are maintained as learning-first codebases. AI coding agents and human contributors adhere to a strict educational commenting standard:
- Complex signatures, generics (`<T>`, `TypeVar`), async flows (`Promise`, `async/await`, tasks), streaming buffers, and framework idioms are demystified line-by-line with concrete examples.
- Code comments serve as first-class educational scaffolding for developers with foundational coding knowledge, eliminating cryptic syntax and preserving long-term comprehensibility across all languages in the repo.

---


## How to Fork This Brain

If you want to use this as a starting point for your own system:
1. **Clone the repo** (you will only get the engine and the vault skeleton).
2. **Replace the vault content** by populating the folders with your own notes.
3. **Adapt the text instructions** to match your own domain context and personal rules.

> [!tip] The "Nested Heart" (Optional Private Versioning)
> Because the `Vault/` folder is explicitly gitignored in this main repository, your personal notes will not have version history by default. If you want to version-control your private thoughts without risking exposing them in your public engine fork, you can initialize a *second, nested* Git repository directly inside the `Vault/` directory (`cd Vault; git init`) and push it to a separate private remote. This repository includes a `scripts/sync_vault.py` script designed to help you commit to this nested private repo automatically without causing Git context-confusion.

## Obsidian Setup

Point Obsidian at the **`Vault/`** subfolder, not the repo root.

> Settings → About → Vault path → `…/Nexus/Vault`
