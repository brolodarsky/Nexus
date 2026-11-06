# Changelog (Recent)

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [3.3.0] - 2026-11-05

### Added
- **Atomic File Move & Delete Tools (`src/nexus/shared_tools/shared.py`):** Added `@tool move_file(source_path, destination_path, reasoning, overwrite=False)` and `@tool delete_file(file_path, reasoning)` to the core tool library, enabling clean note relocation and archival (e.g. concluded Missions from `Campaign - */` to `Archive/YYYY/`) without leaving orphaned active documents on disk.
- **Core Tool Binding (`src/nexus/agent/graph.py`):** Bound `move_file` and `delete_file` into `CORE_TOOLS`, granting direct access to both the primary orchestrator (`NexusAgent` / Astra) and parallel subagents spawned via `spawn_subagent`.
- **HITL Two-Phase Commit Schema & Handlers (`src/nexus/core/hitl_queue.py`):**
  - Added `destination_file TEXT` column to `transactions` and `revisions` with automatic idempotent schema migrations in `init_db()`.
  - Added atomic commit and rollback support for `action_type="move"` and `action_type="delete"`:
    - Pre-commit stale-base verification ensuring source files have not drifted on disk in Obsidian.
    - Destination collision guards preventing un-flagged overwrites.
    - Pre-commit snapshots in `revisions` enabling 100% reversible rollbacks (re-linking deleted files or moving files back to source).
    - Updated `get_pending_for_file` to match across both `target_file` and `destination_file`.
    - Updated `read_file` to surface staged relocation and deletion warning banners.
- **FastAPI Endpoints (`src/nexus/api/routers/hitl.py`):** Added `destination_file` to `TransactionResponse` and `MockTransactionRequest`.
- **Next.js Control Panel Integration (`gui/src/app/hitl/page.tsx`, `gui/src/lib/api/hitl.ts`):** Updated HITL UI to display `source → destination` relocation arrows across ticket items and headers, render pre-commit deletion warnings, and preview destination relocation badges.
- **Unit Test Suite (`tests/test_hitl_commit.py`):** Added test coverage for `commit_transaction` and `rollback_transaction` on moves and deletions, stale-base detection on human edits, collision detection, and tool invocation guards (112 passing pytest tests).
- **Mobile Bottom Navigation Bar (`Sidebar.tsx` & `layout.tsx`):** Added a fixed `h-16` bottom navigation bar (`md:hidden`) with backdrop blur, iOS safe-area bottom inset padding, and compact icon+label tabs (`Home`, `Chat`, `Vault`, `Tools`, `HITL`, `Audit`), plus `pb-16 md:pb-0` on `<main>` while keeping the desktop collapsible `Sidebar` (`hidden md:flex`) 100% unchanged.
- **Mobile Slide-Over Conversation & Blackboard Drawers (`ChatHeader.tsx`, `ChatSidebar.tsx`, `BlackboardDrawer.tsx`, `chat/page.tsx`):** Added a mobile hamburger/threads trigger in `ChatHeader` that opens `ChatSidebar` as a slide-over overlay drawer with backdrop on `< 768px` viewports, defaulted the Blackboard drawer to closed on mobile (and rendered it as a slide-over overlay when opened), and set `ChatInputBar` to `text-base` (`16px`) on mobile to prevent iOS Safari viewport auto-zoom.
- **Per-Conversation Draft Persistence (`gui/src/components/chat/types.ts`):** Added `CHAT_DRAFTS_STORAGE_KEY` (`nexus_chat_drafts`), `DRAFT_NEW_KEY` (`_new`), and `loadPersistedDrafts` / `persistDrafts` helpers with automatic backward-compatibility migration for legacy single-draft storage.
- **Sidebar Draft Indicators (`gui/src/components/chat/ChatSidebar.tsx`):** Added visual `Draft` indicator pills next to conversation titles and on the "New Chat" button when unsubmitted drafts are saved, as well as cyan dot indicators on collapsed sidebar icons.
- **Dynamic Host Resolution in Next.js Client (`gui/src/lib/api/client.ts`):** Added `getApiBase()` helper that dynamically detects the client origin hostname (`window.location.hostname`) in browser sessions, automatically routing API requests, SSE streams, resume artifact downloads, and podcast audio to the host machine's port 8000 when accessed over Tailscale (`http://100.x.y.z:3000`) or LAN (`http://192.168.x.y:3000`), with `NEXT_PUBLIC_API_URL` override support and SSR fallback to `http://127.0.0.1:8000`.
- **Installable Mobile PWA Metadata (`gui/src/app/manifest.ts` & `gui/src/app/layout.tsx`):** Added Web App Manifest route (`MetadataRoute.Manifest`) with standalone display mode, dark background and theme colors matching the design system (`#06080f` and `#0a0a0f`), maskable application icons, and dedicated Next.js `Viewport` export with iOS `appleWebApp` translucent status bar configuration.
- **Tailscale and LAN Discovery Banner (`start.ps1`):** Added automated network interface inspection on startup that extracts the machine's Tailscale IPv4 (`100.x.y.z`) and private LAN IPv4 (`192.168.x.y` / `10.x.y.z`), printing clickable mobile access URLs directly to the terminal banner.
- **Thread-Scoped Shared Agent Blackboard (`src/nexus/core/blackboard.py`, `src/nexus/agent/graph.py`, `src/nexus/shared_tools/shared.py`, `src/nexus/api/routers/board.py`):** Added `thread_id TEXT` column, automatic schema migration in `init_board_db()`, and SQLite index `idx_bulletins_thread_id` to isolate subagent bulletins to active conversation threads.
- **Ambient Execution Context Propagation:** Subagents spawned in parallel or tools calling `post_to_board` / `read_board` automatically inherit and normalize their parent thread ID via ambient HITL execution context (`_resolve_effective_thread_id`), preventing point-in-time sweeps (Gmail, Calendar, Vault scans) from leaking into unrelated conversations.
- **Thread-Scoped Bulletin Deletion & REST API:** Added `thread_id` query filtering to `GET /api/board` and thread-specific unpinned deletion in `DELETE /api/board` (`clear_bulletins(thread_id=...)`), leaving bulletins in other sessions intact.
- **Dynamic Next.js Blackboard Feed (`gui/src/components/chat/BlackboardDrawer.tsx`, `gui/src/app/chat/page.tsx`, `gui/src/lib/api/board.ts`):** Wired `BlackboardDrawer` to track `activeConvId` in the Next.js Chat interface, showing thread-scoped bulletins, clearing only within the active session, and presenting an empty-state card for fresh conversations.
- **Unit Test Suite (`tests/test_blackboard.py`):** Added 4 test suites verifying thread filtering, cross-thread isolation during clear, ambient execution context inheritance, and idempotent schema migration adding `thread_id` to legacy un-scoped tables (11 total passing tests).

