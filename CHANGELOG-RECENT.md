# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [3.0.0] - 2026-10-26

### Added
- Made the global navigation sidebar (`gui/src/components/Sidebar.tsx`) collapsible into a compact icon rail with tooltips, Ctrl+B hotkey, and localStorage state persistence.
- Made the HITL review queue sidebar (`gui/src/app/hitl/page.tsx`) collapsible into a slim ID switcher rail, and added accordion collapse toggles to the Recently Applied undo drawer and Agent Reasoning panel.
- Made the Brain Explorer directory tree menu (`gui/src/app/vault/page.tsx`) collapsible into a slim rail and added accordion collapse to the Podcast Studio control panel.
- Made the Ask Brain conversation history menu (`gui/src/app/ask/page.tsx`) collapsible into a compact switcher rail, and added a direct collapse toggle to the Shared Agent Blackboard drawer.
- Added collapsible toggles to the Agent Fleet grid and Quick Actions launcher menu on the Mission Control dashboard (`gui/src/app/page.tsx`).
- Created `Vault/3. Operations/3.1. Career Strategy & Revenue/Playbook.md` as the canonical Section 3.1 operational guide, folding in the Career Strategy & Principal Advisor persona, resume rendering (`render.js` page-fill targets), job requirement ingestion (`Employer Skill Requirements.md`), compensation/interview calibration, and section asset routing.
- **Shared Inter-Agent Blackboard (`blackboard.py`, `/api/board`, & GUI Bulletin Drawer):** Created `src/nexus/core/blackboard.py` (`blackboard.db`), added `post_to_board` and `read_board` LangChain tools in `src/nexus/shared_tools/shared.py`, wired automatic subagent bulletin publishing into `spawn_subagent` in `src/nexus/agent/graph.py`, mounted `/api/board` in `src/nexus/api/routers/board.py`, and added a live collapsible Subagent Blackboard drawer with channel filters (`all`, `email`, `calendar`, `vault`, `mission`) in `gui/src/app/ask/page.tsx`.
- **Cumulative Overlay Stacking in HITL Queue (`hitl_queue.py` & `shared.py`):** Added `get_pending_for_file()` and updated `add_transaction()`, `modify_file()`, and `read_file()` so multiple edits to the same Vault note automatically stack onto a single cumulative pending review card in `hitl.db` (preserving the true on-disk baseline and merging reasoning bullets) and `read_file` automatically displays staged pending content.
- **Native Gemini 3+ (`ChatGoogleGenerativeAI`) & Tiered Model Routing (`get_chat_model`):** Added `langchain-google-genai` and `get_chat_model(tier)` in `src/nexus/core/constants.py` with Gemini/tiered configuration in `src/nexus/core/config.py` (`gemini_api_key`, `google_api_key`, `ai_provider`, `nexus_primary_tier="strong"` defaulting to Astra / `gemini-4-argon`, `nexus_subagent_tier="low"` defaulting to Flash / `gemini-3.8-flash`). Uses Google's native `ChatGoogleGenerativeAI` client so Gemini 3+ `thought_signature` tokens (`__gemini_function_call_thought_signatures__` and structured content block signatures) are automatically preserved across multi-step tool loops and cross-model conversation history.
- **Structured Content Block Text Extractor (`extract_message_text`):** Added `extract_message_text(msg)` in `src/nexus/agent/graph.py` (and wired into `api.py` and `summarizer.py`) so Gemini's structured signature content blocks remain intact in `SqliteSaver` checkpointer state while clean Markdown strings are returned to the GUI and CLI.
- **Live Token & Prompt Cache Telemetry (`_log_token_usage`):** Added automatic logging of input tokens, cached prompt token hits (`cache_read`), and output tokens to the console and SSE trace bus in `src/nexus/agent/graph.py`.
- **Rich GFM & Obsidian `[[Wiki-Link]]` Chat GUI Renderer (`gui/src/app/ask/page.tsx`):** Installed `react-markdown` and `remark-gfm` and built `MarkdownMessage` + `preprocessObsidianMarkdown()` in `gui/src/app/ask/page.tsx`, replacing raw `<pre>` output with styled headings, lists, task checkboxes (`- [ ]`), glassmorphic tables, blockquotes, syntax blocks, and glowing cyan Vault wiki-link pills.
- Multi-account support in `src/nexus/shared_tools/gmail_engine.py`:
  - Dynamic token filename resolution (`token_gmail.json` for default backward compatibility, `token_gmail_<alias>.json` for named accounts).
  - Configured account discovery via `list_available_accounts()`.
  - New `--account <alias|all>` and `--accounts` CLI flags for inspecting and targeting specific or all accounts.
  - Cross-inbox search, listing, and threading aggregation (`--account all`).
