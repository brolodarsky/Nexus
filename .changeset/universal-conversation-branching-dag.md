---
type: minor
---
### Added
- **Universal Conversation Branching (`chats.db` DAG) & Subroutine Merge Engine (`src/nexus/core/chat_branching.py`, `src/nexus/api/routers/chat_branches.py`):** Implemented engine-level conversation branching (`POST /api/agents/ask/conversations/{id}/branch`) supporting both `'tangent'` mode (proportional `Parent Context Brief` + focal turn in an isolated context window) and `'fork'` mode (verbatim history clone up to `parent_message_id`), plus `POST /api/agents/ask/conversations/{id}/merge` to distill branch takeaways at proportional depth and merge them back into the parent conversation and LangGraph checkpointer (`memory.sqlite`).
- **Modular Next.js Branching UI (`gui/src/components/chat/`, `gui/src/lib/api/branches.ts`):** Added `MessageBranchTrigger.tsx` (per-message `🌿 Branch` popover and inline child branch pills), `BranchLineageBar.tsx` (parent breadcrumb, optional focus guidance note, and `Distill & Merge to Parent ↩` action), `useChatBranching.ts` hook, and collapsible nested branch trees in `ChatSidebar.tsx`.
- **Automated Regression Tests (`tests/test_chat_branching.py`):** Added 6 unit and integration tests covering full history forks, tangent context briefs, Turn-1 tangent optimization, subroutine distillation & merge, parent deletion promotion, and error guards.

### Changed
- **SQLite `chats.db` Lineage Schema (`src/nexus/core/chats_db.py`):** Added idempotent schema migrations (`parent_conversation_id`, `parent_message_id`, `branch_mode`, `merged_at`) to `conversations`, exposed `id` (`messages.id`) in `get_chat_history()`, returned inserted row IDs from `log_message()` (emitted in SSE `done` packets), and promoted child branches to root level on parent deletion.
- **Session Transcript Exporter (`src/nexus/shared_tools/export_conversation.py`):** Updated `load_conversation_source()` to prefer `transcript_full.jsonl` over `transcript.jsonl` when resolving brain directories and conversation UUIDs so long assistant turns are exported in full without mid-response `<truncated ... bytes>` placeholders.

