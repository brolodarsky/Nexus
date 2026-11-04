---
type: patch
---

### Changed
- **HITL Review Queue UI Hierarchy (`gui/src/app/hitl/page.tsx`):**
  - Replaced the monolithic, all-caps `NEXUS_AGENT` label at the top of review queue cards with prominent `Ticket #{id}` badges matching conversational agent citations.
  - Promoted the target note title to the card's primary header (`font-semibold text-sm`) with tooltip truncation.
  - Made the proposing agent and action type the secondary header (`{agent_name} · {action_type}`).
  - Added a visible `Ticket #{id}` badge to the main review panel header alongside the target file title and path.
  - Updated action notices and recently applied ledger entries to consistently cite `Ticket #{id}`.
