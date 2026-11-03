---
type: minor
---
### Added
- **Agentic Web Search Engine (`src/nexus/shared_tools/web_search.py` & `search_web` in `shared.py`):** Added `web_search.py` (`execute_web_search`, `format_search_results_as_markdown`, and `[CLI]` entrypoint `python -m nexus.shared_tools.web_search`) backed by `langchain-tavily` (`TavilySearch`) with search depth (`basic` / `advanced`), topic filtering (`general` / `news` / `finance`), domain whitelisting/blacklisting (`--domain`, `--exclude-domain`), and snippet length capping. Wrapped as `@tool def search_web` in `src/nexus/shared_tools/shared.py` (with a Context Hygiene Directive for subagent delegation) and bound into `CORE_TOOLS` in `src/nexus/agent/graph.py` so both `NexusAgent` and spawned subagents have native live web search.
- **Web Search Unit Test Suite (`tests/test_web_search.py`):** Added 5 unit tests covering empty-query and missing-key guards, parameter clamping, result normalization, Markdown formatting/truncation, and `CORE_TOOLS` graph binding.

### Changed
- **Vault Instruction Sets & Project Documentation (`Master Instructions.md`, `Section Instructions.md`, `README.md`, `Project - *.md`):** Updated `Master Instructions.md`, `2. Health/Section Instructions.md`, `3.1. Career Strategy & Revenue/Section Instructions.md`, and `6. Engineering/Section Instructions.md` to prompt `search_web` for live market/company verification, peer-reviewed clinical literature lookups, and frontier library/benchmark verification; reconciled doc-vs-disk drift across `Project - Nexus Agentic Engine.md`, `Project - Nexus GUI.md`, `Project - Nexus Demo.md`, and `README.md`.
