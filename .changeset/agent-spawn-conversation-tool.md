---
type: minor
---
### Added
- Added `spawn_seeded_conversation()` in `src/nexus/core/chat_branching.py` to create pre-seeded "seed & wait" conversations in `chats.db` (supporting nested child branches and standalone root threads with `title_source="manual"`) and hydrate LangGraph `memory.sqlite` checkpoints without executing an immediate LLM turn.
- Added `@tool def spawn_conversation(title, context_brief, nest_under_current=True)` in `src/nexus/shared_tools/shared.py` and bound it into `CORE_TOOLS` (`src/nexus/agent/graph.py`), enabling both the Head Agent and `spawn_subagent` workers to spin off dedicated, anchor-packed follow-up threads directly from multi-topic sweeps.
- Added automated regression coverage in `tests/test_chat_branching.py` for nested branches, standalone root threads, and subagent execution-context inheritance.

### Changed
- Updated `gui/src/app/chat/page.tsx` so `spawn_conversation` `tool_result` SSE trace events immediately refresh `ChatSidebar` and `BranchLineageBar` mid-turn.
