# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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

## [2.7.0] - 2026-07-03

### Added
- Created `src/nexus/core/chats_db.py` to manage unified frontend chat history and sticky routing state.
- Integrated LangGraph `SqliteSaver` checkpointer for working memory in `career` and `librarian` agents.
- Created `src/nexus/shared_tools/summarizer.py` with `summarize_conversation` for pruning and summarizing short-term recall.
- Added `summarizer_node` to `src/nexus/agents/career/graph.py` to compress working memory on the fly.

### Changed
- Updated `src/nexus/api/routers/agents.py` to persist chat history and implement sticky routing for active agents.
- Updated Next.js frontend (`AskBrainPage`) to fetch chat history on mount.
- Refactored Career Agent (`api.py` and `graph.py`) to build the system prompt ephemerally inside `call_model`, preventing duplication bugs in the checkpointer state.
- Refactored `.gitignore` to explicitly ignore `*.db`, `*.db-shm`, and `*.db-wal` files and untracked existing tracked db files (`logs/chats.db` and `src/nexus/agents/career/memory.sqlite`).
- Refactored `read_note` logic across domain agents. Moved bounded path resolution and fuzzy-searching natively into `vault_reader.read_note_content`.
- Extracted LangChain tool wrapper into `shared.py`'s `get_read_note_tool` factory function.
- Updated `AGENTS.md` Rule 6 to explicitly clarify architectural boundaries between pure Python data access layers (like `vault_reader.py`) and agentic `@tool` wrappers.

### Fixed
- Fixed an issue where the Career Agent would crash with an OpenAI `invalid_request_error` (400) due to dangling tool calls in the LangGraph state checkpoint after interruptions.
- Hardened the `propose_write` tool by resolving paths dynamically based on domain scopes and gracefully de-duplicating path nesting, preventing the creation of redundant directories outside of the Vault (such as in `PROJECT_ROOT`).
- Updated the career agent prompt to use this new simplified pathing behavior.

## [2.6.0] - 2026-06-22

### Added
- Created `src/nexus/core/config.py` using Pydantic `BaseSettings` to serve as the centralized source of truth for environment variables.
- Added dynamic injection of `{datetime}` and `User` to `src/nexus/core/engine_constitution.py`.
- Installed `pydantic-settings` via `uv` and updated `requirements.txt`.

### Changed
- Refactored `src/nexus/core/constants.py`, `src/nexus/interfaces/telegram.py`, and `src/nexus/agents/email/tools.py` to replace scattered `os.getenv` calls with strongly-typed `settings` from `config.py`.
- Moved the `.secrets` directory from `tools/.secrets` to the project root `.secrets` to align with the new `src/nexus` engine architecture and industry standards for credential management.
- Updated `.gitignore` and `src/nexus/agents/email/tools.py` to reflect the new root `.secrets` location.
- Refactored `AGENTS.md` to act strictly as the Builder rulebook, removing internal engine architecture principles.
- Added Standing Guidelines to `AGENTS.md` to enforce strict file structures and centralized logging/validation for all future engine agents.
- Migrated default package management workflow from `uv pip install` & `requirements.txt` to `uv add` and `uv.lock`.
- Updated `AGENTS.md` and `maintain_project_docs` skill to formally deprecate `requirements.txt` in favor of `pyproject.toml`.

### Fixed
- Fixed `OPENAI_API_KEY` missing error when starting Next.js/FastAPI via `start.ps1` by explicitly injecting `.env` into `os.environ` within `src/nexus/core/config.py`.
- Fixed execution failure in `tools/read_email.py` by removing legacy `sys.path.append` hacks and updating to the `nexus.*` import namespace.
- Fixed double chat response bug in Nexus GUI AskBrainPage caused by React Strict Mode double-invoking state updaters

### Removed
- Removed static `ENGINE_CONSTITUTION.md` and replaced it with a dynamic Python module.
- Deleted legacy `requirements.txt`.
