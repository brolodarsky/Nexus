---
type: minor
---
### Added
- Added `context_files: Optional[list[str]] = None` to `spawn_subagent` (`src/nexus/agent/graph.py`) backed by `read_vault_file_with_hitl_overlay()` and `hydrate_subagent_context_files()` (`src/nexus/shared_tools/shared.py`) to pre-hydrate verified disk and staged HITL files under `# Pre-Hydrated Disk Context`, failing fast with nearest-directory sibling listings (`find_nearest_directory_and_matches()` in `src/nexus/shared_tools/vault_reader.py`) when any path does not resolve.
- Added `target_section: Optional[str] = None` and deterministic `verify_context_brief_paths()` link/filename validation to `spawn_conversation` (`src/nexus/shared_tools/shared.py`) and `spawn_seeded_conversation` (`src/nexus/core/chat_branching.py`), appending live section directory snapshots and `[SYSTEM WARNING: ...]` alerts to both the seeded brief and tool receipt when referenced `[[Wiki-Links]]` or `.md`/`.pdf`/`.docx` files do not exist on disk.

### Changed
- Updated `seed_langgraph_thread_from_messages()` (`src/nexus/core/chat_branching.py`) Message #0 anchor to explicitly warn child threads that `Section Instructions` and living notes are not yet loaded and must be hydrated from disk before mutating state or delegating.
- Synced `Vault/Master Instructions.md` and `README.md` with the new `spawn_subagent(..., context_files=...)` and `spawn_conversation(..., target_section=...)` interfaces.