### Changed
- **AgentTracer Telemetry Window Headers: Renamed Commander to Head Agent & Inline Tool Call Parameters (`src/nexus/agent/`, `gui/src/`):**
  - Renamed the root commander agent from generic `"nexus"` / `"NexusAgent"` to **`"Head Agent"`** across console tracer (`nexus_tracer = AgentTracer("Head Agent", ...)`), HITL execution context roles (`Head Agent (<tier>)`), and UI step card badges (`TraceStepCard`).
  - Child subagents retain their clean thread-safe serial IDs (`subagent-1`, `subagent-2`, ...), creating an intuitive visual hierarchy: `Head Agent` $\to$ `subagent-1`, `subagent-2`.
  - Promoted tool call parameters directly into window headers next to the tool name (`tool_name(k1=v1, k2=v2)`), formatted cleanly via `formatHeaderArgValue` with newline sanitization, key-value highlighting, and full tooltip previews.
  - Eliminated the redundant collapsed preview body underneath `tool_call` windows (`evt.type !== "tool_call"`), keeping collapsed tool cards as a single, clean, high-density line.
  - Synchronized DAG node cards in `AgentGraphView` to display explicit `Head Agent (Root)` and `sub.id` badges alongside display labels.
  - Updated `ChatMessageItem.tsx` and `AuditPage` (`gui/src/app/audit/page.tsx`) to display `Head Agent` and inline tool call parameters consistently across chat bubbles and the Subagent Fleet inspector.
- **Default Disclosure & Expand/Collapse Functionality for AgentTracer Telemetry Windows (`gui/src/components/AgentTraceVisualizer.tsx`):**
  - Updated individual trace step cards (`TraceStepCard`) to mount collapsed by default (`isOpen = false`), replacing forced wide-open disclosures that produced massive vertical walls of text during runs.
  - Fixed non-functional Expand/Collapse button on individual step cards: replaced static `forceExpanded || localOpen` boolean short-circuit with synchronized `useEffect` state updates and decoupled individual click handlers, allowing step details to expand or collapse freely.
  - Added dedicated, accessible Expand/Collapse toggle buttons (`▾ Collapse All` / `▸ Expand All`) to `AgentGraphView` (both for the active Node Deep-Dive Inspector and the chronological steps list), ensuring users inspecting DAG nodes can collapse or expand all execution payloads in a single click.
  - Made the initial task prompt card and final assistant synthesis card in `AgentGraphView` collapsible by default with functional `▾ Collapse` / `▸ Expand` controls and clamped 2-line preview fallbacks.
  - Updated `ThinkingPanel` to initialize `expandAllSteps = false` and wired the toolbar toggle to cascade collapse/expand triggers to all child trace cards.
