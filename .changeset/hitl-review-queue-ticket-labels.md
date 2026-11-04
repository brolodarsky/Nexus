---
type: minor
---

### Added
- **HITL Provenance Tracking (`conversation_id`, `thread_id`, `agent_id`, `agent_role`):**
  - Extended `src/nexus/core/hitl_queue.py` (`transactions` schema, idempotent `ALTER TABLE` migration, `add_transaction`, and `get_recent_revisions`) with `conversation_id`, `thread_id`, `agent_id`, and `agent_role` columns plus `ContextVar`-backed execution context propagation (`set_hitl_execution_context`, `reset_hitl_execution_context`, `get_hitl_execution_context`).
  - Wired parent `Commander (<tier>)` (`agent_id="nexus"`) and spawned `Subagent #<n> (<tier>)` (`agent_id="subagent-<n>"`, `thread_id="<conv_id>:subagent-<n>"`) execution contexts in `src/nexus/agent/api.py` and `src/nexus/agent/graph.py`.
  - Exposed all 4 provenance fields in FastAPI `TransactionResponse` / `MockTransactionRequest` (`src/nexus/api/routers/hitl.py`) and TypeScript client types (`gui/src/lib/api/hitl.ts`), and backfilled 244 historical `hitl.db` transactions from run logs.

### Changed
- **HITL Review Queue UI Hierarchy (`gui/src/app/hitl/page.tsx`):**
  - Replaced the legacy `NEXUS_AGENT` label at the top of review queue cards with prominent `Ticket #{id}` badges matching conversational agent citations.
  - Promoted the target note title to the card's primary header (`font-semibold text-sm`) with tooltip truncation.
  - Displayed `agent_role`, `agent_id`, `conversation_id`, and `thread_id` pills in the card's secondary header and the main review inspector header.
  - Updated action notices and recently applied ledger entries to consistently cite `Ticket #{id}`.
