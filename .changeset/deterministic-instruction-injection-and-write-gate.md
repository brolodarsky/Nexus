---
type: minor
---
### Added
- Deterministic tool-layer instruction hydration and write-time gating (`src/nexus/core/instruction_guard.py`), tracking seen `Section Instructions.md`, frontmatter `instructions:`, and inline heading rules per execution scope (`thread_id`) with SHA-256 content-hash invalidation and `ToolNode` parallel batch coordination.
- PyYAML frontmatter `instructions:` contract parsing and Markdown heading-stack context extraction (`parse_frontmatter`, `extract_frontmatter_instructions`, `extract_all_headings_with_rules`, `extract_heading_context_for_line`, `format_partial_read_context`) in `src/nexus/shared_tools/vault_reader.py`.
- Unit and integration tests in `tests/test_instruction_guard.py` covering frontmatter/heading extraction, sliced disk/HITL reads, 3-layer write gating, scope isolation, batch race protection, subagent `Section Instructions.md` auto-hydration, and KV prompt-cache prefix stability.

### Changed
- Sliced `read_file` reads (`read_note_content` and `read_vault_file_with_hitl_overlay`) prepend missing YAML `instructions:` and enclosing heading rules automatically under `[Document Context]`.
- `modify_file` and `create_file` enforce instruction hydration before staging HITL transactions while letting plain ungoverned notes pass on the first call.
- `hydrate_subagent_context_files` and `spawn_subagent` (`src/nexus/agent/graph.py`) automatically discover and pre-hydrate ancestor `Section Instructions.md` files referenced by `context_files` or `task_prompt` (`prehydrated=True`), pruning ephemeral subagent scopes on exit and conversation scopes in `chats_db.delete_conversation`.
