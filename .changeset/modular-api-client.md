---
type: patch
---
### Changed
- **Modular Frontend API Client Layer (`gui/src/lib/api/`):** Refactored the monolithic 595-line `gui/src/lib/api.ts` into a clean modular domain architecture mirroring the FastAPI backend routers:
  - `client.ts`: Base HTTP client, `apiFetch` wrapper, and `ApiError` hierarchy.
  - `stream.ts`: Low-level SSE parser and real-time execution `TraceEvent` streaming engine (`askBrainStream`).
  - `agents.ts`: Swarm agent status, conversations, chat execution, and model catalog endpoints.
  - `vault.ts`: Vault tree browsing, note fetching, note metadata summaries, and podcast TTS synthesis.
  - `hitl.ts`: Human-in-the-Loop approval, rollback, rebase, and conflict resolution type guards.
  - `board.ts`: Shared agent blackboard bulletin board endpoints.
  - `index.ts`: Barrel export preserving 100% backwards compatibility for `@/lib/api` imports across all UI pages.

