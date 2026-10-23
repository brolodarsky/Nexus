---
type: patch
---
### Fixed
- Fixed race condition in concurrent HITL tool calls (`modify_file` and `create_file` executed across parallel LangGraph `ToolNode` worker threads) modifying the same Vault document in a single LLM turn.
- Introduced `get_file_mutation_lock` in `src/nexus/core/hitl_queue.py` (`threading.RLock` per normalized target note) to strictly serialize in-flight checks, surgical replacements, and cumulative overlay stacking so concurrent edits coalesce cleanly into a single review card.
- Added concurrency test `test_concurrent_modify_file_stacks_cleanly_into_single_transaction` in `tests/test_hitl_commit.py`.
