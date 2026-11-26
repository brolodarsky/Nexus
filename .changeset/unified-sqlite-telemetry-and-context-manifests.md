---
type: minor
---
### Added
- Pre-hash API key / Bearer token scrubber (`scrub_secrets`, `scrub_structure`) and deterministic `approx_token_count` (`ceil(chars / 4)`) helper in `src/nexus/core/secret_scrubber.py`.
- Content-addressed SHA-256 context manifest builders (`src/nexus/core/context_telemetry.py`) capturing full injected context across Head Agent `agent_start`, Subagent `agent_start` (post-hydration `# Pre-Hydrated Disk Context` + auto-discovered `Section Instructions.md`), and every wire-level `llm_call` turn.
- Unified SQLite tables in `src/nexus/core/chats_db.py` (`trace_blobs`, `runs`, `trace_events`, `run_blob_refs`, `upload_refs`, `thread_messages`, `schema_migrations`, `PRAGMA foreign_keys = ON`) plus deterministic reference-counted GC (`gc_unreferenced_telemetry`) and one-time legacy importer (`migrate_legacy_telemetry_if_needed`).
- FastAPI lazy blob endpoints `GET /api/agents/trace-blobs/{blob_hash}` and `POST /api/agents/trace-blobs/batch` in `src/nexus/api/routers/agents.py`.
- Folded, lazy-loaded `ContextManifestInspector` (with `Summon Full Context` + `Copy Full Context` and `X chars · ~Y tok` estimates across all character-count displays) in `gui/src/components/AgentTraceVisualizer.tsx`, `gui/src/lib/api/agents.ts`, and `gui/src/app/audit/page.tsx`.
- Global `tests/conftest.py` SQLite isolation and `tests/test_unified_telemetry_and_context.py` regression suite.

### Changed
- Replaced LangGraph's `memory.sqlite` (`SqliteSaver`) and per-turn `logs/runs/*.json` dumps with canonical lossless `thread_messages` persistence and live incremental `trace_events` streaming in `src/nexus/agent/graph.py`, `src/nexus/agent/api.py`, `src/nexus/core/chat_branching.py`, `src/nexus/core/trace.py`, and `src/nexus/core/run_logger.py`.
- Updated `scripts/audit_agent_health.py` and `scripts/audit_run_costs.py` to query SQLite `chats.db` by default (preserving optional `--runs-dir` override for external JSON directories).
