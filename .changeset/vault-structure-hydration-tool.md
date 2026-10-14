---
type: minor
---
### Added
- **Deterministic Vault Structure Hydration Tool (`get_vault_structure`):** Standardized and exported `get_vault_structure(path=None)` in `src/nexus/shared_tools/shared.py` as a shared cross-agent tool for recursive folder orientation (`path=None`) and targeted subtree drill-downs (`path="<section>"`).
- **Dynamic Vault Structure Prompt Hydration:** Added `{vault_structure}` placeholder to `Vault/Playbook.md` and wired `src/nexus/core/engine_constitution.py` to deterministically inject the live Vault folder tree into the engine constitution prefix at runtime.
