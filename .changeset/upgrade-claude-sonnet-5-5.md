---
type: patch
---
### Added
- Added **Claude Haiku 5.5** (`claude-haiku-5-5`) as the Anthropic `low` / fast tier across `src/nexus/core/config.py`, `src/nexus/core/constants.py`, `scripts/audit_run_costs.py`, `gui/src/components/chat/types.ts`, and `gui/src/lib/api/agents.ts`, establishing a 3-tier Anthropic lineup (`Opus 5.5` strong / `Sonnet 5.5` medium / `Haiku 5.5` low) with `temperature` omitted on `haiku-5` models.
- Added `claude-haiku-5-5` / `claude-haiku-5.5` tiered pricing (`$0.10` input / `$0.01` cached / `$0.50` output per 1M tokens up to 100k input tokens, stepping up 5x to `$0.50` / `$0.05` / `$2.50` above 100k tokens) to `src/nexus/core/cost.py` and `extractTurnCost()` in `gui/src/components/chat/types.ts`.

### Changed
- Upgraded default Anthropic `medium` tier model from retiring `claude-sonnet-4-5` to `claude-sonnet-5-5` across `src/nexus/core/config.py`, `src/nexus/core/constants.py`, `scripts/audit_run_costs.py`, `gui/src/components/chat/types.ts`, and `gui/src/lib/api/agents.ts` (keeping `claude-opus-5-5` as the strong tier).
- Added `claude-sonnet-5-5` / `claude-sonnet-5.5` pricing (`$2.00` input / `$0.10` cached / `$10.00` output per 1M tokens) to `src/nexus/core/cost.py` and `extractTurnCost()` in `gui/src/components/chat/types.ts`, while retaining legacy `claude-sonnet-4-5` (`$3/$0.30/$15`) and `claude-opus-4-5` (`$5/$0.50/$25`) entries for accurate historical run audits.
- Added automatic `localStorage` migration in `gui/src/app/chat/page.tsx` mapping retired `claude-sonnet-4-5` / `claude-opus-4-5` selections to `claude-sonnet-5-5` / `claude-opus-5-5` on model catalog load.
