---
type: patch
---
### Changed
- **Compact Directory Tree & Simplified Resident Hydration (`vault_reader.py`, `engine_constitution.py`, `AGENTS.md`):** Added `max_depth` support with inline leaf-folder bracket formatting (`[sub1, sub2]`) to `get_directory_tree()`, compressing `{vault_structure}` from ~100 lines to 28 lines while preserving all 3rd-level section headings, and stripped Obsidian YAML frontmatter/navigation links in `get_engine_constitution()`. Simplified `AGENTS.md` Role A instructions so IDE agents read `Vault/Playbook.md` directly alongside the hydrated structure/tools output.
