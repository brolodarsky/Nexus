---
type: minor
---
### Added
- **Universal `NexusAgent` (`src/nexus/agent/`):** Implemented the Single Universal Agent LangGraph runtime (`src/nexus/agent/graph.py` and `src/nexus/agent/api.py`) with dynamic `inject_root_instructions()` injection, pre-bound core Vault/HITL/comms tools, on-demand CLI execution (`run_shared_tool_cli`), prompt-driven subagent delegation (`spawn_subagent(task_prompt: str)`), and a deterministic $\le 5$ tool-iteration circuit breaker.
- **Surgical File Modification (`modify_file`) & Creation (`create_file`):** Replaced full-file rewrites on existing Vault notes with exact `target` $\rightarrow$ `replacement` block patching in `src/nexus/shared_tools/shared.py` (with CRLF/LF normalization) that stages complete pre/post diffs to the SQLite HITL queue (`hitl.db`). Added line-range slicing (`start_line`, `end_line`) and `resolve_vault_note_path` to `vault_reader.py`.

### Changed
- **Renamed `get_engine_constitution()` $\rightarrow$ `inject_root_instructions()`:** Standardized root instruction hydration in `src/nexus/core/engine_constitution.py` (retaining `get_engine_constitution` as a backward-compatible alias).
- **Rewired FastAPI, CLI, Voice, Telegram & Evals:** Connected `/api/agents/ask`, `/api/agents/ask/stream`, `src/nexus/main.py`, `src/nexus/interfaces/telegram.py`, `src/nexus/interfaces/voice.py`, `src/nexus/evals/runner.py`, and GUI agent badges directly to `NexusAgent`.

### Removed
- **Retired Legacy Multi-Agent Packages:** Removed `src/nexus/agents/router/`, `src/nexus/agents/career/`, and `src/nexus/agents/librarian/`.
