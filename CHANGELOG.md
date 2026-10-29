# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [3.1.0] - 2026-10-28

### Added
- **Builder Agent Work Tracking & Attribution Rule (`.agents/rules/builder_work_tracking.md`):** Established a standing builder rule mandating that any agent doing Nexus work must update `Vault/1. Core/1.1. Philosophy & Personal North Star/Plan.md` under `# Today` (`## Career & Technical`). Requires explicit delineation of human direction vs. agent execution, ensuring the daily synthesis captures what was done, by whom, and through what mechanisms.
- **DAG Execution Graph View (`AgentGraphView`)**: Visual topology canvas reconstructing parent-child execution graphs from trace telemetry, linking Commander (`NexusAgent`) to parallel subagent swarms (`Subagent #1`, `Subagent #2`) with status badges, tool call counts, token meters, and an interactive node inspector showing full untruncated prompts, step logs, and returned syntheses.
- **Agent Audit Log Cockpit (`gui/src/app/audit/page.tsx`)**: Full-screen observability surface accessible via the primary sidebar and Mission Control quick actions, featuring live search across historical run snapshots in `logs/runs/`, complete untruncated query and response inspection, subagent fleet breakdowns, and execution DAG visualization.
- **Hierarchical Agent Telemetry**: Added `agent_id` and `parent_id` tracking to `AgentTracer` and trace events, plus thread-safe subagent serial numbering (`subagent-1`, `subagent-2`, ...) and `reset_subagent_counter()`.
- **Lossless Subagent Fleet Logging**: `log_run` in `src/nexus/core/run_logger.py` now groups subagent steps, prompts, tool calls, and syntheses into structured `subagents` arrays and persists aggregated token metrics.
- Created modular Home UI subcomponents under `gui/src/components/home/`:
  - `HomeHeader.tsx`: Title, active pinned note count badge, refresh disk content trigger, layout view mode segmented switcher (Grid vs Split Reader), and "+ Pin Note" launcher.
  - `HomeEmptyState.tsx`: Onboarding empty state container with quick-pin suggestions for default notes (`Tasks.md`, `Goals.md`) and Vault browse button.
  - `PinnedNoteCard.tsx`: Individual pinned note card in Grid view with header controls (re-ordering arrows, copy markdown with checkmark feedback, open in Vault explorer link, height expand/collapse toggle, unpin button), loading/error states, and word metrics footer.
  - `PinnedCardGrid.tsx`: Multi-column responsive grid container rendering pinned cards.
  - `PinnedNotesReader.tsx`: IDE-style split workspace reader with a left navigation rail and main document viewer pane.
  - `PinNoteModal.tsx`: Searchable note picker modal dialog with search filtering, folder category chips, keyboard Escape dismissal, and pin toggle actions.
  - `types.ts`: Shared data contracts, prop interfaces, storage keys, and fallback defaults.
  - `index.ts`: Clean barrel export for all home components and types.
- **Per-Turn Model Selection in Nexus Chat UI (`gui/src/app/ask/page.tsx` & `gui/src/lib/api.ts`):** Added a segmented model selector directly inside the `/ask` chat input bar (`Strong (gemini-4-argon)` vs. `Fast (gemini-3.8-flash)`), quick-start model buttons under `+ New Chat`, `localStorage` persistence (`nexus_chat_model_tier`), live streaming status indicators, and model execution badges on assistant message bubbles.
- **Model Catalog Endpoint & Dynamic Tier Resolution (`src/nexus/core/constants.py` & `src/nexus/api/routers/agents.py`):** Added `resolve_model_config()`, `get_available_models()`, and `GET /api/agents/models` to expose configured model tiers and active provider identifiers to the frontend.
- **Per-Turn `RunnableConfig` Model Routing (`src/nexus/agent/graph.py` & `src/nexus/agent/api.py`):** Updated `call_model(state, config)` and `run_nexus_agent_with_trace(..., model_tier=...)` to pass `model_tier` via LangGraph `RunnableConfig` (`configurable.model_tier`), enabling per-turn model switching without mutating checkpointed message history or invalidating KV prompt caches.
- **Pinned Notes Home Workspace (`gui/src/app/page.tsx`)**: Replaced the legacy Mission Control and Agent Fleet dashboard with a personal, distraction-free Pinned Notes workspace. Supports both a multi-column Cards Grid view and an IDE-style Split Workspace Reader with full Markdown rendering, code blocks, checklists, and Obsidian wiki-links.
- **Pin / Unpin Note Modal**: Added a searchable, keyboard-friendly dialog enabling one-click pinning across all 300+ Vault notes with category chips for top-level folders, live search, and pin/unpin toggles.
- **Vault Flat Notes API (`GET /api/vault/notes`)**: Added FastAPI endpoint and TypeScript client wrapper `getAllVaultNotes()` returning sorted markdown note summaries (title, path, folder, size, mtime) for rapid client-side search.
- **Bi-directional Vault Pinning (`gui/src/app/vault/page.tsx`)**: Added a direct "Pin to Home" toggle to the Brain Explorer note header, and support for the `?note=...` query parameter to link straight from pinned cards into Brain Explorer.
- Created modular Chat UI subcomponents under `gui/src/components/chat/` (`ChatSidebar.tsx`, `ChatHeader.tsx`, `ChatMessageThread.tsx`, `ChatMessageItem.tsx`, `ChatInputBar.tsx`, `BlackboardDrawer.tsx`, `types.ts`, and `index.ts`).
- Created the `/chat` route orchestrator in `gui/src/app/chat/page.tsx`.
- **Blackboard Unit Test Suite (`tests/test_blackboard.py`):** Added 7 comprehensive unit tests covering bulletin posting, pinned-first retrieval, Markdown digest formatting, deletion, clear-all, legacy kwargs tolerance, and schema migration.

### Changed
- **Agent Constitution & Project Documentation (`AGENTS.md` & `README.md`):** Added the `Daily Plan & Work Attribution` directive to `AGENTS.md` under `# Living Project Context & Engineering Standards` and documented `builder_work_tracking.md` in `README.md`.
- **Thinking Panel (`ThinkingPanel`)**: Replaced truncated single-line trace log with an interactive 3-mode visualizer supporting Graph View, All Steps (with expandable uncut tool arguments & results), and Raw JSON, with toggles for compact scroll vs. full uncut height.
- **Lossless Telemetry Across Backends**: Eliminated character truncation across `src/nexus/core/trace.py`, `src/nexus/agent/graph.py`, `src/nexus/agent/api.py`, and `src/nexus/core/run_logger.py`, ensuring subagent prompts, tool payloads, and intermediate reasoning are captured without cutoff.
- **Synchronous Trace Capture**: `POST /api/agents/ask` now subscribes to `trace_bus` to persist complete trace events into `chats.db` and `logs/runs/`.
- **Modular Frontend API Client Layer (`gui/src/lib/api/`):** Refactored the monolithic 595-line `gui/src/lib/api.ts` into a clean modular domain architecture mirroring the FastAPI backend routers:
  - `client.ts`: Base HTTP client, `apiFetch` wrapper, and `ApiError` hierarchy.
  - `stream.ts`: Low-level SSE parser and real-time execution `TraceEvent` streaming engine (`askBrainStream`).
  - `agents.ts`: Swarm agent status, conversations, chat execution, and model catalog endpoints.
  - `vault.ts`: Vault tree browsing, note fetching, note metadata summaries, and podcast TTS synthesis.
  - `hitl.ts`: Human-in-the-Loop approval, rollback, rebase, and conflict resolution type guards.
  - `board.ts`: Shared agent blackboard bulletin board endpoints.
  - `index.ts`: Barrel export preserving 100% backwards compatibility for `@/lib/api` imports across all UI pages.
- Refactored `gui/src/app/page.tsx` from a monolithic 933-line file into a lean ~230-line route orchestrator delegating all presentation to `@/components/home`.
- Resolved all ESLint warnings and guarded initial hydration with `queueMicrotask` to avoid cascading renders in React 19.
- Updated `Project - Nexus GUI.md` and `Build Log - Nexus GUI.md` with the new component hierarchy.
- **Home Navigation & Layout**: Renamed the primary navigation destination from "Mission Control" to "Home" (`📌`) across `Sidebar.tsx` and updated page metadata in `layout.tsx`.
- Renamed the Next.js conversational route from `/ask` ("Ask Brain") to `/chat` ("Chat") in `gui/src/components/Sidebar.tsx` and across GUI components.
- Decomposed the 932-line monolithic chat page into focused, single-responsibility subcomponents and eliminated synchronous `setState`-in-effect lint errors.
- Compacted `ChatInputBar` base height (`minHeight: 10px`, single-row default) and simplified placeholder to "Type message...".
- Streamlined model selection buttons by omitting model name annotations and moved send/newline keyboard shortcuts into button title tooltip.
- Replaced generic chat starter suggestions with tactical daily execution triggers ("What do we got for today?", "Do an email sweep.", "What are my outstanding Missions?").
- Simplified Blackboard drawer title and header toggle tooltips to "Agent Blackboard".
- Standardized agent routing pills in `ChatMessageItem` to display "NexusAgent".
- **Unified Shared Agent Blackboard (`src/nexus/core/blackboard.py`):** Eliminated artificial agent channel tagging and channel inference (`infer_channel`) in favor of a single, unified situational bulletin stream. Added automatic SQLite schema migration in `init_board_db()` using native `ALTER TABLE bulletins DROP COLUMN channel` while safely absorbing deprecated kwargs for backward compatibility.
- **Agent Orchestrator & Tool Signatures (`src/nexus/agent/graph.py` & `src/nexus/shared_tools/shared.py`):** Updated `spawn_subagent` auto-publishing to post directly to the unified blackboard without channel tagging or channel inference. Simplified `post_to_board` and `read_board` tool signatures and docstrings, removing channel arguments.
- **FastAPI Router & Control Panel UI (`src/nexus/api/routers/board.py`, `gui/src/lib/api.ts`, & `gui/src/app/ask/page.tsx`):** Streamlined `/api/board` REST endpoints, removed channel filter tabs from the `/ask` right drawer, and pruned channel badges from bulletin feed cards in favor of author, ID, and pin status indicators.