- **HITL Review Queue & GUI Inspector Tile Hierarchy (`gui/src/app/hitl/page.tsx`):**
  - Promoted the tool name / action (`modify`, `create`, `move`, `delete`, `write_file`) to the colored top header position across review queue tiles and inspector badges, rendering with semantic color theming (`getActionTheme`: rose for deletions, emerald for creations, violet for relocations, and amber for modifications).
  - Maintained the primary filename header intact (`{target_file} → {destination_file}` or `{target_file}`).
  - Relocated the ticket number (`Ticket #{id}`) down into the secondary metadata row where the action type was previously placed, preserving clean alignment alongside agent role, agent ID, conversation ID, and thread provenance pills.
  - Updated collapsed queue rail tooltips to reflect the action-first hierarchy (`[{action}] {file} · Ticket #{id}`).
- **Mobile-Responsive HITL Diff Reviewer (`hitl/page.tsx`) & Workspaces (`vault/page.tsx`, `audit/page.tsx`, `tools/page.tsx`, `PinnedNotesReader.tsx`):** Stacked HITL, Vault Explorer, and Audit Log queues vertically on mobile (`flex-col md:flex-row`), dynamically configured Monaco `DiffEditor` with `renderSideBySide: false` (inline unified diff) when viewport width `< 768px`, and made Approve / Reject / Rebase controls thumb-friendly on mobile screens.
- Standardized canonical access on the Next.js + FastAPI Control Panel (`start.ps1`, `gui/`, `src/nexus/api/`) and headless agent execution (`python -m nexus.agent.api`).
- Updated `src/nexus/agent/api.py` docstring to eliminate legacy interface call sites.
- Cleaned `README.md` repository tree and meta-scripts table to remove all references to legacy pre-GUI interfaces and entrypoints.
- **LAN & Tailscale CORS Permissiveness (`src/nexus/api/main.py`):** Configured Starlette `CORSMiddleware` with `allow_origin_regex` to permit requests from localhost, RFC 1918 private subnets (`192.168.*`, `10.*`), Tailscale CGNAT addresses (`100.*`), and Tailscale MagicDNS domains (`*.ts.net`) with full credential and header support.
- **Universal Network Listener Binding (`start.ps1`):** Configured FastAPI `uvicorn` (`--host 0.0.0.0 --port 8000`) and Next.js dev server (`npx next dev -H 0.0.0.0 -p 3000`) to bind to `0.0.0.0`, allowing mobile devices to connect seamlessly without proxy buffering.
- **API Callers Refactor (`gui/src/lib/api/stream.ts`, `tools.ts`, `vault.ts`):** Migrated stream, PDF/DOCX compiler URL, and podcast audio endpoints to call `getApiBase()` dynamically.

### Fixed
- **Chat Page Initial Active Conversation Restoration (`gui/src/app/chat/page.tsx`):** Fixed race condition where active conversation state initialized to `null` on mount prematurely wrote `"__new__"` to `ACTIVE_CONV_STORAGE_KEY` before conversations resolved from SQLite, causing the chat page to always default to an empty screen rather than loading the most recent conversation (`convos[0]`). Guarded persistence effect with `isInitialLoadDoneRef`, ensured `savedActiveConv` is restored when valid, and defaulted to `convos[0].id` when refreshed or returned to.
- **Agent Responses Auto-Refresh & SSE Stream Keep-Alive (`src/nexus/api/routers/agents.py`, `gui/src/lib/api/stream.ts`, `gui/src/app/chat/page.tsx`):**
  - Upgraded `/api/agents/ask/stream` from blocking `queue.Queue.get(timeout=0.1)` to non-blocking `get_nowait()` with `await asyncio.sleep(0.05)`, and added RFC 8895 SSE keep-alive comment pings (`: ping\n\n`) every 10 seconds of idle wait to prevent proxy, browser Fetch, and OS TCP socket drops during long LLM/subagent turns.
  - Added `activeStreamConvIdRef` in `ChatPage` to prevent `useEffect([activeConvId])` from wiping messages or prematurely setting `loading = false` when an active SSE stream initiates a new conversation thread.
  - Added background reconciliation in `onError` and `visibilitychange` that polls/syncs `getChatHistory(targetConvId)` directly against SQLite `chats.db`, automatically recovering and displaying agent responses even if network hiccups or browser tab backgrounding severed the streaming transport.
