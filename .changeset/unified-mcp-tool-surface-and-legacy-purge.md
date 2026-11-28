---
type: minor
---
### Added
- Built a stdio-safe unified `FastMCP` server (`src/nexus/mcp/server.py`, registered as `nexus-mcp` in `pyproject.toml`) exposing the exact canonical `nexus.agent.graph.TOOLS` registry (`30` tools + `nexus://instructions/master` resource), with automatic `mcp_session` HITL/cache execution context, `stdout -> stderr` redirection on tool execution, and `NEXUS_STDIO_MCP=1` stderr Loguru routing (`src/nexus/core/logger.py`).
- Added Antigravity workspace plugin bundle `.agents/plugins/nexus/{plugin.json,mcp_config.json}` for zero-config local MCP registration.
- Promoted standalone capabilities into first-class typed `@tool` definitions in `src/nexus/shared_tools/shared.py` and `CORE_TOOLS` (`src/nexus/agent/runtime.py`): `read_webpage`, `get_youtube_transcript` (auto-caching under `cache://youtube/<id>` via `fetch_youtube_transcript()`), `modify_emails`, `trash_emails`, `create_email_draft`, `render_resume_documents`, `ingest_phone_chat`, and `export_agent_conversation`.
- Added `tests/test_unified_mcp_and_tools.py` verifying 1:1 `TOOLS` vs. `FastMCP` parity, slimmed schema+description token footprint, `stdout` JSON-RPC safety, and all newly promoted tools.

### Changed
- Slimmed `@tool` docstrings across `src/nexus/shared_tools/shared.py` and `src/nexus/agent/subagent.py` (while preserving all `#` educational comments), reducing schema+description size across all 30 unified tools below the legacy 23-tool prompt budget.
- Updated `AGENTS.md`, `Vault/Master Instructions.md`, `README.md`, `Vault/1. Core/1.2. Personal Knowledge Management (PKM)/Protocol - Email Triage.md`, `Vault/2. Health/Section Instructions.md`, `Vault/3. Operations/3.1. Career Strategy & Revenue/Section Instructions.md`, and Engineering documentation to reflect the single unified tool surface and native IDE vs. `nexus` MCP split.
- Updated `gui/src/app/chat/page.tsx` mid-turn capture badge refresh triggers to watch `get_youtube_transcript` in place of `run_shared_tool_cli`.

### Removed
- Removed `src/nexus/shared_tools/medical_xml_parser.py` and `src/nexus/shared_tools/generate_podcast.py` (plus `.podcast_history.json` and unused `edge-tts`/`defusedxml` dependencies).
- Removed broken `/api/vault/podcast/generate` and `/api/vault/podcast/download` routes from `src/nexus/api/routers/vault.py`, `has_audio` from `VaultEntry`, `/api/vault/podcast/download` from `QUERY_TOKEN_EXACT_PATHS` (`src/nexus/api/security.py`), and Podcast Studio UI from `gui/src/app/vault/page.tsx`, `gui/src/app/tools/page.tsx`, and `gui/src/lib/api/vault.ts`.
- Removed `run_shared_tool_cli`, `src/nexus/core/tool_catalog.py` (`{shared_tools}` placeholder injection in `src/nexus/core/engine_constitution.py`), `get_read_note_tool`, `get_propose_write_tool`, `CONSTITUTION_PATH`, and `get_engine_constitution`.