### Fixed
- **Auto-Expanding Chat Input Field (`gui/src/app/ask/page.tsx`):** Replaced the single-line fixed `<input>` with an auto-expanding `<textarea>` that starts at a comfortable 56px base height and dynamically grows up to 240px as the user types. Added multiline support (`Shift + Enter` for newlines, `Enter` to submit) and refactored the input card to give the textarea full horizontal width with model selection pills and the send button arranged along a dedicated bottom toolbar.
- **Chat Draft & Active Conversation Persistence Across Tab Navigation (`gui/src/app/ask/page.tsx`):** Added hydration-safe client synchronization for unsubmitted prompt drafts (`nexus_chat_input_draft`) and the active conversation ID (`nexus_chat_active_conv_id`), ensuring typed text and selected conversation context never disappear when navigating between Nexus navigation tabs (Home, Ask Brain, Brain Explorer, HITL, Audit Log) or refreshing the page.

### Removed
- **Vestigial `AGENT_REGISTRY` & Status Route (`src/nexus/api/routers/agents.py`):** Removed in-memory `AGENT_REGISTRY`, `AgentStatusEntry` schema, `GET /api/agents/status` route, and per-turn timestamp update loops left over from the pre-Universal-Agent multi-agent swarm architecture.
- **Orphaned `AgentCard` Component & Client Methods (`gui/src/`):** Deleted unmounted `AgentCard.tsx` component and removed unused `AgentStatus` interface and `getAgentStatus()` fetch helper from `gui/src/lib/api/agents.ts`.
- **Dead Engine Dashboard Route & Core Module (`src/nexus/api/routers/agents.py`, `src/nexus/core/dashboard.py`):** Removed `GET /api/agents/dashboard` and deleted orphaned `src/nexus/core/dashboard.py` health aggregator and Markdown generator leftover from the decommissioned Mission Control fleet view.
- **Decommissioned Sticky Routing Residue (`src/nexus/api/routers/agents.py`, `src/nexus/core/chats_db.py`, `gui/`):** Purged vestigial sticky agent session tracking from the codebase. Removed `set_active_agent` and `get_active_agent` database helpers, removed `active_agent` from new conversation creation in SQLite, deleted `POST /api/agents/ask/conversations/{id}/reset` route, removed unused `get_conversation` import, and purged `resetConversationRouting()` API helper, dead "Reset Routing" button, and static `"Auto-Routing"` label from the frontend chat UI.
- Removed the legacy monolithic `gui/src/app/ask/page.tsx` route directory.

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

## [2.13.0] - 2026-09-27

### Added
- Added `cognitive_boundary_flush` skill (`.agents/skills/cognitive_boundary_flush/SKILL.md`) implementing the 4-tier Hippocampal Flush protocol.
- Added `/flush` slash-command workflow (`.agents/workflows/flush.md`) for explicit event boundary execution.
- Added Engine Coding Standard 21 to `AGENTS.md` mandating proactive Hippocampal Flush prompting upon session conclusion or context switches.
- Updated Section 10 of Engine Constitution (`src/nexus/core/engine_constitution.py`) with the formal 5-step Hippocampal Flush protocol.
- Added `/archive_contact` agentic workflow (`.agents/workflows/archive_contact.md`) for systematic pruning of closed, rejected, or stale networking contacts and requisitions.
- Defined formal CRM Archiving Protocol in `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Protocol - Career Maintenance.md` to preserve Tier 3 living state context windows by migrating inactive rows to `Professional CRM - Archive.md`.
- Integrated Standardized Section Anatomy (Section 9) and Event-Driven Cognitive Boundaries (Section 10) into `src/nexus/core/engine_constitution.py`.
- Added FastMCP dependency (`mcp>=1.30.0`) to `pyproject.toml` and `uv.lock`.
- Updated public `Table of Contents.md` with link to `Concept - Cognitive Boundaries & Event-Driven Agent Memory`.
- Added Engine Standard 20 (`Episodic Life Archiving & Anti-Hallucination Grounding`) to `AGENTS.md` and established Section 1.1 `Playbook.md` to ensure agents interactively verify daily events via calendar and user confirmation, reject copy-pasting aspirational container templates or routine habits, and preserve a grounded 4-compartment life/mission record.
- Integrated the rolling working-set sliding envelope protocol into `.agents/workflows/weekly_review.md` and `.agents/skills/career_counselor/SKILL.md` to ensure `Short Term Execution Plan.md` tracks active working sets only (excluding rest days), places today's granular containers at the top for ADHD focus, enforces proactive prior-day reconciliation prompting, and heavily compresses past/future sets.

### Changed
- Clarified the Project Scope Docs hierarchy in `AGENTS.md` to distinguish software infrastructure projects (compiled Python subgraphs in `src/nexus/` and GUI apps) from declarative domain section subagents (governed natively by standardized section files in `Vault/<Section>/`, eliminating duplicate child project docs).

### Deprecated
- Deprecated and removed legacy `log_llm_conversation` skill in favor of localized atomic episodic archiving in `<Section>/Archive/Conversations/` and domain-scoped ADR logging.

## [2.12.0] - 2026-09-04

### Added
- Implemented structured JSON execution run logger in `src/nexus/core/run_logger.py` persisting complete agent snapshots to `logs/runs/`.
- Integrated `loguru` structured logging in `src/nexus/core/logger.py` with colorized stdout and rotated file persistence at `logs/engine.log`.
- Created unified engine telemetry and health aggregator in `src/nexus/core/dashboard.py` with Markdown summary generator.
- Added `/api/agents/runs`, `/api/agents/runs/{run_id}`, and `/api/agents/dashboard` REST endpoints in FastAPI router.
- Embedded SOTA agentic engineering standards into `AGENTS.md` and `src/nexus/core/engine_constitution.py`: Pydantic-first structured outputs, deterministic AST/YAML pre-commit lint gates, native LangGraph `interrupt()` & `Command` HITL state pausing/resumption, prompt caching prefix isolation, loop circuit breakers, and Sub-Brain living state with atomic conversation archiving (`Archive/Conversations/`).
- Updated master scope doc `Project - Nexus Agentic Engine.md` and all child docs (`Project - Career Agent.md`, `Project - Health Agent.md`, `Project - Forge Agent.md`, `Project - Librarian Agent.md`, `Project - Content Router Agent.md`, `Project - Basic Engine Control Panel.md`) with modern Sub-Brain architectural blueprints, universal shared tooling (`search_my_domain`), and logged architectural evolution to `Log - LLM Conversations.md`.

### Changed
- Clarified `log_llm_conversation` skill trigger and execution boundary to focus exclusively on macro architectural decisions and cognitive idea forging, excluding tactical life task minutiae.
- Architectural paradigm shift: Dynamic Section Subagent Factory & Meta-Orchestration.
- Evolved from static N-agent swarm (one hardcoded Python package per domain) to a Unified Dynamic Section Subagent Factory where one generic SectionSubagent LangGraph engine is parameterized by standardized Vault directory modules (Section Profile.yaml, Playbook.md, Lessons Learned.md, Section Map.md, Tasks.md, Archive/, Logs/).
- Upgraded memory architecture from 3-tier to 5-tier (Working → Session → Procedural → Semantic → Episodic) with Cognitive Inheritance (CI) across parent-child sections.
- Content Router evolved into dual-mode Meta-Orchestrator (Sticky Handoff + Supervisor Worker Spawning).
- Updated all project scope docs, AGENTS.md, engine_constitution.py, and README.md to reflect new architecture.
- Created Glossary - Nexus Engine Terminology note and conversation archive.
- Standardized Section Anatomy in `AGENTS.md` (Standard 18) and `Glossary - Nexus Engine Terminology.md` to formally codify `Log.md` (Operational Rep Log / Event Journal) and `Framework.md` (Permanent Architecture & Living Baseline) per section.
- Migrated technical architecture dialogue records to `Vault/6. Forge/Log.md` and operational cognitive engineering reps to `Vault/2. Health/2.3. Psych/Log.md`.

### Fixed
- Resolved split-brain thread ID isolation bug by propagating UI `conversation_id` down to LangGraph `thread_id` checkpointers across Router, Career, and Librarian agents.

## [2.11.0] - 2026-08-26

### Added
- Created `scripts/audit_career_drift.py` for deterministic Tier-1 career document drift auditing (timestamp staleness, character bounds, skill coverage, telemetry).
- Created `.agents/workflows/audit_career.md` (`/audit_career` slash command) for running cross-document career audits.
- Added Three-Tier Drift Prevention & Sync Architecture and Phase 2 roadmap milestones to `Project - Career Agent.md`.
- Integrated `/audit_career` checks into `Protocol - Career Maintenance.md`.
- Created `.agents/rules/code_commenting_standards.md` establishing mandatory granular, educational code-commenting standards tailored to the developer's learning style.
- Updated `AGENTS.md` (both in Nexus and Portfolio) and `README.md` with standing directives and architectural documentation requiring line-by-line syntax breakdowns, concrete examples for generics/types, and strict preservation of existing educational comments.
- Implemented `HTMLToMarkdownParser` in tools.py for stream parsing HTML emails into clean Markdown while preserving clickable hyperlinks `[text](url)`, headings, and lists.
- Added `_fetch_headers_batch` to execute single-trip IMAP header queries, eliminating N+1 network latency.
- Added `_build_imap_query` to translate natural-language and freeform search phrases into valid RFC-3501 IMAP query filters.
- Upgraded read_email.py CLI with `--search` flag and formatted tabular display.

### Changed
- Added dense, pedagogical inline and pre-block educational comments across `gui/src/lib/api.ts`, `src/nexus/api/routers/agents.py`, `src/nexus/core/trace.py`, `src/nexus/agents/router/graph.py`, and `src/nexus/agents/career/graph.py` adhering to `.agents/rules/code_commenting_standards.md`.

### Fixed
- Corrected relative path resolution in `src/nexus/shared_tools/resume_engine/render.js`, `render_docx.py`, and `inspect_docx.js` following the engine folder reorganization.
- Fixed relative paths to virtual environment and vault directories in `generate_podcast.py` and `ingest_phone.py`.
- Fixed silent body omission bug in `_extract_body` where empty `text/plain` multipart payloads prevented rich HTML fallback.
- Suppressed non-visual HTML containers (`<style>`, `<script>`, `<head>`, `<svg>`, `<noscript>`) to eliminate stylesheet leakage into parsed emails.

## [2.10.0] - 2026-08-20

### Added
- Added `/weekly_review` workflow to systematize Sunday evening weekly review and planning.