- Added HITL commit integrity (`commit_transaction`, `rollback_transaction`, `three_way_merge`, `rebase_transaction`, `get_recent_revisions`) and a pre-commit `revisions` snapshot table in `src/nexus/core/hitl_queue.py`.
- Added `POST /api/hitl/{tx_id}/rebase`, `POST /api/hitl/{tx_id}/rollback`, `GET /api/hitl/revisions/recent`, and structured HTTP 409 (`stale_base` / `merge_conflict`) responses in `src/nexus/api/routers/hitl.py`.
- Added Pre-Commit Preview tab, 3-Way Stale-Base Conflict Viewer, Rebase/Force actions, and Recently Applied Undo list in `gui/src/app/hitl/page.tsx` plus shared `gui/src/components/MarkdownMessage.tsx`.
- Added 20 unit and FastAPI integration tests in `tests/test_hitl_commit.py` (`pytest` dev dependency).
- **Universal `NexusAgent` (`src/nexus/agent/`):** Implemented the Single Universal Agent LangGraph runtime (`src/nexus/agent/graph.py` and `src/nexus/agent/api.py`) with dynamic `inject_root_instructions()` injection, pre-bound core Vault/HITL/comms tools, on-demand CLI execution (`run_shared_tool_cli`), prompt-driven subagent delegation (`spawn_subagent(task_prompt: str)`), and a deterministic $\le 5$ tool-iteration circuit breaker.
- **Surgical File Modification (`modify_file`) & Creation (`create_file`):** Replaced full-file rewrites on existing Vault notes with exact `target` $\rightarrow$ `replacement` block patching in `src/nexus/shared_tools/shared.py` (with CRLF/LF normalization) that stages complete pre/post diffs to the SQLite HITL queue (`hitl.db`). Added line-range slicing (`start_line`, `end_line`) and `resolve_vault_note_path` to `vault_reader.py`.
- Added `get_recent_modifications` to `src/nexus/shared_tools/vault_reader.py` along with a `[CLI]` entrypoint (`python -m nexus.shared_tools.vault_reader --today` / `--hours` / `--since` / `--path` / `--tree` / `--read` / `--search`) to deterministically list Vault documents created or edited within a time window.
- Added `@tool def get_recent_modifications` wrapper in `src/nexus/shared_tools/shared.py` and bound it to the Librarian agent (`src/nexus/agents/librarian/tools.py` & `graph.py`).
- Enhanced `src/nexus/interfaces/telegram.py` with automatic 4,000-character message chunking (`_split_telegram_message`), non-blocking `asyncio.to_thread` execution with a live typing heartbeat (`_keep_typing`), per-chat conversation thread management (`/new`), and remote HITL queue commands (`/pending`, `/approve <id|all>`, `/reject <id>`).