- **Zero-Lag Typing & Subtree Memoization Across Nexus GUI (`gui/src/app/chat/page.tsx`, `gui/src/components/chat/`, `gui/src/components/MarkdownMessage.tsx` & `gui/src/app/tools/page.tsx`):**
  - Isolated active keystroke buffers inside `ChatInputBar.tsx` (`localInput` synchronized via render-phase `inputSyncId` tracking) and `ResumeMarkdownEditor` (`gui/src/app/tools/page.tsx`), preventing per-character root page re-renders when typing prompts or editing resume markdown.
  - Wrapped `MarkdownMessage`, `ChatMessageThread`, `ChatMessageItem`, `ChatSidebar`, `ChatHeader`, `BlackboardDrawer`, `ThinkingPanel`, and `AgentGraphView` in `React.memo`, hoisted `REMARK_PLUGINS` (`[remarkGfm]`) and `MARKDOWN_COMPONENTS` to module scope, and memoized `preprocessObsidianMarkdown()` so historical chat messages never re-parse Markdown ASTs during typing.
  - Replaced post-render `useEffect` textarea height recalculations with inline event-handler resizing (`syncTextareaHeight`) to eliminate forced synchronous DOM reflows, debounced `localStorage` draft persistence (`persistDrafts`) by 300ms with `beforeunload`/unmount flush guarantees, added `useDeferredValue` to search inputs in `/audit`, `/tools`, and `PinNoteModal.tsx`, and scoped `.glass-card` CSS transitions in `gui/src/app/globals.css` to non-layout properties.
- **Per-Conversation Input Isolation (`gui/src/app/chat/page.tsx`):** Fixed chat input retaining the same global draft across conversation switches. Switching conversations now seamlessly saves the outgoing thread's draft, clears or restores the target thread's draft, preserves the "New Chat" draft independently, and clears drafts upon successful message submission or thread deletion.

### Removed
- Retired legacy pre-GUI interfaces and audio transcription scaffolding in a Zero-Vestige refactoring:
  - Deleted `src/nexus/interfaces/telegram.py`, `src/nexus/interfaces/voice.py`, `src/nexus/interfaces/cli.py`, `src/nexus/interfaces/__init__.py`, and removed `src/nexus/interfaces/` directory.
  - Deleted `src/nexus/core/audio.py` (Whisper STT helper) and `src/nexus/main.py` (legacy terminal mission control / Telegram runner).
  - Pruned orphaned package dependencies `python-telegram-bot` and `pyaudio` from `pyproject.toml` and `uv.lock` via `uv remove`.
  - Removed obsolete console script entrypoint `[project.scripts]` `nexus = "nexus.main:main"` from `pyproject.toml`.
  - Removed dead config settings `telegram_bot_token` and `allowed_user_ids` from `EngineSettings` in `src/nexus/core/config.py`.

## [3.2.0] - 2026-11-04