### Changed
- `project_work` skill: Added Build Log formatting standards enforcing past-tense action verbs and prohibiting redundant `- **Completed:**` prefixes.
- `/create_project` workflow: Modernized workflow to scaffold the canonical 7-section project note architecture (`Goal`, `Current State`, `Architecture`, `Standing Guidelines`, `Build Log`, `Roadmap`, `Resources`), TOC back-links, and To Do List registration.
- Standardized instruction hierarchy, atomic sub-bullet density, and clean structural anchors across all `.agents/skills/` and `.agents/workflows/`.
- Refactored `skill_creator` and `workflow_creator` meta-standards from first principles to prioritize structural hierarchy and atomic instruction density.
- Extracted shared medical research, citation, and safely caveated tone guidelines into `analyze_health/references/medical_research_protocol.md` to eliminate instruction duplication between `analyze_health` and `analyze_psych`.
- Fixed stale path references in `add_job_requirement.md` (`3.1. Career Strategy & Revenue`) and `AGENTS.md`.
- Synchronized `/create_new_note` and `/release` into `README.md` workflow index.

## [2.9.0] - 2026-08-18

### Added
- Created `src/nexus/shared_tools/export_conversation.py` as a universal JSON/JSONL chat transcript parser and formatter (supporting generic JSON message lists, JSONL streams, ChatGPT exports, stdin piping, and local Antigravity transcripts).
- Added CLI capabilities for direct Markdown export (`-o`), Obsidian Inbox ingestion with YAML frontmatter (`-v` / `--vault-inbox`), thinking blocks accordion (`-t`), and stdout output (`--stdout`).
- Added local conversation transcript discovery helpers (`--list`, `--latest`, UUID prefix matching).
- Documented tool in `README.md` and `Project - Nexus Agentic Engine.md`.
- Created `scripts/` directory to separate meta/maintenance scripts from engine runtime tools.
- New `/release` slash command workflow added in `.agents/workflows/release.md`.
- `release.py` now explicitly handles text encoding `errors='replace'` to avoid crashing on non-UTF-8 changeset fragments.
- Created `src/nexus/shared_tools/` as the new home for all deterministic Python integration scripts (e.g. `read_email.py`, `generate_podcast.py`, `ingest_phone.py`).

### Changed
- Moved meta scripts `release.py`, `backup_vault.py`, `check_folders.py`, `create_folders.py`, `sync_vault.py`, and `add_gitkeeps.py` from `tools/` to the new `scripts/` directory.
- Updated `AGENTS.md` and `README.md` to reflect the new `scripts/` directory and `/release` workflow integration.
- Moved all engine runtime tools from the root `tools/` directory into `src/nexus/shared_tools/`.
- Deleted the root `tools/` directory to enforce a strict boundary between repository maintenance scripts (`scripts/`) and engine components (`src/nexus/`).
- Updated `AGENTS.md` and `README.md` to reflect the new architecture.
- Updated slash command workflows (`/add_job_requirement`, `/capture_content`, `/distill_learning`, `/ingest_medical_record`, `/render_resume`) to point to the new `src/nexus/shared_tools/` paths.
- `scripts/sync_vault.py`: Automatically runs `git push` after committing changes (and pushes pre-existing unpushed commits if working tree is clean). Added cross-platform UTF-8 stream handling.
- `README.md`: Updated maintenance scripts table and sections.

### Removed
- Cleaned up obsolete temporary BLOB inspection scripts (`scripts/inspect_antigravity_db.py`, `scripts/extract_antigravity_preview.py`).
- `scripts/backup_vault.py`: Removed obsolete backup script in favor of direct external backup tools.
- `scripts/create_folders.py`: Removed obsolete initial folder scaffolding script.
- `scripts/check_folders.py`: Removed obsolete dry-run folder checker script.
- `scripts/add_gitkeeps.py`: Removed manual gitkeep script in favor of agentic gitkeep rules.

## [2.8.0] - 2026-08-04

### Added
- Multi-Conversation Chat Architecture: The Ask Brain UI now supports multiple parallel conversation threads decoupled from eternal agent memory.
- Added CRUD API endpoints for conversations under `/api/agents/ask/conversations`.
- `AGENTS.md`: New `Project Scope Docs: Ultimate Authority` section establishing the parent/child project scope hierarchy as the ground truth for all Nexus engine work, with read-before and update-after obligations and conflict resolution rules.
- `project_work` skill: New §5 `Nexus Engine: Parent + Child Project Scope Doc Hierarchy` detailing the exact folder path, doc structure, and mandatory before/after protocol for reading and updating scope docs on every engine task.

### Changed
- Refactored `chats_db.py` to use a `conversations` table instead of a single `sessions` table.
- Career Agent now receives Domain Boundary instructions and emits `[HANDOFF]` to release sticky routing locks.
- Frontend AskBrainPage updated with a two-pane layout featuring a conversation sidebar and "Reset Routing" control.
- Updated model constants in `src/nexus/core/constants.py` by renaming `AI_MODEL` to `AI_MODEL_LOW` and including `AI_MODEL_MEDIUM` and `AI_MODEL_HIGH`. Updated the Career Agent (`src/nexus/agents/career/graph.py`) to use `AI_MODEL_MEDIUM` for main LLM operations and `AI_MODEL_LOW` for conversation summarization, and updated all other model references across router, librarian, email agent, and eval runners to `AI_MODEL_LOW`.
- Updated `/add_job_requirement` workflow to use chronological YYYY-MM-DD naming convention for saved job listings to better track industry trends over time.

### Fixed
- Fixed bug where `RemoveMessage` objects from `summarize_conversation` were incorrectly appended to agent states instead of deleting old messages, causing an OpenAI `BadRequestError` (stringified as `Got unknown type`). Replaced `operator.add` with LangGraph's `add_messages` across career, router, librarian, and email agents.

## [2.7.0] - 2026-07-03

### Added
- Created `src/nexus/core/chats_db.py` to manage unified frontend chat history and sticky routing state.
- Integrated LangGraph `SqliteSaver` checkpointer for working memory in `career` and `librarian` agents.
- Created `src/nexus/shared_tools/summarizer.py` with `summarize_conversation` for pruning and summarizing short-term recall.
- Added `summarizer_node` to `src/nexus/agents/career/graph.py` to compress working memory on the fly.

### Changed
- Updated `src/nexus/api/routers/agents.py` to persist chat history and implement sticky routing for active agents.
- Updated Next.js frontend (`AskBrainPage`) to fetch chat history on mount.
- Refactored Career Agent (`api.py` and `graph.py`) to build the system prompt ephemerally inside `call_model`, preventing duplication bugs in the checkpointer state.
- Refactored `.gitignore` to explicitly ignore `*.db`, `*.db-shm`, and `*.db-wal` files and untracked existing tracked db files (`logs/chats.db` and `src/nexus/agents/career/memory.sqlite`).
- Refactored `read_note` logic across domain agents. Moved bounded path resolution and fuzzy-searching natively into `vault_reader.read_note_content`.
- Extracted LangChain tool wrapper into `shared.py`'s `get_read_note_tool` factory function.
- Updated `AGENTS.md` Rule 6 to explicitly clarify architectural boundaries between pure Python data access layers (like `vault_reader.py`) and agentic `@tool` wrappers.

### Fixed
- Fixed an issue where the Career Agent would crash with an OpenAI `invalid_request_error` (400) due to dangling tool calls in the LangGraph state checkpoint after interruptions.
- Hardened the `propose_write` tool by resolving paths dynamically based on domain scopes and gracefully de-duplicating path nesting, preventing the creation of redundant directories outside of the Vault (such as in `PROJECT_ROOT`).
- Updated the career agent prompt to use this new simplified pathing behavior.

## [2.6.0] - 2026-06-22

### Added
- Created `src/nexus/core/config.py` using Pydantic `BaseSettings` to serve as the centralized source of truth for environment variables.
- Added dynamic injection of `{datetime}` and `User` to `src/nexus/core/engine_constitution.py`.
- Installed `pydantic-settings` via `uv` and updated `requirements.txt`.

### Changed
- Refactored `src/nexus/core/constants.py`, `src/nexus/interfaces/telegram.py`, and `src/nexus/agents/email/tools.py` to replace scattered `os.getenv` calls with strongly-typed `settings` from `config.py`.
- Moved the `.secrets` directory from `tools/.secrets` to the project root `.secrets` to align with the new `src/nexus` engine architecture and industry standards for credential management.
- Updated `.gitignore` and `src/nexus/agents/email/tools.py` to reflect the new root `.secrets` location.
- Refactored `AGENTS.md` to act strictly as the Builder rulebook, removing internal engine architecture principles.
- Added Standing Guidelines to `AGENTS.md` to enforce strict file structures and centralized logging/validation for all future engine agents.
- Migrated default package management workflow from `uv pip install` & `requirements.txt` to `uv add` and `uv.lock`.
- Updated `AGENTS.md` and `maintain_project_docs` skill to formally deprecate `requirements.txt` in favor of `pyproject.toml`.

### Fixed
- Fixed `OPENAI_API_KEY` missing error when starting Next.js/FastAPI via `start.ps1` by explicitly injecting `.env` into `os.environ` within `src/nexus/core/config.py`.
- Fixed execution failure in `tools/read_email.py` by removing legacy `sys.path.append` hacks and updating to the `nexus.*` import namespace.
- Fixed double chat response bug in Nexus GUI AskBrainPage caused by React Strict Mode double-invoking state updaters

### Removed
- Removed static `ENGINE_CONSTITUTION.md` and replaced it with a dynamic Python module.
- Deleted legacy `requirements.txt`.

## [2.5.0] - 2026-06-09

### Added
- Real-time agent trace streaming from the Python engine to the Next.js GUI via Server-Sent Events (SSE).
- `POST /api/agents/ask/stream` endpoint in FastAPI that yields live trace events.
- `TraceEventBus` pub/sub system in `engine/core/trace.py` that broadcasts `AgentTracer` events.
- Collapsible "Thinking Panel" in the Ask Brain GUI that displays live agent tool calls, routing decisions, and LLM reasoning steps with colors and icons.
- Persisted trace logs for past messages in the chat history.

### Changed
- Wire GUI Ask Brain page to the Content Router agent instead of calling the Librarian directly. The /api/agents/ask endpoint now routes through classify → domain dispatch, and the frontend displays which agent handled each query with domain and confidence metadata.
- Migrated python environment management from `pip` and `python -m venv` to Astral's `uv` for improved speed and determinism.
- Updated `AGENTS.md`, `README.md`, and `maintain_project_docs` skill to enforce `uv pip` usage.
- Restructured `engine/` directory into a standard `src/nexus/` Python package layout.
- Replaced `requirements.txt` with `pyproject.toml` (using `uv` and `hatchling` backend).
- Updated all internal imports to absolute imports under the `nexus.*` namespace.
- Replaced the standalone `python engine/main.py` command with a managed `nexus` CLI executable.
- Updated `start.ps1` to use absolute imports (`nexus.api.main:app`) and project-root working directory.

