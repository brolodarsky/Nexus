---
type: patch
---
### Removed
- **Vestigial `AGENT_REGISTRY` & Status Route (`src/nexus/api/routers/agents.py`):** Removed in-memory `AGENT_REGISTRY`, `AgentStatusEntry` schema, `GET /api/agents/status` route, and per-turn timestamp update loops left over from the pre-Universal-Agent multi-agent swarm architecture.
- **Orphaned `AgentCard` Component & Client Methods (`gui/src/`):** Deleted unmounted `AgentCard.tsx` component and removed unused `AgentStatus` interface and `getAgentStatus()` fetch helper from `gui/src/lib/api/agents.ts`.
