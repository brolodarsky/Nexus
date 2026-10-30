---
type: patch
---
### Fixed
- Calibrated real-time LLM cost estimation in `src/nexus/core/cost.py` for Gemini Pro and Argon models exceeding 128k context tokens, applying Google's 2x tier step-up pricing ($2.50/1M prompt, $0.625/1M cached, $10.00/1M output).
- Upgraded `scripts/audit_run_costs.py` to infer model names and capability tiers from agent reasoning strings on legacy snapshots and parse token usage from historical trace telemetry.
- Backfilled 83 historical run snapshots in `logs/runs/` with accurate token counts and tiered pricing.

### Added
- Added unit tests in `tests/test_cost_tracking.py` verifying context step-up thresholds and rates for models with large context windows.