### Added
- **LLM Cost Estimation & Pricing Engine (`src/nexus/core/cost.py`):** Created a dedicated inference cost calculation engine with model-specific pricing tables for Google Gemini (`gemini-3.8-flash`, `gemini-4-argon`, Pro/Flash families) and OpenAI (`gpt-5.4-mini`, `gpt-5.6-terra`, `gpt-5.6-sol`, o-series). Supports prompt context caching discount accounting (e.g. 75% Gemini discount, 50% OpenAI discount).
- **Run Snapshot Cost Telemetry (`src/nexus/core/run_logger.py` & `src/nexus/agent/graph.py`):** Added real-time cost calculation to `_log_token_usage()`, emitted in live trace events and terminal logs. Updated `log_run()` to compute and persist root and per-subagent `cost_usd` and `cache_savings_usd` in `logs/runs/*.json` snapshots and `list_runs()` summaries.
- **Run Cost Audit & Backfill Utility (`scripts/audit_run_costs.py`):** Built a standalone CLI tool that scans all persisted execution snapshots in `logs/runs/`, reports total spend ($14.02 across 150 historical runs, 49M tokens, $16.50 saved via prompt caching with an 82.4% cache hit rate), shows breakdowns by model, and includes `--backfill` to retroactively stamp `cost_usd` into legacy snapshots.
- **Control Panel Cost Badges (`gui/`):** Displayed estimated dollar inference costs on assistant chat message bubbles (`ChatMessageItem.tsx`), quick-stats pills and run ledger summaries in the Agent Audit Log (`/audit`), and individual agent node execution cards in `AgentTraceVisualizer.tsx`.
- **Unit Test Coverage (`tests/test_cost_tracking.py`):** Added 5 automated tests validating rate lookups, prompt caching discounts, zero-token edge cases, and run snapshot cost persistence (86 passing engine tests).
- **Tools Suite Page (`gui/src/app/tools/page.tsx`):** Added a dedicated `/tools` page to the Nexus Control Panel featuring an extensible tool tab switcher and hosting the premier Resume & Document Compiler Engine.
- **Sidebar Destination (`gui/src/components/Sidebar.tsx`):** Added a primary navigation link for `🛠️ Tools` to the global sidebar menu.
- **Resume Engine Interactive Studio:** Replaced the terminal CLI workflow with a rich browser workspace including:
  - Portfolio document explorer with category tabs (`Resumes`, `Cover Letters`, `All`), multi-select checkboxes, and search filtering.
  - Page Budget & Metrics scorecard displaying total page count, last page fill %, geometry verdicts (`GOOD FIT`, `TIGHT FIT`, `ROOM`, `UNDERFILL`, `OVERFLOW`), and bullet points headroom / trim estimators.
  - Live in-browser markdown editor with direct saving to Vault.
  - Live inline PDF viewer iframe streamed directly from the engine backend.
  - Execution console log drawer and one-click PDF/DOCX downloads.
