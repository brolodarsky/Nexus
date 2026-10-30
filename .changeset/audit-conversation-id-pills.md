---
type: patch
---

### Changed
- **Audit Run Ledger Conversation ID Badges (`gui/src/app/audit/page.tsx`):** Replaced the redundant static `"nexus"` agent badge on each run card in the left ledger with a compact conversation badge (`conv: <short_id>`) that displays the full UUID on hover. Falls back to agent name if unassociated with a thread.
- **Audit Search Filter (`gui/src/app/audit/page.tsx`):** Added `r.thread_id` to the search filter and updated placeholder to `Search runs by query, run ID, or conversation...` so users can filter all execution runs by conversation thread.

### Removed
- **Legacy Multi-Agent Run Logs (`logs/runs/`):** Pruned obsolete historical run snapshots from deprecated multi-agent routing (`librarian`, `career`).
