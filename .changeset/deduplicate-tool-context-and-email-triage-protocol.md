---
type: patch
---
### Changed
- Extracted cross-Vault email sweep and triage rules from `Vault/1. Core/1.1. Philosophy & Personal North Star/Section Instructions.md` and `Vault/3. Operations/3.1. Career Strategy & Revenue/Section Instructions.md` into an on-demand autopoietic note (`Vault/1. Core/1.2. Personal Knowledge Management (PKM)/Protocol - Email Triage.md`), linked from `Vault/Table of Contents.md`, `Vault/Master Instructions.md`, and `fetch_emails`.
- Removed duplicated bound-tool signatures and orchestration prose from `Vault/Master Instructions.md` and trimmed parent delegation directives from `search_web` and `read_browser_tabs` docstrings in `src/nexus/shared_tools/shared.py`.
- Filtered `get_shared_tools_catalog()` in `src/nexus/core/tool_catalog.py` to include only runnable `[CLI]` modules (`__main__` entrypoint), excluding non-CLI library modules (`shared.py`, `summarizer.py`, `resume_engine.service`).

### Removed
- Removed the duplicate `@tool def get_vault_structure` alias from `src/nexus/shared_tools/shared.py` and `CORE_TOOLS` in `src/nexus/agent/graph.py` (retaining `get_directory_structure` and the FastAPI `/api/vault/structure` endpoint).