- **FastAPI Tools Router (`src/nexus/api/routers/tools.py`):** Added `/api/tools/resume/*` endpoints for portfolio scanning, document metadata inspection, markdown updating, headless Chromium & Word DOCX rendering, and binary asset streaming.
- **Resume Engine Backend Service (`src/nexus/shared_tools/resume_engine/service.py`):** Authoritative backend controller managing file discovery, directory traversal security checks, disk caching (`metrics_cache.json`), and compilation execution.
- **TypeScript API Client (`gui/src/lib/api/tools.ts`):** Client-side bindings and TypeScript data interfaces for all resume engine actions.
- **Automated Test Suite (`tests/test_resume_engine_api.py`):** 8 unit and integration tests covering document discovery, path traversal sandbox enforcement (HTTP 403 / ValueError), document reading, and binary PDF streaming.
- **Agentic Web Search Engine (`src/nexus/shared_tools/web_search.py` & `search_web` in `shared.py`):** Added `web_search.py` (`execute_web_search`, `format_search_results_as_markdown`, and `[CLI]` entrypoint `python -m nexus.shared_tools.web_search`) backed by `langchain-tavily` (`TavilySearch`) with search depth (`basic` / `advanced`), topic filtering (`general` / `news` / `finance`), domain whitelisting/blacklisting (`--domain`, `--exclude-domain`), and snippet length capping. Wrapped as `@tool def search_web` in `src/nexus/shared_tools/shared.py` (with a Context Hygiene Directive for subagent delegation) and bound into `CORE_TOOLS` in `src/nexus/agent/graph.py` so both `NexusAgent` and spawned subagents have native live web search.
- **Web Search Unit Test Suite (`tests/test_web_search.py`):** Added 5 unit tests covering empty-query and missing-key guards, parameter clamping, result normalization, Markdown formatting/truncation, and `CORE_TOOLS` graph binding.
- **Zero-Vestige Refactoring Standard (`.agents/rules/no_vestigial_code.md`):** Added a standing architectural rule requiring all coding and builder agents to identify and prune superseded code, dead CLI interfaces, obsolete debug scripts, and orphaned package dependencies whenever implementing replacements or modernizing existing tools.
- **Standing Directive in `AGENTS.md` & `Master Instructions.md`:** Integrated the Zero-Vestige Refactoring mandate into the core developer agent guidelines and living vault constitution to prevent code rot and zombie CLI scaffolds.
- **Anthropic Claude Model Options (`claude-opus-4-5` & `claude-sonnet-4-5`):** Added `langchain-anthropic` (`ChatAnthropic`) integration, `ANTHROPIC_API_KEY` / model tier settings in `src/nexus/core/config.py`, and side-by-side Chat UI model selector options (`Opus 4.5` for `strong` and `Sonnet 4.5` for `low`) in `src/nexus/core/constants.py`, `gui/src/components/chat/types.ts`, `gui/src/components/chat/ChatSidebar.tsx`, and `gui/src/components/chat/ChatInputBar.tsx`.
- **Provider-Matched Subagent Spawning (`spawn_subagent`):** Updated `call_model` and `spawn_subagent` in `src/nexus/agent/graph.py` so subagents spawned during an Anthropic Claude turn automatically route `low` tier execution to `claude-sonnet-4-5`.
- **Anthropic Cost & Prompt-Cache Pricing (`src/nexus/core/cost.py`):** Added Claude Opus 4.5 (`$5.00` input / `$0.50` cached / `$25.00` output per 1M tokens) and Claude Sonnet 4.5 (`$3.00` input / `$0.30` cached / `$15.00` output per 1M tokens) to the real-time pricing catalog and frontend fallback cost calculator.
- Added unit tests in `tests/test_cost_tracking.py` verifying context step-up thresholds and rates for models with large context windows.
- **Chat Title Renaming & Inline Editing in Next.js GUI (`gui/`):** Added inline conversation title editing in both `ChatSidebar.tsx` (via hover pencil button or double-click on thread items) and `ChatHeader.tsx` (via click-to-edit or hover pencil button) with keyboard shortcuts (Enter to save, Escape to cancel) and optimistic UI synchronization.
- **AI Auto-Titling Endpoint & UI Action:** Added `POST /api/agents/ask/conversations/{conversation_id}/auto-title` in `src/nexus/api/routers/agents.py` using fast low-tier models (`gemini-3.8-flash` / `claude-sonnet-4-5`) to summarize the opening turn into a concise 3–6 word topic title. Connected to a dedicated "✨" sparkle action button in `ChatHeader.tsx` and automated background auto-titling after the initial turn of newly started chats.
- **Validation & Safe Error Handling:** Enhanced `PATCH /api/agents/ask/conversations/{conversation_id}` in `src/nexus/api/routers/agents.py` to reject blank/whitespace-only titles with HTTP 400 Bad Request and verify thread existence in SQLite `chats.db` before writing.
- **Unit Test Coverage (`tests/test_chat_titles.py`):** Added 6 unit tests covering manual title updates, validation guards, 404 handling, mock LLM auto-titling, and fallback title generation on LLM timeout/quota exceptions.
- **Collapsible Nexus Message Bar (`gui/src/components/chat/ChatInputBar.tsx`):** Added collapsible state to the chat message composer bar. When minimized, collapses into a sleek, compact bottom rail displaying unsubmitted draft previews, the active model capability badge, and a click/keyboard expand toggle.
- **Global '/' Keyboard Shortcut (`gui/src/app/chat/page.tsx`):** Added a global keyboard shortcut listening for `/` when viewing the conversation thread to automatically expand the message bar and focus the multiline textarea.
- **Persistent Storage (`gui/src/components/chat/types.ts`):** Added `CHAT_INPUT_COLLAPSED_KEY` (`nexus_chat_input_collapsed`) to persist the message bar's collapsed/expanded preference across page refreshes and tab navigations.
- **Auto-Expansion on Starter Prompts (`gui/src/app/chat/page.tsx`):** Selecting any empty-state starter suggestion prompt automatically expands the message bar and pre-fills the textarea.
- Added automated security test suite in `tests/test_path_safety.py` verifying rejection of traversal payloads (`../.env`, `..\\.env`, `C:\\Windows\\win.ini`, `/etc/passwd`, `3. Operations/../../.env`), escaping symlinks, and successful resolution of valid notes and unique basenames.
- **HITL Provenance Tracking (`conversation_id`, `thread_id`, `agent_id`, `agent_role`):**
  - Extended `src/nexus/core/hitl_queue.py` (`transactions` schema, idempotent `ALTER TABLE` migration, `add_transaction`, and `get_recent_revisions`) with `conversation_id`, `thread_id`, `agent_id`, and `agent_role` columns plus `ContextVar`-backed execution context propagation (`set_hitl_execution_context`, `reset_hitl_execution_context`, `get_hitl_execution_context`).
  - Wired parent `Commander (<tier>)` (`agent_id="nexus"`) and spawned `Subagent #<n> (<tier>)` (`agent_id="subagent-<n>"`, `thread_id="<conv_id>:subagent-<n>"`) execution contexts in `src/nexus/agent/api.py` and `src/nexus/agent/graph.py`.
  - Exposed all 4 provenance fields in FastAPI `TransactionResponse` / `MockTransactionRequest` (`src/nexus/api/routers/hitl.py`) and TypeScript client types (`gui/src/lib/api/hitl.ts`), and backfilled 244 historical `hitl.db` transactions from run logs.
