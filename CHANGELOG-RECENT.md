# Changelog (Recent)

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
