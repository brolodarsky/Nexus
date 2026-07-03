# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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

## [2.5.0] - 2026-06-09

### Added
- Real-time agent trace streaming from the Python engine to the Next.js GUI via Server-Sent Events (SSE).
- `POST /api/agents/ask/stream` endpoint in FastAPI that yields live trace events.
- `TraceEventBus` pub/sub system in `engine/core/trace.py` that broadcasts `AgentTracer` events.
- Collapsible "Thinking Panel" in the Ask Brain GUI that displays live agent tool calls, routing decisions, and LLM reasoning steps with colors and icons.
- Persisted trace logs for past messages in the chat history.

### Changed
- Wire GUI Ask Brain page to the Content Router agent instead of calling the Librarian directly. The /api/agents/ask endpoint now routes through classify → domain dispatch, and the frontend displays which agent handled each query with domain and confidence metadata.
- Migrated python environment management from `pip` and `python -m venv` to Astral's `uv` for improved speed and determinism.
- Updated `AGENTS.md`, `README.md`, and `maintain_project_docs` skill to enforce `uv pip` usage.
- Restructured `engine/` directory into a standard `src/nexus/` Python package layout.
- Replaced `requirements.txt` with `pyproject.toml` (using `uv` and `hatchling` backend).
- Updated all internal imports to absolute imports under the `nexus.*` namespace.
- Replaced the standalone `python engine/main.py` command with a managed `nexus` CLI executable.
- Updated `start.ps1` to use absolute imports (`nexus.api.main:app`) and project-root working directory.

### Fixed
- Fixed `IndentationError` in `engine/agents/email/tools.py` due to missing `try` block for `list_recent_emails`.
- Fixed Content Router LLM hallucination where it aggressively triggered `fetch_emails` for local notes by tightening the `fetch_emails` tool docstring and router prompt.

### Removed
- Deleted `requirements.txt` in favor of PEP-621 `pyproject.toml` management.
- Removed legacy `sys.path.insert()` and `sys.path.append()` hacks used for standalone script execution.
