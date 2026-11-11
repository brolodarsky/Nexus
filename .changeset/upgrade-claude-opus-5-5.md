---
type: minor
---
### Changed
- Upgraded the Anthropic Claude strong-tier model default from Claude Opus 4.5 (`claude-opus-4-5`) to Claude Opus 5.5 (`claude-opus-5-5`) in `src/nexus/core/config.py` and `src/nexus/core/constants.py`.
- Extended `_normalize_anthropic_model_name()` to normalize `claude-opus-5.5`, `opus-5.5`, `opus-5-5`, and `opus 5.5` to canonical `claude-opus-5-5` while preserving `claude-opus-4-5` backwards-compatibility for legacy invocations.
- Updated `get_available_models()` so the side-by-side Anthropic Strong card reflects `Opus 5.5 (claude-opus-5-5)`.
- Added `claude-opus-5-5` and `claude-opus-5.5` to `MODEL_PRICING` in `src/nexus/core/cost.py` with $4.00 input, $0.20 cached (95% prompt cache discount), and $20.00 output rates per 1M tokens. Preserved legacy `claude-opus-4-5` pricing in the catalog for retrospective auditing and re-routed fuzzy "opus" matches to `claude-opus-5-5`.
- Updated `FALLBACK_MODEL_OPTIONS` in `gui/src/components/chat/types.ts` and `gui/src/lib/api/agents.ts` to present Opus 5.5 (`claude-opus-5-5`). Enhanced `extractTurnCost()` to differentiate between Opus 5.5 ($4/$0.20/$20) and legacy Opus 4.5 ($5/$0.50/$25) when estimating token costs.
- Updated reasoning model backfill targets in `scripts/audit_run_costs.py` and comments in `src/nexus/agent/graph.py` to reference `claude-opus-5-5`.
- Updated test suites in `tests/test_cost_tracking.py` and `tests/test_model_config_and_resilience.py` to validate `claude-opus-5-5` pricing, catalog exposure, and ChatAnthropic client instantiation (213/213 full suite passing).