### Fixed
- Fixed `IndentationError` in `engine/agents/email/tools.py` due to missing `try` block for `list_recent_emails`.
- Fixed Content Router LLM hallucination where it aggressively triggered `fetch_emails` for local notes by tightening the `fetch_emails` tool docstring and router prompt.

### Removed
- Deleted `requirements.txt` in favor of PEP-621 `pyproject.toml` management.
- Removed legacy `sys.path.insert()` and `sys.path.append()` hacks used for standalone script execution.

## [2.4.0] - 2026-06-04

### Changed
- Add real-time console tracing to all agents (Router, Career, Librarian, Email) via new `core/trace.py` AgentTracer. Replace interactive 1/2/3 menu in `main.py` with a persistent chat REPL that never clears the console.
- Refactored entire agent swarm architecture (Router, Email, Career, Librarian) into modular `api.py`, `graph.py`, `tools.py` structure.
- Globalized pure Python vault filesystem I/O operations into `engine/shared_tools/vault_reader.py`.
- Extracted shared cross-agent @tool wrappers (e.g. `ask_librarian_escalation`, `propose_write`) into `engine/shared_tools/shared.py`.
- Updated all API routes and CLI tools to consume agents strictly via their public `api.py` boundaries.
- Refactor career agent to move tools from `agent.py` to a dedicated `tools.py` file, matching other agents' structure and improving separation of concerns.
- Updated `generate_obsidian_note` and `project_work` skills to enforce the new canonical project template structure (Overview, Current State, Architecture, Standing Guidelines, Build Log, Roadmap).

### Removed
- Deleted legacy monolithic `engine/tools/vault_tools.py` and `engine/tools/` directory.

## [2.3.0] - 2026-06-01

### Added
- Created the **Email Agent** compiled LangGraph subgraph under `engine/agents/email/` to fetch and search IMAP emails.
- Added `search_emails` tool to `engine/agents/email/tools.py`.
- Established the Email Agent Golden Dataset evaluation suite in `engine/agents/email/evals/`.
- Added 5 new evaluation cases to the Career Agent dataset in `engine/agents/career/evals/dataset.json`.
- Created decentralized `evals` framework for the Content Router and Career Agent.
- Added `dataset.json` and `runner.py` to `engine/agents/router/evals/` and `engine/agents/career/evals/`.
- Configured LangSmith tracing inside `.env`.
- Added high-resolution PNG and Windows multi-resolution ICO icon assets for the sync-vault shortcut button inside the GUI's public directory.
- Installed `pillow` Python package in the project environment for image manipulation.
- `get_master_resume()` tool for the Career Agent — reads `Resume - Master.md` for resume tailoring workflows.
- Resume Tailoring Protocol in the Career Agent system prompt — agent reads master resume, crafts tailored version, and proposes via HITL.
- `run_career_agent_with_trace()` API — returns tool call metadata alongside agent response for eval observability.
- Known Cross-Domain File Paths section in the Career Agent prompt — provides exact vault paths for files outside the career domain (Current Learning, To Do List).

### Changed
- Migrated `engine/tools/email_tool.py` to `engine/agents/email/tools.py`.
- Refactored **Content Router** (`engine/agents/router/agent.py`) into a ReAct agent to support `fetch_emails` tool calling prior to classification.
- Updated `tools/read_email.py` to import from the new agent tools module.
- Hardened Career Agent HITL compliance via mandatory trigger rules in the system prompt (interview status changes, learning completions, skill acquisitions, job applications).
- Upgraded eval runner grader to use actual tool call traces instead of inferring HITL compliance from response prose.
- Renamed "Vault Explorer" to "Brain Explorer" in the GUI Sidebar navigation and Vault page component.
- Unified Nexus entry points (`engine/main.py` and `engine/interfaces/telegram.py`) to use the Content Router (`route_content`) instead of the Librarian directly.
- Updated the Content Router's fallback logic to escalate general knowledge queries to the Librarian Agent rather than returning a placeholder.
- Added `filters` support to the Router to propagate CLI tags/domains to the Librarian subgraph.
- Updated `README.md` Repository Structure to include `capture_content.md`.
- Added `release.py` to the Deterministic Tools table in `README.md`.

### Fixed
- Career Agent HITL compliance: pass rate improved from 33% (1/3) to 100% (3/3), avg score from 5.0 to 8.0.
- Career Agent failing to call `propose_write` for cross-domain files (e.g., `Current Learning.md`) because it couldn't see them in its domain listing.
- Fixed a `UnicodeEncodeError` on Windows consoles by forcing `sys.stdout` to UTF-8 in `engine/main.py`.

## [2.2.0] - 2026-05-28

### Added
- **Changeset Release Compilation System (Agent Context Optimization - Phase 1):**
  - Created `.changeset/` staging directory with `.gitkeep` for storing fragmented change notes.
  - Implemented `tools/release.py` Python compiler script to parse changeset fragments, determine semantic version bumps, update `CHANGELOG.md` and keep a rolling 3-release window in `CHANGELOG-RECENT.md`, and clean up staging.
  - Created `CHANGELOG-RECENT.md` as a low-token active context file for developer agents.

### Changed
- **Changelog Policies & Skills:**
  - Updated `maintain_project_docs` skill (`.agents/skills/maintain_project_docs/SKILL.md`) to instruct agents to write to `.changeset/` instead of directly modifying `CHANGELOG.md`.
  - Updated `AGENTS.md` Git & Changelog Policy rules to mandate changesets for engine changes.
  - Checked off Phase 1 tasks in the `Project - Agent Context Optimization & Changeset Automation.md` project log.
  - **Conversation Logging Optimization:**
  - Updated `log_llm_conversation` skill instructions to prepend entries at the top of `Log - LLM Conversations.md` instead of appending them at the bottom.
  - Re-ordered `Log - LLM Conversations.md` to place newer entries first, enabling future agents to verify duplicates by reading only the first 20 lines of the file.

## [2.1.0] - 2026-05-28

### Added
- **Multi-Agent Pipeline (Content Router → Career Agent → Librarian):**
  - **Content Router Agent (`engine/agents/router/`):** LangGraph-based classifier that categorizes incoming content into domain categories (career, health, general) via structured JSON output and routes to the appropriate domain agent using conditional edges. Includes fallback handling for unparseable LLM responses.
  - **Career Agent (`engine/agents/career/`):** Domain-specialized LangGraph ReAct agent for job analysis, skill gap detection, and career strategy. Implements the **Deterministic Pre-flight Hydration (DPFH)** pattern — before each LLM invocation, a pure-Python orchestration node reads the career domain file listing (`os.listdir`), `My Skills.md`, and `Employer Skill Requirements.md` and injects them into the system prompt at zero LLM cost. Includes domain-scoped `search_career_domain` tool, `ask_librarian` escalation tool for cross-domain queries, and `propose_write` tool that submits modifications to the existing HITL transaction queue for human approval.
  - **Librarian Integration:** The existing Librarian Agent (`engine/agents/librarian/`) now serves as the cross-domain search escalation service, callable as a tool by the Career Agent for queries outside its domain folder.
  - **End-to-End Orchestration:** The Router's `career_agent` node invokes the real Career Agent subgraph (replacing the Step 1 placeholder), enabling a full pipeline: raw content → classification → domain-specific analysis with live vault context → optional cross-domain retrieval → structured response.
- **Direct Execution Fix:** Added `sys.path` bootstrapping to both `router/agent.py` and `career/agent.py` so they can be run directly from the project root (`python engine/agents/router/agent.py`) without `ModuleNotFoundError`.
- **Vault Explorer & Podcast Studio:**
  - Implemented `gui/src/app/vault/page.tsx` offering a dual-pane layout with an interactive tree browser and markdown preview.
  - Added visual badges (`🎧`) to markdown files indicating ready-to-play generated audio.
  - Created a 1-click generation Podcast Studio in the frontend with a dark-mode friendly HTML5 audio player for in-browser playback.
- **Podcast Vault Endpoints:** Added `/api/vault/list`, `/api/vault/podcast/generate`, and `/api/vault/podcast/download` endpoints to the FastAPI backend to safely bridge the GUI to the local filesystem.
- **Typed API Client (`gui/src/lib/api.ts`):** Added `VaultEntry` interfaces and methods for the new Vault endpoints.

### Changed
- **Podcast Generation Tool (`tools/generate_podcast.py`):**
  - Refactored to save generated `.mp3` files directly alongside the source `.md` files instead of a central `Audio/` folder.
  - Migrated history tracking to `.podcast_history.json`.
  - Fixed Windows CLI character limits and `edge-tts.exe` crashes by writing text to a temporary file and invoking `python -m edge_tts --file`.
- **Developer Agent Constitution Refactor (`AGENTS.md`):**
  - Slimmed down `AGENTS.md` by >70%, removing redundant verbatim listings of skills, workflows, and tools that are already managed by the platform or documented in `README.md`.
  - Added explicit Meta-Boundary guidelines separating the external Developer Agent from the internal Nexus Agentic Engine.
  - Added explicit authorization for developer agents to read and use `Vault/` files for personal domain context and run `tools/` and `engine/` scripts.
  - Summarized the 4 core engine architectural principles (Agentic File System, Folder-Mapped Swarm, Pre-flight Hydration, and HITL Queue) that developer agents must respect when editing engine code.
  - Simplified the `maintain_project_docs` skill rules to remove the obsolete "Compiler Pattern" for auto-generating `AGENTS.md`.



## [2.0.0] - 2026-05-26

### Added
- **Nexus Engine Control Panel — Phase 1 (Full-Stack Foundation):**
  - **FastAPI Backend (`engine/api/`):** New HTTP bridge layer between the Next.js GUI and the Python engine. Includes CORS middleware, health check endpoint, agent status registry (6 agents), real `ask_librarian()` integration, vault structure/note/search endpoints.
  - **Next.js Frontend (`gui/`):** Scaffolded with TypeScript, Tailwind CSS v4, App Router. Premium dark-mode design system with deep space palette, glassmorphism cards, glowing status pills, staggered entrance animations, and gradient text.
  - **Mission Control Dashboard (`/`):** Real-time agent fleet overview with summary stat cards (engine status, active agents, pending HITL, errors), agent cards populated from the live API with 15-second polling, and quick-launch action buttons.
  - **Ask Brain Chat Interface (`/ask`):** Conversational page wired to the Librarian agent via `POST /api/agents/ask`. Features message history, example queries, typing indicator, and responsive layout.
  - **Typed API Client (`gui/src/lib/api.ts`):** Centralized fetch wrapper with full TypeScript types for all backend endpoints.
  - **Sidebar Navigation:** Logo, active-link highlighting, disabled items for future phases (Vault Explorer, HITL Queue, Audit Log), live system status indicator.