### Changed
- **Compact Directory Tree & Simplified Resident Hydration (`vault_reader.py`, `engine_constitution.py`, `AGENTS.md`):** Added `max_depth` support with inline leaf-folder bracket formatting (`[sub1, sub2]`) to `get_directory_tree()`, compressing `{vault_structure}` from ~100 lines to 28 lines while preserving all 3rd-level section headings, and stripped Obsidian YAML frontmatter/navigation links in `get_engine_constitution()`. Simplified `AGENTS.md` Role A instructions so IDE agents read `Vault/Playbook.md` directly alongside the hydrated structure/tools output.
- Standardized Self-Managing Document contracts (`# Document Playbook` headers) into YAML frontmatter `playbook:` properties across `Vault/Playbook.md`, `AGENTS.md`, and active living Vault documents, strictly separating document maintenance/archival rules from substantive domain content.
- Consolidated all Resident Vault skills and workflows into `Vault/Playbook.md`, `Vault/1. Core/1.1. Philosophy & Personal North Star/Playbook.md`, `Vault/2. Health/Playbook.md`, `Vault/3. Operations/3.1. Career Strategy & Revenue/Playbook.md`, and `Protocol - Career Maintenance.md`, reserving `.agents/skills/` (`conventional_commits`, `maintain_project_docs`, `skill_creator`, `workflow_creator`) and `.agents/workflows/` (`/release`) strictly for Builder (repo/engine) operations.
- **Subagent Cost Tiering & Parallel Swarming (`spawn_subagent`):** Updated `spawn_subagent(task_prompt: str, model_tier: ModelTier = "low")` to default to the fast, low-cost model tier (`"low"`) while allowing `"medium"` or `"strong"` overrides, and updated `Vault/Master Instructions.md` and tool docstrings to instruct parallel multi-tool/subagent fan-out in a single turn.
- **Prompt Caching Prefix Isolation:** Reordered `Vault/Master Instructions.md` so static constitutional instructions, `{shared_tools}`, and `{vault_structure}` form a contiguous static prefix, and updated `inject_root_instructions(cache_stable=True)` in `src/nexus/core/engine_constitution.py` to align `{current_time}` to the hour boundary (`YYYY-MM-DD HH:00`) at the tail so second-by-second timestamps never invalidate provider KV prompt caches across multi-step tool loops.
- **Dynamic Per-Turn Model Resolution:** `get_chat_model()` and `call_model()` now re-read `EngineSettings()` dynamically on every turn (with `timeout=90, max_retries=2`), allowing `.env` model/tier edits without editing `.py` files or triggering a `uvicorn --reload` worker kill mid-request.
- `fetch_emails` tool in `src/nexus/shared_tools/shared.py`: added `account: str = "all"` argument to support querying across all authenticated Gmail accounts by default or filtering to a specific alias.
- Updated `README.md` and `Vault/6. Engineering/6.1. Projects/6.1.2. Agentic R&D/Project - Nexus Agentic Engine/Project - Nexus Agentic Engine.md` with multi-account documentation and build logs.
- **Renamed `get_engine_constitution()` $\rightarrow$ `inject_root_instructions()`:** Standardized root instruction hydration in `src/nexus/core/engine_constitution.py` (retaining `get_engine_constitution` as a backward-compatible alias).
- **Rewired FastAPI, CLI, Voice, Telegram & Evals:** Connected `/api/agents/ask`, `/api/agents/ask/stream`, `src/nexus/main.py`, `src/nexus/interfaces/telegram.py`, `src/nexus/interfaces/voice.py`, `src/nexus/evals/runner.py`, and GUI agent badges directly to `NexusAgent`.
- Renamed `Vault/Playbook.md` to `Vault/Master Instructions.md`, section-level `Playbook.md` files to `Section Instructions.md`, and YAML frontmatter `playbook:` properties to `instructions:`.
- Updated `src/nexus/core/engine_constitution.py`, `src/nexus/core/tool_catalog.py`, `AGENTS.md`, `README.md`, `Concept - The Nexus Execution Lifecycle.md`, and `Project - Nexus Agentic Engine.md` to align with the Single Universal Agent (`NexusAgent`) + on-demand tool loading + dynamic `spawn_subagent` architecture.
- Updated default `openai_model` fallback in `src/nexus/core/config.py` to `gpt-6-luna`.

