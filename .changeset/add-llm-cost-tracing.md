---
type: minor
---

### Added
- **LLM Cost Estimation & Pricing Engine (`src/nexus/core/cost.py`):** Created a dedicated inference cost calculation engine with model-specific pricing tables for Google Gemini (`gemini-3.8-flash`, `gemini-4-argon`, Pro/Flash families) and OpenAI (`gpt-5.4-mini`, `gpt-5.6-terra`, `gpt-5.6-sol`, o-series). Supports prompt context caching discount accounting (e.g. 75% Gemini discount, 50% OpenAI discount).
- **Run Snapshot Cost Telemetry (`src/nexus/core/run_logger.py` & `src/nexus/agent/graph.py`):** Added real-time cost calculation to `_log_token_usage()`, emitted in live trace events and terminal logs. Updated `log_run()` to compute and persist root and per-subagent `cost_usd` and `cache_savings_usd` in `logs/runs/*.json` snapshots and `list_runs()` summaries.
- **Run Cost Audit & Backfill Utility (`scripts/audit_run_costs.py`):** Built a standalone CLI tool that scans all persisted execution snapshots in `logs/runs/`, reports total spend ($14.02 across 150 historical runs, 49M tokens, $16.50 saved via prompt caching with an 82.4% cache hit rate), shows breakdowns by model, and includes `--backfill` to retroactively stamp `cost_usd` into legacy snapshots.
- **Control Panel Cost Badges (`gui/`):** Displayed estimated dollar inference costs on assistant chat message bubbles (`ChatMessageItem.tsx`), quick-stats pills and run ledger summaries in the Agent Audit Log (`/audit`), and individual agent node execution cards in `AgentTraceVisualizer.tsx`.
- **Unit Test Coverage (`tests/test_cost_tracking.py`):** Added 5 automated tests validating rate lookups, prompt caching discounts, zero-token edge cases, and run snapshot cost persistence (86 passing engine tests).