- **HITL Transaction Queue & Review Surface (Phase 1.5 — Core Safety):**
  - **SQLite HITL Queue (`engine/core/hitl_queue.py`):** Persistent transaction queue storing proposed agent writes with original content, proposed content, agent reasoning, and approval status. Durable across restarts.
  - **HITL API Router (`engine/api/routers/hitl.py`):** Endpoints for listing pending transactions, approving (writes to disk with PROJECT_ROOT resolution), rejecting, and mock seeding for development.
  - **HITL Review Page (`gui/src/app/hitl/page.tsx`):** Full review surface with a sidebar queue list, agent reasoning context panel, and Monaco Editor (`@monaco-editor/react`) side-by-side diff viewer for VS Code-quality pre-commit previews.
  - **Dashboard Integration:** Mission Control now fetches live pending HITL counts from the API and displays a "Review Queue" quick-action button with badge count.
- **Dependency:** Added `fastapi` and `starlette` to `.venv` and `requirements.txt`. Added `@monaco-editor/react` to `gui/`.

### Changed
- **`.gitignore`:** Added `gui/node_modules/`, `gui/.next/`, `gui/out/` exclusions for the frontend build artifacts.
- **`start.ps1` Process Cleanup:** Replaced `Stop-Process` with `taskkill /T /F` to kill the entire uvicorn process tree on exit, preventing zombie worker processes from holding port 8000 across restarts.

### Fixed
- **`start.ps1` Encoding:** Saved `start.ps1` with UTF-8 BOM encoding to prevent PowerShell 5.1 from misinterpreting Unicode characters (such as emojis and boxes) as ANSI smart quotes, resolving the script parsing and launch errors.

## [1.17.2] - 2026-05-23