### Fixed
- **AI Request Timeout & Retry Resilience (`config.py` & `constants.py`):** Replaced hardcoded `timeout=90` and `max_retries=2` in `src/nexus/core/constants.py` with configurable `ai_request_timeout: int = 300` (default 300s / 5 minutes) and `ai_max_retries: int = 3` in `src/nexus/core/config.py` (`EngineSettings`). Gives thinking/reasoning models (such as `gemini-4-argon`) full latency headroom (5 minutes) and retry tolerance on deep multi-turn synthesis tasks.
- **Graceful Tier Fallback on Deadline Exceeded (`graph.py`):** Added resilient error recovery in `call_model()` (`src/nexus/agent/graph.py`). If the primary model tier (`gemini-4-argon` / `strong`) encounters a `504 DEADLINE_EXCEEDED` or request timeout after retries, `NexusAgent` automatically logs a trace alert and executes a seamless fallback to the low-latency tier (`gemini-3.8-flash` / `low`), preserving the active session and completing the turn instead of crashing.
- **Architect-Drafter Delegation (`shared.py`, `graph.py` & `Master Instructions.md`):** Reinforced `read_file` with a context-hygiene threshold directive against multi-file stuffing in primary threads, and expanded `spawn_subagent` and `Master Instructions.md` with the Architect-Drafter pattern: the Commander formulates strategy and exact replacement content, delegating the `read_file` + `modify_file` execution tool loop to isolated subagents to stage changes to HITL without compounding raw note diffs into the parent context.
- **Diagnostic Guidance for Chat Invocations (`api.py`):** Enhanced error reporting in `run_nexus_agent_with_trace()` (`src/nexus/agent/api.py`) to demystify provider deadline timeouts and provide actionable guidance to the user.
- **Obsidian `[[Wiki-Link]]`, `.md` Note Title & LaTeX Arrow Rendering (`MarkdownMessage.tsx`):** Fixed an issue where backtick-wrapped wikilinks (`\`[[Plan]]\``) and backticked Markdown note titles (`\`1.1. Section Instructions.md\``, `\`Plan.md\``) rendered inconsistently as raw link syntax or split inline `<code>` spans instead of unified cyan `VaultNotePill` badges. Added inline LaTeX arrow/operator normalization (`$\leftrightarrow$` $\rightarrow$ `↔`, `$\rightarrow$` $\rightarrow$ `→`, `$\leftarrow$` $\rightarrow$ `←`), `.md` extension stripping on note pills, and `inline-block` border integrity on inline code tags.
- **Summarizer Turn-Boundary Pruning & Self-Healing History (`summarizer.py` & `_sanitize_messages`):** Updated `summarize_conversation()` to snap message pruning cut-points to `HumanMessage` boundaries (never slicing mid-turn inside a tool loop), and enhanced `_sanitize_messages()` in `src/nexus/agent/graph.py` to strip leading orphaned `ToolMessage` / `AIMessage(tool_calls)` fragments and anchor standalone `AIMessage` responses so Gemini's strict `user -> model` turn ordering is never violated.
- **Historical Calendar Inspection (`get_calendar_schedule`):** Added `days_back: int = 0` parameter to `get_calendar_schedule` in `src/nexus/shared_tools/shared.py` so `NexusAgent` can directly audit yesterday's calendar when rolling `Plan.md` and `Events/YYYY/` receipts forward.
- **Gemini Tool Schema Compatibility (`run_shared_tool_cli`):** Renamed parameter `args` $\rightarrow$ `cli_args` on `run_shared_tool_cli` in `src/nexus/shared_tools/shared.py` to prevent Pydantic v2 from emitting an untyped `v__args` property that caused Gemini `GenerateContentRequest` schema validation errors.
- Fixed `src/nexus/core/seed_hitl.py` import path (`nexus.core.hitl_queue`) and post-action selection state in `gui/src/app/hitl/page.tsx`.
- Fixed race condition in concurrent HITL tool calls (`modify_file` and `create_file` executed across parallel LangGraph `ToolNode` worker threads) modifying the same Vault document in a single LLM turn.
- Introduced `get_file_mutation_lock` in `src/nexus/core/hitl_queue.py` (`threading.RLock` per normalized target note) to strictly serialize in-flight checks, surgical replacements, and cumulative overlay stacking so concurrent edits coalesce cleanly into a single review card.
- Added concurrency test `test_concurrent_modify_file_stacks_cleanly_into_single_transaction` in `tests/test_hitl_commit.py`.

### Removed
- Retired all 6 IDE-locked Resident skills (`generate_obsidian_note`, `cleanup_orphans`, `project_work`, `archive_project`, `cognitive_boundary_flush`, `career_counselor`) from `.agents/skills/` and all 14 Resident workflows (`add_job_requirement`, `archive_contact`, `ask_brain`, `audit_career`, `audit_inbox`, `capture_content`, `create_new_note`, `create_project`, `distill_learning`, `flush`, `ingest_medical_record`, `plan_activity`, `render_resume`, `weekly_review`) from `.agents/workflows/`.
- **Mid-Session Message Pruning (`summarizer_node`):** Removed `summarizer_node` (and `SystemMessage` summary mutation) from `src/nexus/agent/graph.py` so `route_after_agent` routes directly to `END` when tool calls finish. Preserves 100% lossless conversation history within event-bounded threads and prevents `RemoveMessage` from invalidating the left-to-right provider KV prompt cache across multi-turn sessions.
- **Custom Tool-Iteration Circuit Breaker (`MAX_TOOL_ITERATIONS_PER_TURN`):** Removed the custom step-counting circuit breaker from `src/nexus/agent/graph.py` and `Vault/Master Instructions.md`, allowing multi-file Vault workflows to converge naturally while relying on LangGraph's built-in `recursion_limit` for infinite-loop protection.
- **Retired Legacy Multi-Agent Packages:** Removed `src/nexus/agents/router/`, `src/nexus/agents/career/`, and `src/nexus/agents/librarian/`.

