---
type: patch
---
### Fixed
- Exempted `cache://...` handles and `{{cache:...}}` placeholders (including ones containing `.md`/`.pdf`/`.docx`) from false `[SYSTEM WARNING]` triggers inside `verify_context_brief_paths()` (`src/nexus/shared_tools/vault_reader.py`).
- Fixed CLI/eval `"nexus_primary"` runs skipping capture inheritance when invoking `spawn_conversation` (`src/nexus/shared_tools/shared.py`), preserving standalone root conversation creation while still passing `source_cache_conversation_id` into `spawn_seeded_conversation()`.
- Appended a lightweight `Inherited External Captures` manifest (via `format_captures_manifest()`) to seeded briefs in `spawn_seeded_conversation()` (`src/nexus/core/chat_branching.py`) and reported the inherited capture count in `spawn_conversation` receipts.