- Added `_invoke_tool_node_resilient()` in `src/nexus/agent/graph.py` to automatically fall back to sequential in-thread tool execution when `ToolNode`'s `ContextThreadPoolExecutor` raises `RuntimeError('cannot schedule new futures after shutdown')` during a `uvicorn --reload` worker restart.
- Added human-readable error translation in `run_nexus_agent_with_trace()` (`src/nexus/agent/api.py`) for `cannot schedule new futures after` and `BrokenThreadPool` exceptions.
- Added 2 unit tests in `tests/test_model_config_and_resilience.py` covering synchronous tool fallback and reload error translation.
- Persisted client storage keys `CHAT_SIDEBAR_COLLAPSED_KEY` and `CHAT_BOARD_OPEN_KEY` in `gui/src/components/chat/types.ts`.
- **Mandatory Engineering Section Instructions Directive (`AGENTS.md`):** Mandated that all Builder agents read and adhere to `Vault/6. Engineering/Section Instructions.md` ALWAYS when operating on the Nexus Engine, tools, or architecture.
- **Prompt-First Session Transcript Archival Directive (`Vault/6. Engineering/Section Instructions.md`):** Codified Section 2.D requiring AI agents to proactively offer to export and archive high-signal co-engineering session transcripts into `<Project>/Transcripts/` via `export_conversation.py` linked to `[[Build Log - <Project>]]` at the conclusion of non-trivial milestones. Explicitly prohibits silent or automated transcript exports without user confirmation.
- **Master Instructions Flush Integration (`Vault/Master Instructions.md`):** Integrated prompt-first transcript archival as step 3 of the Cognitive Boundary Flush protocol.
- **Resizable Conversation History Sidebar (`gui/src/components/chat/ChatSidebar.tsx`):** Added a draggable right-border resize handle with native pointer coordinate tracking (`PointerEvent`), min/max boundary clamping (`200px` to `640px`), double-click reset to default width (`256px`), and smooth transition prevention during active drag.
- **Persistent Sidebar Width Storage (`gui/src/components/chat/types.ts`):** Added `CHAT_SIDEBAR_WIDTH_KEY` (`nexus_chat_sidebar_width`) to save custom sidebar width in `localStorage`, maintaining user sizing across tab navigation and reloads.

### Changed
- **Headless Compiler Streamlining (`src/nexus/shared_tools/resume_engine/render.js`):** Refactored `render.js` into a dedicated headless Chromium PDF and page metrics compiler accepting CLI paths or batch flags (`--all`).
- **Native Python Execution (`src/nexus/shared_tools/resume_engine/service.py`):** Replaced the indirect Node-to-Python subprocess hop for Word DOCX generation with direct Python invocation via `render_docx.render_docx()`.
- **Updated `README.md`:** Added documentation for `src/nexus/api/routers/tools.py` and the Control Panel `/tools` page.
- **Vault Instruction Sets & Project Documentation (`Master Instructions.md`, `Section Instructions.md`, `README.md`, `Project - *.md`):** Updated `Master Instructions.md`, `2. Health/Section Instructions.md`, `3.1. Career Strategy & Revenue/Section Instructions.md`, and `6. Engineering/Section Instructions.md` to prompt `search_web` for live market/company verification, peer-reviewed clinical literature lookups, and frontier library/benchmark verification; reconciled doc-vs-disk drift across `Project - Nexus Agentic Engine.md`, `Project - Nexus GUI.md`, `Project - Nexus Demo.md`, and `README.md`.
- **Audit Run Ledger Conversation ID Badges (`gui/src/app/audit/page.tsx`):** Replaced the redundant static `"nexus"` agent badge on each run card in the left ledger with a compact conversation badge (`conv: <short_id>`) that displays the full UUID on hover. Falls back to agent name if unassociated with a thread.
- **Audit Search Filter (`gui/src/app/audit/page.tsx`):** Added `r.thread_id` to the search filter and updated placeholder to `Search runs by query, run ID, or conversation...` so users can filter all execution runs by conversation thread.
- **Default Disclosure of Live Agent Execution (`gui/`):** Configured real-time agent trace visualization (`ThinkingPanel`) in `ChatMessageThread.tsx` to mount collapsed by default (`defaultExpanded={false}`), preventing UI jumpiness while streaming responses.
- **Trace Panel Disclosure Polishing (`gui/`):** Updated default prop value in `AgentTraceVisualizer.tsx` to `defaultExpanded = false` and removed extraneous bottom border when the control bar is in collapsed state.
- **Blackboard Empty State Description (`gui/`):** Generalized placeholder copy in `BlackboardDrawer.tsx` from Astra-specific terminology to reference primary agents dispatching subagents.
- **HITL Review Queue UI Hierarchy (`gui/src/app/hitl/page.tsx`):**
  - Replaced the legacy `NEXUS_AGENT` label at the top of review queue cards with prominent `Ticket #{id}` badges matching conversational agent citations.
  - Promoted the target note title to the card's primary header (`font-semibold text-sm`) with tooltip truncation.
  - Displayed `agent_role`, `agent_id`, `conversation_id`, and `thread_id` pills in the card's secondary header and the main review inspector header.
  - Updated action notices and recently applied ledger entries to consistently cite `Ticket #{id}`.