## [2.15.0] - 2026-10-16

### Added
- `src/nexus/shared_tools/gmail_engine.py`: Gmail REST API v1 data layer + CLI (native Gmail search, read/thread as markdown, labels, archive, trash, drafts). Scope `gmail.modify`; token isolated in `.secrets/token_gmail.json`. No send function by design.
- `src/nexus/core/tool_catalog.py`: static `ast`-based catalog of `src/nexus/shared_tools/` for prompt hydration.
- `{shared_tools}` placeholder and `## Shared Tools` section in `Vault/Playbook.md`, hydrated by `engine_constitution.py`.
- `python -m nexus.core.engine_constitution` entrypoint that prints the fully hydrated Playbook.
- Module docstrings for `summarizer.py`, `generate_podcast.py`, `medical_xml_parser.py`.
- **Deterministic Vault Structure Hydration Tool (`get_vault_structure`):** Standardized and exported `get_vault_structure(path=None)` in `src/nexus/shared_tools/shared.py` as a shared cross-agent tool for recursive folder orientation (`path=None`) and targeted subtree drill-downs (`path="<section>"`).
- **Dynamic Vault Structure Prompt Hydration:** Added `{vault_structure}` placeholder to `Vault/Playbook.md` and wired `src/nexus/core/engine_constitution.py` to deterministically inject the live Vault folder tree into the engine constitution prefix at runtime.

### Changed
- Consolidated and upgraded health, clinical research, and psychological architecture guidelines into `Vault/2. Health/Playbook.md` as the Vault-native single source of truth.
- Router `fetch_emails` now calls `gmail_engine` directly (Gmail search syntax, optional `count`, bodies capped at 4,000 chars) instead of delegating to an Email Agent subgraph.
- `AGENTS.md`: Resident agents inject the hydrated Playbook via the engine instead of reading the raw template.
- Migrated `src/nexus/core/ENGINE_CONSTITUTION.md` to `Vault/Playbook.md` (`aliases: [Vault Playbook, Root Playbook, Engine Constitution]`) and updated `src/nexus/core/engine_constitution.py` and `AGENTS.md` to load the root Vault Playbook directly from `Vault/Playbook.md`.
- Consolidated `.agents/rules/zero_sycophancy.md` into `Vault/Playbook.md` §11 and removed build-level implementation details from the Resident constitution.
- Simplified `.agents/skills/cognitive_boundary_flush/SKILL.md` and fixed stale `Plan.md` path in `.agents/skills/career_counselor/SKILL.md`.
- Fixed stale module paths in `README.md` (`vault_reader.py`, `shared.py`, `graph.py`).
- Streamlined `AGENTS.md` into a lean standing operational contract covering agent role routing, safety boundaries, execution environment rules, and git/changeset policy.
- Migrated granular coding standards and engineering invariants (tool factories, ephemeral prompt checkpointer hygiene, absolute imports, educational commenting) into `Project - Nexus Agentic Engine.md`.

### Removed
- Deleted legacy `.agents/skills/analyze_health/` (and `references/medical_research_protocol.md`) and `.agents/skills/analyze_psych/` skill directories after folding their rules into `Vault/2. Health/Playbook.md`.
- Email Agent subgraph (`src/nexus/agents/email/`, including its evals).
- IMAP/XOAUTH2 email client and `src/nexus/shared_tools/read_email.py`.
- `email_address` / `imap_*` settings from `core/config.py`.
- Removed `src/nexus/core/ENGINE_CONSTITUTION.md` (moved to `Vault/Playbook.md`) and `.agents/rules/zero_sycophancy.md` (folded into `Vault/Playbook.md` §11).

## [2.14.0] - 2026-10-07

### Added
- Added rule 22 to `AGENTS.md` (Self-Managing Documents): Establishing the `# Document Playbook` architecture for complex living state documents, encapsulating maintenance/archival logic directly inside the data layer.
- Created `src/nexus/shared_tools/calendar_engine.py` providing deterministic Google Calendar API integration (`list_events`, `create_event`, `update_event`, `delete_event`, `clean_html_description`, and CLI commands) with UTF-8 Windows terminal support.
- Added agentic shared LangChain `@tool` wrappers in `src/nexus/shared_tools/shared.py` (`get_calendar_schedule`, `create_calendar_event`, `update_calendar_event`).
- Documented `calendar_engine.py` in `README.md` under Deterministic Tools.
- Standardized first-class `Events/` directory (`<Section>/Events/YYYY/`) for Tier 4 Episodic Memory across all universal section sub-brains, housing discrete historical records (`YYYY-MM-DD - <Topic>.md`: networking exchanges, screens, interviews, agent sessions).
- Added Rule 12 (`Zero Sycophancy & Grounded Reality`) and `.agents/rules/zero_sycophancy.md` enforcing absolute anti-sycophancy and fact-grounded communication across all agent interactions.

