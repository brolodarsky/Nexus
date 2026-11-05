---
type: patch
---
### Changed
- **HITL Review Queue & GUI Inspector Tile Hierarchy (`gui/src/app/hitl/page.tsx`):**
  - Promoted the tool name / action (`modify`, `create`, `move`, `delete`, `write_file`) to the colored top header position across review queue tiles and inspector badges, rendering with semantic color theming (`getActionTheme`: rose for deletions, emerald for creations, violet for relocations, and amber for modifications).
  - Maintained the primary filename header intact (`{target_file} → {destination_file}` or `{target_file}`).
  - Relocated the ticket number (`Ticket #{id}`) down into the secondary metadata row where the action type was previously placed, preserving clean alignment alongside agent role, agent ID, conversation ID, and thread provenance pills.
  - Updated collapsed queue rail tooltips to reflect the action-first hierarchy (`[{action}] {file} · Ticket #{id}`).