- Updated `start.ps1` to scope Uvicorn file watching with `--reload-dir src/nexus`, exclude standalone CLI tools and SQLite files (`--reload-exclude export_conversation.py`, `--reload-exclude *.db*`, `--reload-exclude *.sqlite*`), and set `--timeout-graceful-shutdown 30`.
- Refactored `gui/src/app/chat/page.tsx` to restore and sync left conversation history menu (`ChatSidebar`) and right situational feed drawer (`BlackboardDrawer`) open/collapsed states via `localStorage`, ensuring user sidebar choices persist across Nexus page navigations.
- **Full-Width Conversation Titles with Floating Hover Actions (`gui/src/components/chat/ChatSidebar.tsx`):** Restructured conversation history items so titles take up 100% of available row width instead of reserving 70px of space for hidden action buttons. Action buttons (rename, AI auto-title, delete) now float seamlessly over the right edge on hover inside a backdrop-blurred pill container, avoiding text truncation.

### Fixed
- Calibrated real-time LLM cost estimation in `src/nexus/core/cost.py` for Gemini Pro and Argon models exceeding 128k context tokens, applying Google's 2x tier step-up pricing ($2.50/1M prompt, $0.625/1M cached, $10.00/1M output).
- Upgraded `scripts/audit_run_costs.py` to infer model names and capability tiers from agent reasoning strings on legacy snapshots and parse token usage from historical trace telemetry.
- Backfilled 83 historical run snapshots in `logs/runs/` with accurate token counts and tiered pricing.
- **SSE Stream Disconnect Recovery:** Hardened `gui/src/lib/api/stream.ts` to detect abrupt HTTP socket closures before a terminal `done` or `error` packet is emitted (e.g. backend reloads or network drops). Previously, an abrupt closure exited the read loop silently, leaving the chat UI permanently hung in a loading state. Now, it flushes trailing buffer data and invokes `callbacks.onError()` to cleanly stop the spinner and notify the user.

### Removed
- **Vestigial Terminal CLI Code (`src/nexus/shared_tools/resume_engine/render.js`):** Removed legacy interactive terminal prompt (`readline`, `promptFileSelection()`, `createInterface()`) now superseded by the `/tools` web studio.
- **Obsolete Debug Scripts & Unused Packages:** Deleted unused `inspect_docx.js` and removed unneeded `html-to-docx` and `adm-zip` dependencies from `src/nexus/shared_tools/resume_engine/package.json`.
- **Legacy Multi-Agent Run Logs (`logs/runs/`):** Pruned obsolete historical run snapshots from deprecated multi-agent routing (`librarian`, `career`).
- Removed orphaned 0-byte `src/nexus/agent/hitl.db` file.

### Security
- Fixed arbitrary-file-read and path traversal vulnerability in `src/nexus/shared_tools/vault_reader.py` (`resolve_vault_note_path`): rejected absolute paths and Windows drive letters upfront, resolved all candidate paths (direct and basename fallback) against `VAULT_PATH.resolve()` (or resolved domain root), and enforced `is_relative_to()` containment before reading or returning paths.
- Hardened path containment across all path-accepting functions in `src/nexus/shared_tools/vault_reader.py` (`get_directory_tree`, `search_within`, `get_recent_modifications`) via `_resolve_vault_dir` and pruned symlinks escaping the Vault.
- Hardened FastAPI Vault routes in `src/nexus/api/routers/vault.py` (`/structure`, `/note`, `/search`, `/list`, `/podcast/generate`, `/podcast/download`) by rejecting absolute/drive-letter inputs and resolving both sides against `VAULT_PATH.resolve()`.
- Hardened `get_run()` in `src/nexus/core/run_logger.py` and `GET /api/agents/runs/{run_id}` in `src/nexus/api/routers/agents.py`: rejected `run_id` inputs containing path separators or `..`.
- Hardened `read_file` and `create_file` LangChain tool wrappers in `src/nexus/shared_tools/shared.py` with strict Vault boundary enforcement.

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