### Changed
- Refactored `Protocol - Career Maintenance.md` cadences to natively trigger the `Employer Skill Requirements.md` document playbook rather than duplicating logic.
- Extended `src/nexus/core/google_auth.py` with `token_filename` parameter to enable isolated OAuth tokens per service (`token_calendar.json` vs `token.json`).
- Updated AGENTS.md, README.md, and Glossary to reference the new Concept - The Nexus Execution Lifecycle SSOT, removing duplicated anatomy schemas and formalizing the Operational vs. Conceptual section classification rule.
- Refactor and condense Section 6.2 (`Library & Learning`) from 14 sprawling academic sub-sections into a focused 4-part AI Engineering Core (`6.2.1. Intelligent Agents & Autonomy`, `6.2.2. Language Models & Production RAG`, `6.2.3. Programming & Software Engineering`, `6.2.4. Data Engineering & MLOps`).
- Consolidate foundational mathematics, classical machine learning, deep learning theory, and biomedical AI into `Technical Reference Archive.md` (MOC) under `Archive/`, eliminating 166 lines of syllabus clutter from `Table of Contents.md` while preserving 100% of user notes. Prune 6 empty stub directories.
- Moved the engine constitution to `src/nexus/core/ENGINE_CONSTITUTION.md`, loaded by `engine_constitution.py`, so internal agents and IDE agents (Resident + Builder) read one shared rule file. Slimmed AGENTS.md to a boot sequence plus Builder coding standards. The resident behaviors (life archiving, flush trigger, Document Playbooks, grounding) moved into the constitution, and the section anatomy now points to the Execution Lifecycle SSOT (Operational vs. Conceptual).
- Decoupled Cold Storage (`<Section>/Archive/`) from Episodic Neocortex (`<Section>/Events/`), clarifying `Archive/` strictly as cold storage for retired Tier 3 Living State (superseded documents, completed projects, closed CRM contacts) rather than burying active life history.
- Migrated legacy `Archive/Conversations/` to `Events/2026/` across `3.1. Career Strategy & Revenue`, `6. Forge`, and `2. Health/2.3. Psych`.
- Updated engine specifications, section building protocols, and agent instructions in `AGENTS.md`, `src/nexus/core/engine_constitution.py`, `Project - Nexus Agentic Engine.md`, and `Glossary - Nexus Engine Terminology.md`.
- Reworded AGENTS.md standards 2 and 19 and the README headline to mark the SubagentFactory and Cognitive Inheritance as planned architecture, since `src/nexus/` has no agent-spawning tooling and all agents are hardcoded LangGraph graphs.
- Moved the documented location of Section 1.1 daily execution logs from `Archive/YYYY/MM/` to `Events/YYYY/` (AGENTS.md standard 20, Table of Contents) for consistency with the universal section anatomy.
- Executed top-level Vault taxonomy refactor to establish single-word, sovereign life domains:
  - `1. The Core` $\to$ `1. Core`
  - `3. Operations & Wealth` $\to$ `3. Operations`
  - `4. Playground` $\to$ `4. Life`
  - `5. Capture & Archive` $\to$ `5. Reference`
  - `6. Forge` $\to$ `6. Engineering`
- Cleaned Vault root: moved loose `0. Quick Capture.md` into `0. Inbox/`, loose psychology guide into `2. Health/2.3. Psych/`, `Movies/` into `4. Life/4.3. Culture & Inspiration/`, and `Project Helix Instructions/` into `6. Engineering/6.1. Projects/`.
- Updated `Table of Contents.md` section headers and deprecated fragile `obsidian://search` URI links in favor of clean, sovereign Markdown structure.
- Updated path references across all engine agents (`src/nexus/agents/career/`), resume engines (`render.js`, `render_docx.py`, `inspect_docx.js`), maintenance scripts (`scripts/audit_career_drift.py`), `.agents/skills/`, and `.agents/workflows/`.
- Updated `AGENTS.md` and `README.md` to reflect the new taxonomy.