### Changed
- **README Technical Restructure:** Refactored the introduction of [README.md](file:///c:/Users/Willi/Documents/Projects/Nexus/README.md) to prioritize technical utility, highlighting the system's architectural pillars (Agentic search engine, workflows, skills, and tools) and framing the personal vault layout as a live production case study.
- **RAG Architecture Cleanup:** Removed outdated RAG architecture references in the overview text and directory tree diagram to align with the active local agent-based traversal architecture.

## [1.17.1] - 2026-05-22

### Added
- **LLM Conversation Logger Skill (`log_llm_conversation`):**
  - New agentic skill to automatically summarize and log design discussions, architectural decisions, and key technical trade-offs at the end of AI conversations.
  - Target journal note created at [Log - LLM Conversations.md](file:///c:/Users/Willi/Documents/Projects/Nexus/Vault/1.%20The%20Core/1.1.%20Philosophy%20&%20Personal%20North%20Star/1.1.1.%20Personal%20Logs/Journal/Log%20-%20LLM%20Conversations.md) to serve as a running history of cognitive system evolution.

## [1.17.0] - 2026-05-21

### Added
- **Phase 2 Search: Tree-Based Navigation & Targeted Grep (Librarian Item 9):**
  - New `get_vault_structure(path)` tool — recursive "Agentic ls" that returns the full folder tree (root) or files + folders (drilled subtree). Replaces blind full-vault searches with cheap structural orientation.
  - New `search_vault(keyword, path, tags)` params — optional `path` for targeted subtree grep and `tags` for YAML frontmatter filtering via lightweight regex.
  - New `_parse_frontmatter_tags()` and `_build_tree()` helpers in `vault_tools.py`.
- **Dynamic Structure Injection:** `execute_vault_query()` now calls `get_vault_structure()` programmatically at query time and injects the live folder tree into the system prompt via `{vault_structure}` placeholder. Eliminates one LLM round-trip per query while staying fresh after vault restructures.
- **Token Usage Tracking:** Both `run_logs.jsonl` and `evals/runner.py` now extract `usage_metadata` from LangChain AI messages and log `prompt_tokens`, `completion_tokens`, and `total_tokens` per query. Eval summary prints aggregate token stats.
- **Resume Engine Page Metrics:** `render.js` now measures rendered content height via Playwright after every PDF generation and outputs a structured `📐 PAGE METRICS` summary with: page count, last page fill %, verdict (`UNDERFILL`/`ROOM`/`GOOD FIT`/`TIGHT FIT`/`OVERFLOW`), approximate bullet points remaining, and a machine-readable `[METRICS_JSON]` line for agent consumption. Agents can now make data-driven add/trim decisions to optimize page utilization.
- **Extended Resume Version:** Created `Resume - Master (Extended).md` — a multi-page "wishful thinking" resume with 7 Nexus bullets (content ingestion, architectural evolution narrative), full work experience detail, and expanded technical skills.

### Changed
- **Global Paradigm Shift (Rename):** Renamed the "Brain 2" project to "Nexus" across all documentation, files, folders, and code interfaces. Ideological references to generic "Brain" remain intact.
- **Librarian System Prompt Rewrite:** Enforces a "navigate-first, search-second" strategy. Step 1 is now "review the vault structure above" (pre-injected), followed by targeted drill-down and scoped grep. Full-vault search is an explicit last resort.
- **Ignored Directories:** Added `.stfolder`, `.vscode`, `__pycache__` to `IGNORE_DIRS` in `constants.py`.
- **Eval Runner Output:** Now displays per-case duration and token count, plus aggregate token stats in the summary (prompt/output/total tokens, avg tokens/query).
- **Eval Runner Output:** Restructured `report_*.json` output to include a top-level `summary` object containing aggregate token stats, scores, and runtimes, alongside the `results` array.
- **Resume Overhaul:** Upgraded all Nexus bullet points across `Resume - Master.md` to surface previously undersold technical accomplishments: dynamic prompt injection, LLM-as-a-Judge eval pipeline, JSONL observability, 11-platform ADB scraper, dual-format resume engine, compiled meta-skills, content ingestion infrastructure. Added `LangChain`, `LangSmith`, `Whisper`, `ADB/Android`, `Telegram Bot API`, `IMAP/OAuth2` to technical skills. Compressed Handshake and VRMC sections. Tightened cover letters (Agentic AI: replaced "Project Feeder" with eval/observability story; Java: generalized addressee).
- **Render Resume Workflow:** Updated `/render_resume` workflow to document the page metrics feedback loop, agent decision rules (UNDERFILL → add content, OVERFLOW → trim), and the two-version resume strategy (Master 1-page + Extended).

### Fixed
- **YAML Frontmatter & Link Stripping:** Updated frontmatter and navigation link parsing regexes across the resume engine (`render.js`, `render_docx.py`), podcast generator (`generate_podcast.py`), and vault tools (`vault_tools.py`) to support Windows CRLF (`\r\n`) line endings, preventing frontmatter leak into rendered output.


## [1.16.0] - 2026-05-19

### Added
- **New Tool: Phone Chat Ingestion (`ingest_phone.py`):** Universal ADB screen-scraper that captures conversations from any Android app (Google Messages, Tinder, Hinge, WhatsApp, Signal, Bumble, etc.) via `uiautomator dump` and saves structured Markdown notes to `Vault/0. Inbox/`. Features include: auto-scroll to bottom before capture, multi-screen scroll with deduplication, contact name detection from toolbar, sender alignment detection (me vs them), and timestamp divider rendering. Zero dependencies (pure stdlib), zero third-party phone apps required — only USB Debugging.
- **New Skill: Project Work (`project_work`):** Enforces keeping active project notes in the vault up-to-date automatically whenever task lists are completed/modified or conceptual project plans change.


### Fixed
- **Phone Chat Ingestion (`ingest_phone.py`):** Increased empty screen tolerance from 1 to 3 consecutive screens. This prevents the scraper from prematurely terminating when encountering long voice notes or large emoji reactions that register as zero text nodes in the UI hierarchy.

### Changed
- **Analyze Health & Analyze Psych Skills:** Updated `analyze_health` and `analyze_psych` skills to mandate safely caveated, probabilistic language when discussing medical symptoms, diagnoses, or physiological mechanisms (e.g., using "may be a cause" instead of absolute declarations). Updated their descriptions in `AGENTS.md` to reflect this tone adjustment.

## [1.15.1] - 2026-05-16

### Added
- **Structured Run Logs for Librarian:** Implemented a lightweight, append-only JSONL run logger (`engine/logs/run_logs.jsonl`) that captures execution details for every vault reader query (CLI, interactive, voice, Telegram, and evals). Logs include ISO timestamp, raw query, execution status, deduplicated cited sources (extracted from tool calls and final text), errors, and sequential tool calls with arguments.

### Changed
- **Local-First Security Ignore Rules:** Updated `.gitignore` to explicitly exclude `engine/logs/` from version control, preserving the local-only nature of the user's private query history and thoughts.

## [1.15.0] - 2026-05-15

### Added
- **Shared Google Auth Module:** Created `engine/core/google_auth.py` to centralize OAuth2 handling (refreshing, token management, and browser-based auth) for all Google-integrated tools.
- **Agentic Email Tool:** Created `engine/tools/email_tool.py` containing the core IMAP and MIME parsing logic, allowing the AI Agent to import email capabilities directly.

### Fixed
- **Email Tool Imports:** Resolved a `ModuleNotFoundError` where `engine/tools/email_tool.py` could not locate the `core` package when imported from the project root. Improved path injection robustness for standalone tool execution.

### Changed
- **Email Tool Refactor:** Modularized `tools/read_email.py` into a thin CLI wrapper. It now imports its core logic from the engine and stores credentials in a dedicated, gitignored `tools/.secrets/` folder.
- **Improved Security:** Updated `.gitignore` to protect the new `tools/.secrets/` directory and transitioned to the standard `https://mail.google.com/` OAuth scope for more reliable IMAP access.

## [1.14.1] - 2026-05-14

### Added
- **New Tool: Email Reader:** Created `tools/read_email.py`, a lightweight IMAP email reader analogous to `read_webpage.py`. Fetches a single email by UID and outputs clean markdown (subject, from, date, body). Supports Gmail App Passwords via env vars (`EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `IMAP_SERVER`). Includes a `--list-recent N` flag for browsing the inbox before fetching. No external deps beyond stdlib; `python-dotenv` used optionally for `.env` loading.
- **New Tool: Webpage Reader:** Created `tools/read_webpage.py`, a lightweight, deterministic webpage scraper using `trafilatura`. Designed to provide clean markdown content for the Nexus Agentic Engine's content ingestion and career search pipelines.
- **Librarian Eval Framework:** Created `engine/evals/dataset.json` (Golden Dataset) with 12 real-world Q&A cases and `engine/evals/runner.py` for automated agent benchmarking and groundedness grading.
- **Dependency Update:** Added `python-dotenv`, `trafilatura`, and `lxml_html_clean` to the project environment and updated `requirements.txt`.

### Changed
- **Agentic Instructions Enhancement:** Updated `generate_obsidian_note` skill to mandate a `list_dir` pattern check before proposing filenames to prevent hallucinated prefixes. Added physical folder structure priority rules to resolve discrepancies with logical nesting in `Table of Contents.md`. Added mandatory **Localized Synthesis Check** rule instructing agents to scan target folders for local synthesis/hub notes and integrate external article findings into them.
- **Workflow Chaining & Synthesis:** Updated `/audit_inbox` workflow to actively identify and chain specialized downstream workflows (e.g., `/add_job_requirement`, `/ingest_medical_record`, `/distill_learning`), and enforce Localized Synthesis Integration Checks when filing articles or external research.
- **Resume Engine Refactor:** `render.js` now scans `3.1. Career Strategy & Revenue` and `3.1.3. Professional Portfolio & Evidence` for renderable markdown documents (resumes, cover letters, docs) and presents an interactive selection menu. Supports rendering one, multiple, or all documents in a single pass. Also accepts a CLI path argument for scripted/workflow use.
- **DOCX Renderer:** `render_docx.py` now accepts an optional file path argument instead of hardcoding `Resume - Master.md`. Falls back to Master Resume when no argument is given.
- **Obsidian Cleanup:** Both renderers now strip YAML frontmatter and Obsidian navigation links (`Back to:` lines) before rendering to PDF/DOCX.
- **Workflow Integration:** Integrated `read_webpage.py` into `/capture_content`, `/distill_learning`, and `/add_job_requirement` workflows to ensure clean, boilerplate-free text extraction from URLs.
- **Workflow Update:** Updated `/render_resume` workflow to reflect the new interactive document picker and non-interactive CLI mode.
- **Portfolio Restructure:** Created `Resumes/` and `Cover Letters/` subfolders inside `3.1.3. Professional Portfolio & Evidence`. Moved all resume and cover letter files (md, pdf, docx) into their respective folders. Updated `Table of Contents.md`, `render.js`, and `render_docx.py` scan paths accordingly.

---

## [1.14.0] - 2026-05-07

### Added
- **Nested Heart Architecture (Item 23):** Created a private Git repository inside `Vault/` to track personal history without polluting the public engine repository.
- **Nested Heart Tool:** Added `tools/sync_vault.py` to automate the context-switch required to commit to the nested Vault repository.
- Created `Project - Librarian Agent.md` to chart the new Agentic File System (AFS) Navigator architecture, replacing standard ChromaDB RAG.
- **Librarian Agent Implementation:** Built `engine/tools/vault_tools.py` (`read_toc`, `read_note`, `search_vault`) and the LangGraph ReAct agent (`engine/agents/librarian/agent.py`) to actively navigate the local filesystem.

### Changed
- **Agent Rules:** Added Rule 11 to `AGENTS.md` explicitly instructing agents to ignore the `Vault/.git` directory.
- Pivoted `/ask_brain` architecture from Vector RAG to Agentic Librarian to solve Context Fragmentation and preserve Zettelkasten hierarchy.
- Archived `engine/agents/rag/` into `Vault/6. Forge/6.1. Projects/6.1.4. Script Attic/Legacy RAG Engine/`.
- Updated `Project - Nexus Agentic Engine.md`, `Table of Contents.md`, and `To Do List.md` to reflect the pivot.
- Updated `engine/main.py` dispatcher to point to the new Librarian agent for CLI text queries.
- Updated `ask_brain` workflow documentation in `AGENTS.md` and `README.md` to reflect removal of vector indexing requirement.
- **Presentation Layer Centralization:** Refactored `engine/main.py` to be the sole presentation layer (using a new `print_agent_response` helper). Stripped execution and printing logic from `engine/interfaces/cli.py` and `engine/interfaces/voice.py`, turning them into pure input parsers (`parse_cli_args`, `capture_voice_query`).

### Removed
- Uninstalled `chromadb` and deleted `.chroma_db/` index and `.rag_index_manifest.json` as part of the pivot.
- Removed `engine/agents/rag/ingest_vault.py` and `engine/agents/rag/eval_rag.py` from tool index.

## [1.13.0] - 2026-05-07

### Added
- **Engine Coordinator Mode:** Upgraded `engine/main.py` from a one-off dispatcher to a persistent "Mission Control" coordinator.
  - Launches the Telegram Bot in a background thread by default for "always-on" remote access.
  - Implements an interactive CLI menu with numbered options for Text Query, Voice Query, Ingestion, and Maintenance.
- **Shared Audio Utility:** Created `engine/core/audio.py` to centralize Whisper transcription logic.

### Changed
- **Interface Refactor:** Updated `engine/interfaces/voice.py` (Local) and `engine/interfaces/telegram.py` (Remote) to use the new shared `transcribe_audio` service, eliminating redundant transcription code.
- **Improved CLI UX:** Suppressed verbose library logs (`httpx`, `telegram`) to keep the Mission Control interface clean and focused.

## [1.12.1] - 2026-05-07

### Added
- **Unified Engine Dispatcher:** Refactored `engine/main.py` into a central dispatcher that handles CLI, Voice, Telegram, and Ingestion via flags (`--voice`, `--telegram`, `--ingest`).
- **Engine Interfaces Layer:** Created `engine/interfaces/` to isolate entry-point logic (`cli.py`, `voice.py`, `telegram.py`) from core agent logic.
- **PowerShell Command Sync:** Added `brain-telegram` function and updated `ask-brain`, `brain-voice`, and `ingest-vault` in the Windows PowerShell profile to use the unified `main.py` entry point.

### Changed
- **Architectural Cleanup:** Deleted redundant root-level wrappers (`engine/ask_brain.py`, `engine/brain_voice.py`, `engine/brain_telegram.py`) in favor of the unified dispatcher.
- **Agent Modularity:** Moved `execute_rag_query` and `ask_librarian` from `engine/main.py` to `engine/agents/rag/agent.py`.
- **Ingestion Refinement:** Updated `engine/agents/rag/ingest_vault.py` with a proper `main()` entry point and fixed internal module pathing for the new architecture.

### Fixed
- Corrected a module import shadowing issue in `ingest_vault.py` by using absolute package imports for RAG tools.

## [1.12.0] - 2026-05-07

### Added
- **Incremental Indexing (Phase 8):** `engine/ingest_vault.py` now tracks file modification times via a JSON manifest (`.rag_index_manifest.json`) and only re-embeds files that have changed since the last run. Added `--force` flag for full re-indexing.
- **Orphan Cleanup (Phase 8):** After each ingestion run, the system queries ChromaDB for entries whose source files no longer exist on disk and purges them automatically.
- **Frontmatter Metadata Extraction (Phase 8):** Ingestion now parses YAML frontmatter (`tags`, `type`) and derives a `domain` category (health, career, tech, etc.) stored as ChromaDB filterable metadata on every chunk.
- **Filtered Search (Phase 8):** `engine/main.py` now accepts `--domain`, `--tag`, and `--type` CLI flags that generate ChromaDB `where` clauses to constrain retrieval by metadata.
- **Schema Foresight Audit (Phase 8):** Documented current metadata distribution (1,577 chunks, 60% domain-tagged) and evaluated future fields (`word_count`, `date_created`, `confidence`) with accept/defer/reject decisions.
- **Phase 8.5 Tech Debt Tracked:** Flagged that ~60% of `engine/core/` and `engine/tools/` is RAG-specific code that should be scoped to `engine/agents/rag/` before building domain agent #2.
- **RAG Module Consolidation:** Moved RAG-specific utilities (`ingest_vault.py`, `eval_rag.py`, `eval_dataset.json`) from `engine/` root to `engine/agents/rag/` to ensure a clean boundary between the dispatcher and domain-specific RAG logic. Updated all internal paths and added `sys.path` bootstrapping to maintain CLI script functionality.

### Changed
- Replaced raw `sys.argv` parsing in `engine/main.py` with `argparse` for structured CLI flag support.
- Moved index manifest logic to `engine/agents/rag/index_manifest.py` (RAG-scoped, not shared core).
- **Module Ownership Cleanup (Phase 8.5):** Refactored the engine's internal structure to improve modularity and prepare for multi-agent support.
  - Moved RAG-specific constants from `engine/core/constants.py` to `engine/agents/rag/constants.py`.
  - Moved `AgentState` from `engine/core/state.py` to `engine/agents/rag/state.py`.
  - Relocated RAG-specific tools (`chroma_tool.py`, `text_utils.py`) from `engine/tools/` to `engine/agents/rag/tools/`.
  - Updated all internal imports across the engine (`main.py`, `ingest_vault.py`, `nodes.py`, `graph.py`, `eval_rag.py`) to reflect the new scoped architecture.

---

## [1.11.4] - 2026-05-06

### Added
- **Domain-specific Sources Architecture:** Created `Sources/` subfolders in all 14 subsections of `6.2. Library & Learning` to separate raw captures from synthesized concept notes.

### Changed
- **Library Organization:** Relocated technical articles (IBM Granite, VALID Framework, TRIBE v2) from domain roots into specialized `Sources/` subfolders.
- **TOC Refinement:** Standardized the Table of Contents with `📁 Sources` headers for all technical domains.
- **Workflow Refinement:** Updated `/audit_inbox` to avoid adding granular inbox items directly to the Table of Contents and to use existing hubs, MOCs, project notes, logs, or folders for routine filing.
- **Documentation Sync:** Refreshed `/audit_inbox` descriptions in `AGENTS.md` and `README.md` to reference the current Brain Inbox and Quick Capture paths.

---

## [1.11.3] - 2026-05-06

### Added
- **Telegram Bot Integration:** Created `engine/brain_telegram.py` to provide a remote, smartphone-friendly interface to the RAG Agent.
- **Voice-first RAG Query:** Implemented `engine/brain_voice.py` to capture microphone input via OpenAI Whisper.
- **Enhanced YouTube Transcripts:** Updated `tools/youtube_transcript.py` to save Obsidian-ready markdown notes directly to `Vault/Inbox` with YAML frontmatter and video title fetching.
- **Workflow Refinement:** Updated `/distill_learning` to include a mandatory redundancy check, prioritizing the augmentation of existing notes over creating duplicates.

### Changed
- **Architectural Refactor:** Extracted core LangGraph execution into `execute_rag_query` in `engine/main.py` to unify the RAG pipeline across CLI, Voice, and Telegram interfaces.
- **Podcast Generation Tool:** Refactored `tools/generate_podcast.py` to process a single markdown file specified via command-line argument instead of scanning the entire Vault. Added a `--force` flag to bypass modification time checks.
- **Telegram UX Refinement:** Removed source citations from Telegram responses to optimize for mobile display and avoid broken `obsidian://` deep links on mobile clients.
- **Voice Note Support:** Added secure `.ogg` voice note transcription for the Telegram bot, bridging the Phase 6A Whisper logic to mobile.
- **RAG Retrieval Quality Enhancements (Phase 7):**
  - **Eval Framework:** Created `engine/eval_rag.py` using an LLM-as-a-judge approach and `engine/eval_dataset.json` to systematically test the agent's accuracy against a golden dataset.
  - **Similarity Threshold:** Added a cosine distance filter (`SIMILARITY_THRESHOLD = 0.7`) to drop low-quality retrieval chunks before they pollute the context window.
  - **HyDE (Hypothetical Document Embedding):** Modified the `retrieve` node in `engine/agents/rag/nodes.py` to generate a hypothetical perfect answer using GPT-4o before vector search, bridging the vocabulary gap between short user queries and dense markdown notes.
  - **LLM Re-Ranking:** Added an LLM-based re-ranker step to score and sort the top retrieved chunks from ChromaDB, drastically improving the signal-to-noise ratio.


## [1.11.2] - 2026-05-05

### Changed
- **RAG Engine Modularization:** Completed the architectural refactor of the RAG system from flat scripts into a scalable, modular engine:
  - `engine/core/`: Shared constants and state definitions.
  - `engine/agents/rag/`: Isolated RAG nodes and LangGraph definitions.
  - `engine/tools/`: Atomic utilities for ChromaDB, text splitting, and vault crawling.
  - `engine/main.py`: New universal dispatcher for multi-agent support.

### Fixed
- **RAG Engine:** Corrected import path errors in modularized components to ensure reliable execution from the project root.

---

## [1.11.1] - 2026-05-04

### Changed
- **Resume Engine:** Integrated `tools/resume_engine/render_docx.py` into `render.js`. Running the Node.js renderer now automatically triggers the Python DOCX renderer using the project's virtual environment, ensuring both PDF and DOCX formats are generated in a single pass.
- **Workflow:** Updated `/render_resume` to consolidate PDF and DOCX rendering into a single step, reflecting the tool integration.

---

## [1.11.0] - 2026-04-28

### Added
- Created the `archive_project` agentic skill to systematically manage and archive completed projects while maintaining contextual Vault architecture.

### Changed
- Executed **Radical Transparency Public Release Strategy**:
  - Restructured `.gitignore` to use a robust wildcard approach (`Vault/**`) to untrack all vault content files while retaining folder structure and `.gitkeep` files.
  - Added `.gitattributes` rule to explicitly exempt `Vault/Table of Contents.md` from `git-crypt` encryption, establishing it as the public-facing cognitive map.
  - Untracked 200+ personal vault files from the repository via `git rm --cached` while preserving local copies.
  - Rewrote `README.md` to articulate the "Human Context Statement" and document architectural methods (Engine/Vault separation, Agentic Config mirror).
  - Verified `AGENTS.md` as public-facing agentic constitution.
  - Formally licensed the repository under AGPL-3.0.

---

## [1.10.2] - 2026-04-27

### Added
- Added `ipython` and `langchain-tavily` to `requirements.txt` for agent development and updated Tavily integration.

---

## [1.10.1] - 2026-04-23

### Changed
- **Resume Engine:** Updated `render.js` to automatically save a copy of the generated PDF to the user's `Downloads` folder for easier access.
- **Generalization:** Removed hardcoded names from the resume engine and workflow. The output PDF filename is now dynamically extracted from the first H1 header in the Markdown source.

---

## [1.10.0] - 2026-04-22

### Added
- **Career Counselor Skill:** Implemented `career_counselor` agentic skill to act as a high-stakes career architect.
  - Mandates synthesis of three pillars: Career Strategy (3.1), Technical Evidence (6.1), and Cognitive Architecture (2.3).
  - Integrated `search_web` for real-time market alignment and compensation benchmarking.
  - Enforces non-sycophantic, analytical advice grounded in the "AI Superagency" and "Proof of Work" frameworks.

---

## [1.9.0] - 2026-04-21

### Added
- **RAG Engine Integration:** Implemented a Retrieval-Augmented Generation (RAG) system for semantic search across the entire Vault.
  - Added `engine/ingest_vault.py` for indexing markdown notes into a local ChromaDB vector store.
  - Added `engine/ask_brain.py` as a RAG query agent to provide grounded answers with citations.
  - Added `/ask_brain` agentic workflow to allow natural language vault queries via slash command.

---

## [1.8.4] - 2026-04-16

### Added
- **LangGraph Integration:** Formally integrated `langgraph` and `langchain-openai` into the development stack to start development of AI agent orchestration.
- **Vault Restructure:** Created new `6.2.12. AI for Science & Healthcare` section to un-clutter Agent frameworks. Shifted `Robotics` (now 6.2.13) and `AI Ethics` (now 6.2.14) down.

### Changed
- **Environment Management:** Updated `requirements.txt` with new dependencies for stateful agent development.
- **Hygiene:** Verified global Python 3.12 install remains pristine (pip-only) while project environment manages 60+ specialized libraries.

---

## [1.8.3] - 2026-04-14

### Changed
- Upgraded `analyze_health` skill (Step 9 & 10: Update the Vault) to explicitly mandate active narrative restructuring and visual re-weighting of `Health Summary.md`. Added strict requirements for table hygiene (re-sorting, consolidation) and mandatory syncing of medical action items to the master `To Do List.md`.

---

## [1.8.2] - 2026-04-13

### Changed
- Promoted **Career Strategy & Revenue** from `3.3` to `3.1` to align with priority and daily usage.
- Re-ordered Section 3 (Operations & Wealth) folders: Wealth & Asset Management shifted to `3.2`, Infrastructure & Logistics shifted to `3.3`.
- Updated `Table of Contents.md` and `README.md` to map to the new hierarchy.
- **Fixed:** Reconstructed broken `.venv` configuration caused by absolute path fragmentation (moved from `Knowledge Base`).
- **Added:** Integrated `openai`, `langgraph`, `httpx`, and `python-dotenv` into `requirements.txt` for agentic development.
- **Added:** Created `sandbox_langgraph.py` in `Vault/6. Forge/6.1. Projects/6.1.2. Agentic R&D/` for isolated state machine testing.

---

## [1.8.1] - 2026-04-12

### Added
- In `generate_obsidian_note` skill (Formatting and Structure section), mandated the use of synchronized horizontal navigation bars for "tight clusters" of notes (e.g., Auto, Health, Career) to allow lateral movement between related Map of Content (MOC) notes.

### Changed
- Refactored **Rules 4 & 5** in `AGENTS.md` into a single unified **Git & Changelog Policy** with a structured decision table to eliminate model ambiguity at rule execution time. Previously, two prose rules with overlapping scope caused false-positive commits for routine note/TOC-link additions.
- Implemented **Compiled Portability Architecture** across core skills:
  - Added strict Compiler Rules to `maintain_project_docs` to force verbatim YAML transcription into `AGENTS.md` to prevent context drift.
  - Refactored `skill_creator` and `workflow_creator` to delegate `AGENTS.md` updates to `maintain_project_docs`.
  - Wrapped `AGENTS.md` lists in strict `<!-- AUTO-COMPILED -->` warnings to preserve system portability.
  
---

## [1.8.0] - 2026-04-11

### Changed
- Executed **Vault Structural Refactor & Friction Reduction** (Roadmap Item #5):
  - Moved **`Inbox/`** and **`Quick Capture.md`** out of deep nesting into the Vault root (`0. Inbox/`, `0. Quick Capture.md`) to eliminate capture friction.
  - Re-allocated **`Memories`** and Journaling into **`1.1. Philosophy & Personal North Star / Personal Logs`**, rather than creating an unnecessary extra section format.
  - Split Personal Logs into `Daily Notes (Journal)` for stream-of-consciousness, and `Memories/` for curated milestones and Trophy Case.
  - Renamed `5. Capture & Archive` subsections to reflect the removal of the Brain Dump.
- Updated `audit_inbox` and `capture_content` workflows to use the new zero-friction paths.
- Updated `Table of Contents.md` and `README.md` to reflect the new architecture.

---

## [1.7.0] - 2026-04-11

### Added
- Created new educational sections in **6.2 Library & Learning**:
  - **6.2.3. Algorithms & Data Structures**: Core CS fundamentals for technical depth and interview preparation.
  - **6.2.4. System Design & Distributed Systems**: Architectural principles for scaling complex systems.
  - **6.2.11. Knowledge Graphs & GraphRAG**: Integrated graph theory and applied graph-based retrieval into the NLP and Math domains.
- Added boilerplate study frameworks for all new sections to facilitate future knowledge synthesis.
- Added `.gitkeep` to new empty folders to ensure structural tracking in Git.

### Changed
- Re-architected Section **6.2 Library & Learning** for optimal pedagogical flow:
  - Moved **Data Engineering (6.2.5)** before Machine Learning to treat it as a prerequisite.
  - Grouped all Deep Learning application domains (NLP, Computer Vision, Reinforcement Learning) into a continuous sequence (6.2.8 - 6.2.10).
  - Promoted **Intelligent Agents (6.2.11)** as the culmination of the Deep Learning sequence.
- Renamed the master index alias from "Table of Contents" to include "Map of Content" (MOC) to reflect the Zettelkasten organizational paradigm.
- Updated `README.md` directory tree to reflect the deep restructure of the Forge.

---

## [1.6.2] - 2026-04-07

### Added
- Created new Vault section **2.5. Mom's Health Tracking** in the TOC and filesystem.
- Implemented **Mom's Health Summary** dashboard for centralized symptom, medication, and visit tracking.
- Created `Mom_Health_Logs` and `Mom_Lab_Work` folder structure for clinical record organization.
- Added `2.5. Mom's Health Tracking/` to the `README.md` directory tree.
- Created `tools/medical_xml_parser.py` script to parse complex HL7 CDA medical XML files into structured Markdown.
- Added `/ingest_medical_record` workflow to automate standardizing and importing raw patient records.

### Changed
- Upgraded `analyze_health` skill to optionally integrate checking Section 2.2 Medical insurance coverage documents for realistic financial/logistical medical planning.
- Standardized `analyze_health` skill to support multi-profile diagnostics (handling multiple health summaries like Mom's vs. Primary) via patient-context switching.

## [1.6.1] - 2026-04-05

### Changed
- Upgraded `analyze_health` skill with mandatory `search_web` step before forming any diagnostic hypothesis or treatment recommendation:
  - Open-ended recency queries (no year pinning — uses "latest", "current guidelines" language)
  - Evidence quality hierarchy: meta-analyses > RCTs > guidelines > case reports
  - Explicit instruction to surface conflicting evidence rather than defaulting to most recent
- Upgraded `analyze_psych` skill with the same web research step:
  - Open-ended recency queries; vigilance flags for psychedelic-assisted therapy, sleep science, neuroinflammation, gut-brain axis
  - Same evidence quality hierarchy and conflict-surfacing rule
- Added mandatory **Source Citation** rule (step 7) to both `analyze_health` and `analyze_psych` skills:
  - Preferred source hierarchy defined per skill (PubMed/NCBI, Cochrane, domain-specific clinical guidelines, Mayo Clinic, Cleveland Clinic, JAMA/NEJM/Lancet, NIH)
  - Blocklist: wellness blogs, product sites, Reddit, non-peer-reviewed sources
  - Mandatory inline markdown link format beside each claim
  - Fallback: cite institution + document name if direct URL unavailable
  - Links must be written into Vault note updates for persistent reference

## [1.6.0] - 2026-04-05

### Added
- New meta-skill `skill_creator` — moved from `Vault/SKILL.md` into `.agents/skills/skill_creator/SKILL.md`. Covers full skill anatomy, progressive disclosure, writing patterns, and eval guidance.
- New meta-skill `workflow_creator` — `.agents/skills/workflow_creator/SKILL.md`. Covers workflow anatomy, format rules, overlap resolution, sharp descriptions, and registration checklist. Mirrors `skill_creator` for the workflow domain.
- Both new skills registered in `AGENTS.md`, `README.md`, and `List - Agentic Instructions.md`.

### Changed
- Standardized all 6 existing skills against the `skill_creator` spec:
  - Added missing `name:` frontmatter field to `cleanup_orphans`, `conventional_commits`, `generate_obsidian_note`, `maintain_project_docs`.
  - Upgraded all weak descriptions to "pushy" triggering language (explicit context cues and imperative phrasing).
  - Fixed typo in `maintain_project_docs` description ("warrent" → "warrant").
  - Removed redundant `## Trigger` body sections from `analyze_health` and `analyze_psych` — trigger logic consolidated into `description:` only.
- Standardized all 8 workflows:
  - Removed redundant `## Trigger` body sections from `add_job_requirement`, `audit_inbox`, `create_project`, `distill_learning`, `plan_activity`, `render_resume`.
  - Sharpened overlapping descriptions on `capture_content`, `distill_learning`, and `create_new_note` — each now explicitly cross-references the other two to prevent agent confusion.

## [1.5.1] - 2026-04-01

### Added
- Implemented `/capture_content` workflow and agentic scaffolding (Template, SKILL updates) for logging videos, articles, and raw snippets.
- Created `tools/youtube_transcript.py` script to extract YouTube video transcripts directly to text files.
- Added `youtube-transcript-api` to `requirements.txt`.

## [1.5.0] - 2026-03-31

### Added
- Added `analyze_psych` agentic skill to provide science-based, non-sycophantic psychological support and cognitive architecture analysis.
- Mandatory context check of Section 2.3 ("Psych") in the TOC before providing emotional or mental health support.
- Updated `AGENTS.md`, `README.md`, and `Workshop - Agentic Instructions.md` to register the new skill.
- New Vault subsections under `2.2. Medical/`: `Health Logs/` (doctor visit notes) and `Lab Work/` (bloodwork results).
- New Vault subsections under `3.3. Career Strategy & Revenue/`: `3.3.2` through `3.3.6` (Interview Prep, Portfolio, Networking CRM, Income Streams, Compensation).
- Updated `README.md` directory tree to reflect all new subsections.
- Updated `Table of Contents.md` with wiki-links for all new Health Logs and Lab Work notes.

### Fixed
- Fixed stale references in `audit_inbox.md`, `add_job_requirement.md`, and `create_project.md`.
- Updated `create_project.md` to include mandatory registration in the `To Do List`.
- Updated `distill_learning.md` to optionally update `Current Learning.md` with new study materials.
- Significant improvements to `AGENTS.md`: fixed Rule 4 typo, added deterministic Tools documentation (Python scripts and Resume Engine), and added Rule 11 for mandatory `To Do List` registration for projects/protocols.

## [1.4.0] - 2026-03-30

### Added
- Added `analyze_health` agentic skill to enforce reading Section 2 of the TOC and performing comprehensive context checks before analyzing user health issues.
- Updated `AGENTS.md` to register `analyze_health` as a mandatory behavior skill.

## [1.3.0] - 2026-03-21

### Added
- Implemented `resume-engine` tool for generating professional PDF resumes from Markdown sources.
- Added `tools/resume_engine/` directory with `render.js` script and `style.css`.
- Updated `AGENTS.md` to include `resume-engine` as a deterministic capability for generating resumes.
- Added `tools/resume_engine/package-lock.json` for dependency management.

### Changed
- Deepened `README.md` repository structure to show one more header level (H2 equivalent) for all primary Vault sections.
- Added concise descriptive comments to all Vault and Agent Workflow files in the `README.md` directory tree for improved clarity.

## [1.2.0] - 2026-03-20

### Added
- Implemented `git-crypt` for transparent, local-only encryption of all Vault contents (`Vault/**`) before syncing to GitHub.
- Added strict ignore rules to `.gitignore` to prevent committing the `git-crypt` master key and other sensitive credential files.
- Updated `AGENTS.md` and `conventional_commits` skill to explicitly enforce batching of commits and pushes (forbid micro-commits).
- Added Production Engineering - Meta job listing to `Employer Skill Requirements.md` and refreshed the AI summary.
- Transitioned to an "Engine-only" Git policy: AI agents will no longer commit individual notes or "thoughts" in the `Vault/` directory, focusing Git operations on tools, skills, workflows, and project structure.

## [1.1.0] - 2026-03-19

### Added
- Four new Agentic Workflows to simplify knowledge management and cognitive load:
  - `/audit_inbox` — Zettelkasten maintenance and raw note structuring.
  - `/create_project` — Task extraction and project planning from raw notes.
  - `/distill_learning` — Concept extraction and atomic note generation from complex papers/articles.
  - `/plan_activity` — Intelligent itinerary generation using relationship/activity data.
- Updated `Protocol - System Maintenance.md` to include running `/audit_inbox`.

## [1.0.4] - 2026-03-19

### Added
- `Vault/Sensitive/` folder for sensitive notes/files gitignored

### Changed
- Renamed `scripts/` to `tools/`.
- Updated `AGENTS.md` and `README.md` to reflect the new unified "Tools & Workflows" structure.
- Updated `conventional_commits` skill and `AGENTS.md` to require TOC section references for Vault changes in git commit messages.
- Updated `maintain_project_docs` skill and `AGENTS.md` to require README, CHANGELOG and AGENTS.md updates when needed & to maintain README's vault structure diagram.
- Put section 3.Forge at the end of the TOC b/c it's so big. Changed TOC & folder structure.
- Added "Brain Functions & Automation" conceptual framework to `README.md` and `AGENTS.md` to clarify the use of Active Procedures (Workflows) vs. Deterministic Capabilities (Tools).

### Removed
- Section 3.2.12 - "Career" - moved to section 4.3

## [1.0.3] - 2026-03-18

### Added
- Note generation rules enforcing prefixed filenames (`Project -`, `Protocol -`, etc), banning redundant H1 headers, and moving the Table of Contents link to the top of the file
- Rule 10 in `AGENTS.md` enforcing `.gitkeep` files for empty directories.
- Folder maintenance scripts: `scripts/create_folders.py`, `scripts/check_folders.py`, and `scripts/add_gitkeeps.py`.
- `/add_job_requirement` workflow for automated PDF/URL job criteria extraction.

### Changed
- Moved all python scripts into the `scripts/` root directory.
- Updated all script references across `README.md`, `CHANGELOG.md`, and `AGENTS.md`.
- Readjusted relative paths in `scripts/generate_podcast.py`.

## [1.0.2] - 2026-03-17

### Changed
- Updated documentation to use conventional "Affirm Vault Structure" language instead of deprecated sync_vault.py
- Updated `AGENTS.md` rules to require `CHANGELOG.md` updates and `git push` on every commit.

### Removed
- All active references to `sync_vault.py` from `AGENTS.md` and `README.md`


## [1.0.1] - 2026-03-16

### Added
- "Middle ground" TOC header structure in section 3.2 (3.2.x numbered, children unnumbered)
- Top-level files in `Vault/` created to match full TOC structure
- Added new category files and documentation
- New CSS snippet `headers.css` for custom header styling in Obsidian

### Changed
- Relocated Library & Learning resources from `Vault/` root to `Vault/3. Forge/`

### Removed
- `sync_vault.py` — script deleted in favor of direct agentic structure management

## [1.0.0] - 2026-03-14

### Added
- `scripts/generate_podcast.py` — converts all Vault notes to MP3 via edge-tts
- `sync_vault.py` — syncs Vault folder structure with Table of Contents H1 sections
- `AGENTS.md` — central AI agent constitution for the repository
- `README.md` — project documentation with setup, scripts, and structure
- `requirements.txt` — pinned Python dependencies
- `.agents/skills/generate_obsidian_note` — skill for creating Zettelkasten-formatted notes
- `.agents/skills/sync_vault_structure` — mandatory skill for folder/TOC sync
- `.agents/skills/maintain_project_docs` — mandatory skill for requirements.txt and README updates
- `.agents/skills/conventional_commits` — mandatory skill for commit message format
- `.agents/workflows/create_new_note` — end-to-end note creation workflow
- Vault folder structure created for all 12 TOC sections
- `.gitkeep` normalisation across all empty Vault folders

### Changed
- Reorganised repo: moved all Obsidian content into `Vault/` subfolder
- `scripts/generate_podcast.py` resolves edge-tts from `.venv` automatically
- `.gitignore` updated to exclude `.venv/`, `Vault/Audio/`, and `podcast_history.json`
