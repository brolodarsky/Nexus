---
type: patch
---
### Changed
- Migrated `src/nexus/core/ENGINE_CONSTITUTION.md` to `Vault/Playbook.md` (`aliases: [Vault Playbook, Root Playbook, Engine Constitution]`) and updated `src/nexus/core/engine_constitution.py` and `AGENTS.md` to load the root Vault Playbook directly from `Vault/Playbook.md`.
- Consolidated `.agents/rules/zero_sycophancy.md` into `Vault/Playbook.md` §11 and removed build-level implementation details from the Resident constitution.
- Simplified `.agents/skills/cognitive_boundary_flush/SKILL.md` and fixed stale `Plan.md` path in `.agents/skills/career_counselor/SKILL.md`.
- Fixed stale module paths in `README.md` (`vault_reader.py`, `shared.py`, `graph.py`).

### Removed
- Removed `src/nexus/core/ENGINE_CONSTITUTION.md` (moved to `Vault/Playbook.md`) and `.agents/rules/zero_sycophancy.md` (folded into `Vault/Playbook.md` §11).
