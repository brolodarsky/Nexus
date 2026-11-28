---
type: minor
---
### Added
- **Verbatim Chat-Draft Block Cache (`cache://chat`):** Added CommonMark-aware fenced block extraction (`extract_fenced_blocks`, `list_chat_blocks`, `get_chat_block`, `format_chat_blocks_manifest`) in `src/nexus/core/conversation_cache.py`, integrated with `read_file("cache://chat")` / `read_file("cache://")`, `hydrate_subagent_context_files`, and `{{cache:chat/m<id>-b<n>}}` verbatim splicing in `create_file` / `modify_file` (with zero new bound tools, preserving 30/30 `FastMCP` parity).

### Fixed
- **Root Directory Tree Token Bomb (`get_directory_structure`):** Bounded root aliases (`""`, `"."`, `"/"`, `"Vault"`, `"Vault/"`) to depth 1 (`max_depth=1`) in `src/nexus/shared_tools/shared.py` so inspecting root notes no longer dumps every nested file across the Vault.
- **Literal `{{cache:...}}` Documentation Immunity (`_resolve_cache_placeholders`):** Ignored inline-backticked syntax examples (`` `{{cache:...}}` ``) and metasyntax placeholders (`...`, `<...>`, `*`) in `src/nexus/shared_tools/shared.py` while keeping strict fail-fast validation for missing active splice keys.
- **Fenced Code-Block False Hydration (`discover_section_instructions_for_subagent`):** Added `_strip_fenced_code_blocks()` in `src/nexus/core/instruction_guard.py` so pasted draft text inside `spawn_subagent(task_prompt=...)` no longer triggers spurious `Section Instructions.md` pre-hydration.
- **Subagent Batching & Photocopy Relay Guard (`subagent.py`, `Vault/Master Instructions.md`):** Updated `subagent_protocol` to batch independent `create_file`/`modify_file` calls in parallel and instructed the Commander not to relay already-drafted files through `spawn_subagent` when parallel `create_file` + `{{cache:chat/...}}` works directly.
