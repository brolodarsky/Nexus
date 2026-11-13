# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [3.4.0] - 2026-11-12

### Added
- Created `src/nexus/shared_tools/transcribe_media.py` implementing verbatim multimodal audio (.mp3, .wav, .m4a, .aac, .ogg, .flac) and video (.mp4, .mov, .mkv, .avi) transcription via the Google GenAI File API (`gemini-3.8-flash` with 65,536 output tokens).
- Added support for files up to 2GB directly without local audio extraction, PyTorch, or FFmpeg dependencies on Windows.
- Added asynchronous polling loop for server-side transcode/index states (`PROCESSING` -> `ACTIVE`) with 10-minute timeout and automatic cloud file deletion (`client.files.delete` in `finally:` block).
- Added structured Obsidian Vault note persistence to `Vault/0. Inbox/Transcripts/` with YAML frontmatter (tags, source file, duration, file size, transcription model, timestamp).
- Added LangChain `@tool transcribe_media` in `src/nexus/shared_tools/shared.py` and bound it to `CORE_TOOLS` in `src/nexus/agent/graph.py` returning the full verbatim transcript.
- Added standalone CLI entrypoint (`python -m nexus.shared_tools.transcribe_media`).
- Authored 12 unit tests in `tests/test_transcribe_media.py` covering path resolution, MIME detection, API mocking, poll states, error handling, LangChain `@tool` execution, and CLI flags (212/212 total pytest suite passing).
- **Active Floating Chat Overlay & Active Modal Extraction (`src/nexus/shared_tools/browser_extension/background.js`):**
  - Added dedicated, non-blocking active overlay extraction pass to the read-only browser bridge content extractor (`extractTabMarkdownReadOnly`), running after primary document extraction.
  - Detects expanded chat bubbles and floating dialogs (e.g. LinkedIn InMail/messaging chats via `aside.msg-overlay-container .msg-overlay-conversation-bubble--is-expanded`, `[role="dialog"]`, and active chat widgets) that were previously skipped as boilerplate outside the `<main>` container.
  - Extracts conversation participant names (automatically stripping ephemeral status indicators such as "Active now" or connection degree badges).
  - Extracts chronological message threads, resolving senders (with viewer/`--me` attribution), timestamps (relative/absolute), InMail subject lines, and message body text with inline links preserved.
  - Formats dialogue cleanly as blockquotes appended to the bottom of the page's standard Markdown body under `## Active Chat & Floating Overlays`.
  - Enforces non-blocking progressive enhancement: safely ignores minimized/collapsed bubbles and cookie consent banners (`/cookie|consent|gdpr|onetrust/i`), returning standard page markdown without error or extra headers when no overlays are active.
- **Automated Regression Test Suite (`tests/test_browser_bridge.py`, `tests/test_browser_extension_dom.js`):**
  - Added unit test coverage in `tests/test_browser_bridge.py` verifying formatted Markdown rendering of tabs with active chat overlays.
  - Built a Node.js DOM simulation test (`tests/test_browser_extension_dom.js`) evaluating `extractTabMarkdownReadOnly` against simulated DOM structures for expanded chat bubbles, minimized bubbles, cookie modals, and clean pages.
- Added event ID exposure (`(id: <event_id>)`) to `format_events_as_markdown` in `src/nexus/shared_tools/calendar_engine.py`, guaranteeing that `get_calendar_schedule` and CLI schedule outputs provide exact Google Calendar event IDs for downstream updates and deletions.
- Added `@tool delete_calendar_event` to `src/nexus/shared_tools/shared.py` and bound it to `CORE_TOOLS` in `src/nexus/agent/graph.py`.
- Added `--json` flag to `src/nexus/shared_tools/calendar_engine.py` CLI for deterministic JSON inspection of calendar events.
- Added 4 unit tests in `tests/test_model_config_and_resilience.py` verifying `ToolNode(handle_tool_errors=True)` error wrapping, event ID formatting in markdown digests, and defensive `HttpError` 404 interception across calendar tools (218/218 total pytest suite passing).
- **Chat Header Three-Dots Dropdown Menu (`ChatHeader.tsx`, `page.tsx`):** Folded the inline rename and AI auto-titling buttons into a unified three-dots (`•••`) menu button in the header bar. Added a destructive "Delete conversation" action with browser confirmation dialog and red styling. Added an accessible popover dropdown with outside-click and Escape key dismissal, plus an inline background "Titling..." badge to provide instant visual feedback during AI title generation.
- **Chat Image Uploads & Multimodal Vision Support:** Added native image attachment support to the Nexus Agent chat interface, enabling users to upload, paste from clipboard (`Ctrl+V`), or drag-and-drop images (PNG, JPEG, WEBP, GIF, BMP) for visual analysis alongside their prompts.
- **FastAPI Upload & Asset Serving Routes (`/api/agents/upload`, `/api/agents/uploads/{filename}`):** Added multipart file upload endpoint validating image integrity via Pillow, auto-resizing oversized assets (>1600px max edge) to control token consumption, and serving persisted images from `logs/uploads/` with strict path traversal guards.
- **Multimodal HumanMessage Construction (`src/nexus/agent/api.py`):** Extended `run_nexus_agent_with_trace` to resolve uploaded image paths into base64 data URLs (`data:image/...;base64,...`) and construct structured multimodal LangChain `HumanMessage` content blocks for native processing by Gemini, Claude, and OpenAI frontier models.
- **SQLite Schema Migration (`chats.db`):** Added `images TEXT` column to `messages` table in `chats_db.py`, persisting attached image URLs without database bloat and hydrating message history for thread rendering.
- **Staged Image Attachments Ribbon & User Bubble Grid:** Added thumbnail preview ribbon with removal buttons to `ChatInputBar.tsx` and rich clickable image cards to `ChatMessageItem.tsx` preserving 100% prompt text visibility.
- **Unit Test Coverage (`tests/test_image_upload_and_multimodal.py`):** Added 8 unit tests covering image upload, Pillow downscaling, MIME validation, path traversal prevention, database persistence, and base64 data URL conversion.
- **Chat Stop & Revert Action (`gui/src/` & `src/nexus/`):** Added a first-class Stop & Revert capability to Nexus Chat, allowing users to immediately halt in-flight agent execution and cleanly roll back all turn state with zero orphan mutations left behind.
- **FastAPI Stop & Revert Endpoint (`POST /api/agents/stop-and-revert`):** Implemented an atomic route coordinating thread-safe execution cancellation, pending HITL transaction purging, LangGraph checkpointer rollback, and chats.db message removal, returning the user's prompt text and image attachments for composer recovery.
- **Thread Cancellation Registry & Checks (`src/nexus/agent/graph.py`):** Added `_CANCEL_EVENTS` registry and `is_thread_cancelled(thread_id)`. Wrapped `call_model`, `traced_tool_node`, `route_after_agent`, and `spawn_subagent` with cancellation checks raising `InterruptedError` to halt LangGraph cycles immediately without corrupting SQLite handles.
- **Checkpointer Memory Rollback (`src/nexus/agent/graph.py`):** Authored `rollback_checkpoints_for_thread(thread_id, pre_turn_checkpoint_id)` which prunes newer checkpoints and channel writes from `memory.sqlite` back to the pre-turn baseline.
- **HITL Transaction Cancellation (`src/nexus/core/hitl_queue.py`):** Added `cancel_pending_transactions_for_conversation(conversation_id)` to transition all unapproved pending file mutations staged during the aborted turn to status `'cancelled'`.
- **Chat Message Purging & Prompt Extraction (`src/nexus/core/chats_db.py`):** Added `revert_last_turn(conversation_id)` to purge user and assistant messages from `chats.db` in reverse chronological order and extract prompt text and attached images.
- **Dynamic UI Buttons & Keyboard Shortcuts (`ChatInputBar.tsx`, `ChatMessageThread.tsx`, `ChatMessageItem.tsx`, `page.tsx`):**
  - Replaced disabled send button in `ChatInputBar` with a rose-styled `[ ⏹ Stop & Revert ]` button while streaming.
  - Added an inline `[ ⏹ Stop & Revert ]` button to the live thinking banner in `ChatMessageThread`.
  - Added `Escape` key shortcut during streaming to trigger instant stop & revert.
  - Added a `[ ↩ Revert turn ]` pill button to the latest assistant message bubble when idle for post-turn rollback.
  - Restored query text and images into the composer and focused the textarea upon stop or revert.
- **Automated Regression Suite (`tests/test_stop_and_revert.py`):** Added 9 unit and integration tests verifying mid-turn aborts, completed turn rollbacks, HITL cancellation, checkpointer DAG pruning, thread cancellation lifecycles, and FastAPI endpoint handling.
- **Universal Conversation Exporter Modernization (`src/nexus/shared_tools/export_conversation.py`):** Overhauled transcript exporter with Turn Coalescing to aggregate intermediate tool actions into collapsible `<details>` blocks, classify `type: GENERIC` tool stdout accurately, eliminate 12,000-line transcript bloat, and authored unit tests (`tests/test_export_conversation.py`).
- **Relational Telemetry Decoupling (`message_traces` table in `chats_db.py`):** Separated heavy diagnostic JSON trace arrays out of the primary `messages` table into a dedicated `message_traces (message_id INTEGER PRIMARY KEY, trace TEXT, FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE)` table.
- **Message Metadata Columns (`messages` table):** Added `model_tier TEXT`, `model_name TEXT`, `cost_usd REAL`, and `has_trace INTEGER DEFAULT 0` to `messages` for fast scalar indexing without needing to parse multi-megabyte trace JSON arrays.
- **On-Demand Lazy Telemetry Endpoint (`GET /api/agents/messages/{message_id}/trace`):** Mounted a dedicated FastAPI route in `src/nexus/api/routers/agents.py` fetching untruncated trace arrays on demand for a single message row.
- **Next.js Lazy ThinkingPanel Disclosure (`AgentTraceVisualizer.tsx`, `ChatMessageItem.tsx`, `types.ts`):** Enhanced `ThinkingPanel` to accept `messageId?: number`. When expanding a historical message with `hasTrace=true`, it displays an interactive loading spinner and fetches `getMessageTrace(messageId)` on demand. Active streaming turns retain instant zero-network inspection from client memory (`liveTraceRef.current`).
- **Comprehensive Unit Test Suite (`tests/test_chats_db_telemetry.py`):** Authored 8 unit tests validating schema isolation, lean history retrieval, cascade deletion, lazy endpoint responses, and bounded summary previews.
- Integrated PyMuPDF (`pymupdf`) into the Nexus Engine for layout-aware text extraction, tabular recognition, and high-fidelity page rasterization.
- Implemented `_read_pdf_content()` in `src/nexus/shared_tools/vault_reader.py` with native table detection (`page.find_tables().to_markdown()`), geometric reading block sorting (`sort=True`), scanned document detection, and page/line slicing.
- Extended the `@tool read_file` wrapper in `src/nexus/shared_tools/shared.py` with `start_page` and `end_page` slicing arguments for PDF documents.
- Enabled binary file handling across `move_file`, `delete_file` (`src/nexus/shared_tools/shared.py`), and the Two-Phase Commit HITL queue (`src/nexus/core/hitl_queue.py`), preventing `UnicodeDecodeError` and enabling atomic relocation and rollback of binary assets (PDFs, images).
- Authored 12 automated unit and integration tests in `tests/test_pdf_support.py` validating single-page/multi-page reading, page slicing, line slicing, vault table extraction, synthetic tables, scanned document flagging, tool execution, multi-page upload rasterization, thumbnail capping on >10 page documents, and binary move/delete/rollback lifecycles.
- **Dynamic AI Provider Rate-Limit (429 RESOURCE_EXHAUSTED) Backoff & Rollover:** Implemented `_extract_retry_delay`, `_cooperative_sleep`, and `_invoke_llm_with_resilience` in `src/nexus/agent/graph.py` across `call_model` (including deadline timeout fallback paths) and `spawn_subagent` ReAct loops to intercept 429 quota exhaustion errors, extract provider `retryDelay` metadata (or exponential backoff), stream structured SSE trace events to the Thinking Panel, and automatically retry upon sliding token-window rollover.
- **Demystified 429 User Diagnostic Guidance:** Added an actionable rate-limit diagnostic handler in `src/nexus/agent/api.py` explaining token-per-minute (TPM) sliding windows and sequential orchestration guidance.
- **Automated Regression Suite:** Authored 6 unit tests in `tests/test_model_config_and_resilience.py` verifying rate-limit error classification, delay extraction across Google RPC / natural text / headers, cooperative cancellation polling, backoff retry recovery, retry exhaustion, and diagnostic formatting (188/188 total pytest suite passing, 0 failures).
- **Read-Only Live Chrome Browser & Tab Group Bridge (`src/nexus/shared_tools/browser_bridge.py`, `src/nexus/shared_tools/browser_extension/`, `src/nexus/api/routers/browser.py`):**
  - Created an unpacked Manifest V3 Chrome Extension (`src/nexus/shared_tools/browser_extension/`) with offscreen service-worker keepalive that connects over loopback (`127.0.0.1`) to expose native Chrome Tab Groups (`chrome.tabGroups.query`), open tab metadata (`chrome.tabs.query`), and strictly read-only live DOM-to-Markdown + JSON-LD (`JobPosting` / `Product` / `Article`) extraction (`chrome.scripting.executeScript`).
  - Mounted `/api/browser` router in FastAPI (`ws://127.0.0.1:8000/api/browser/ws`, `GET /status`, `GET /tabs`, `POST /read`) and added automatic standalone ephemeral WebSocket fallback (`ws://127.0.0.1:8765/api/browser/ws`) in `browser_bridge.py` so CLI and IDE Resident agents work seamlessly even when `start.ps1` is offline.
  - Bound `list_browser_tabs` and `read_browser_tabs` `@tool` wrappers in `src/nexus/shared_tools/shared.py` and `CORE_TOOLS` in `src/nexus/agent/graph.py` with a Context Hygiene Directive for parallel `spawn_subagent` fan-out across multi-tab Chrome Tab Groups.
  - Added unit and integration test suite (`tests/test_browser_bridge.py`).
- Built the bidirectional Telegram Mobile Voice & Notification Bridge (`src/nexus/shared_tools/telegram_bridge.py`) supporting asynchronous long-polling queue draining (`getUpdates`), Pixel Gboard STT text, Telegram microphone `.ogg` Opus voice note transcription via Gemini Flash multimodal audio (with OpenAI Whisper fallback), camera photo ingestion, automatic first-user owner enrollment, `📱` conversation creation in `chats.db` with swipe-to-reply thread continuation, and structured HITL staging ping-backs.
- Added `@tool send_telegram_notification` in `src/nexus/shared_tools/shared.py` and bound it to `CORE_TOOLS` in `src/nexus/agent/graph.py` so `NexusAgent` can send proactive push notifications to the user's phone.
- Wired automatic background poller startup into FastAPI's `lifespan` in `src/nexus/api/main.py` (`/api/health` and `/api/telegram/status`), `start.ps1`, and Windows logon (`--install-autostart`) with cross-process `FileLock` coordination.
- Added 6 unit and integration tests in `tests/test_telegram_bridge.py`.
- **Universal Conversation Branching (`chats.db` DAG) & Subroutine Merge Engine (`src/nexus/core/chat_branching.py`, `src/nexus/api/routers/chat_branches.py`):** Implemented engine-level conversation branching (`POST /api/agents/ask/conversations/{id}/branch`) supporting both `'tangent'` mode (proportional `Parent Context Brief` + focal turn in an isolated context window) and `'fork'` mode (verbatim history clone up to `parent_message_id`), plus `POST /api/agents/ask/conversations/{id}/merge` to distill branch takeaways at proportional depth and merge them back into the parent conversation and LangGraph checkpointer (`memory.sqlite`).
- **Modular Next.js Branching UI (`gui/src/components/chat/`, `gui/src/lib/api/branches.ts`):** Added `MessageBranchTrigger.tsx` (per-message `🌿 Branch` popover and inline child branch pills), `BranchLineageBar.tsx` (parent breadcrumb, optional focus guidance note, and `Distill & Merge to Parent ↩` action), `useChatBranching.ts` hook, and collapsible nested branch trees in `ChatSidebar.tsx`.
- **Automated Regression Tests (`tests/test_chat_branching.py`):** Added 6 unit and integration tests covering full history forks, tangent context briefs, Turn-1 tangent optimization, subroutine distillation & merge, parent deletion promotion, and error guards.
- **Auto-Collapsing YAML Frontmatter Component (`gui/src/components/NoteFrontmatter.tsx`):**
  - Built a zero-dependency Obsidian frontmatter parser supporting strings, numbers, booleans, inline flow arrays (`[a, b]`), indented block lists (`- item`), and unquoted scalar fields.
  - Implemented an auto-collapsed metadata panel with a sleek, compact summary bar (showing note type, tags preview, last updated timestamp, and field counts).
  - Built an expanded inspector featuring tabs for a structured property definition table and a raw YAML syntax viewer with a one-click clipboard copy action.

### Changed
- **Main Walk Boilerplate Isolation (`src/nexus/shared_tools/browser_extension/background.js`):**
  - Updated `isElementHidden(el, skipBoilerplate)` to skip floating chat containers (`.msg-overlay-container`, `.chat-window`, `.chat-overlay`) and active dialogs (`[role="dialog"]`, `[role="alertdialog"]`, `<dialog>`) during the primary document body walk when `skipBoilerplate=true`, preventing unformatted drawer buttons and modal noise from polluting the primary document prose.
- **Sidepanel Hover Toolbar & Dead Code Removal (`ChatSidebar.tsx`, `page.tsx`):** Excised the hover action toolbar containing the sidepanel's edit (pencil), auto-title (sparkle), and delete (cross) buttons. In accordance with zero-vestige engineering standards, completely pruned obsolete inline editing states (`editingId`, `editTitle`, `editInputRef`, `handleStartEdit`, `handleSaveEdit`, `handleCancelEdit`) and unused props (`onDeleteChat`, `onAutoGenerateTitle`, `onUpdateTitle`) from `ChatSidebar`. Unlocked 100% full horizontal row width for conversation titles without hover popovers obscuring text or causing accidental taps on touch screens.
- **Persistent Server-Side Trace Buffer & SSE Stream Re-Attachment (`src/nexus/api/routers/agents.py`):**
- Expanded `ActiveRun` with model metadata (`model_tier`, `model_name`, `model_label`), `user_message_id`, thread-safe buffered `trace_events` replay backlog, multi-subscriber fan-out queues (`publish_trace`, `publish_terminal`, `subscribe`, `unsubscribe`), and status snapshots while retaining `event_queue` compatibility.
- Added `GET /api/agents/ask/active`, `GET /api/agents/ask/active/{conversation_id}`, and `GET /api/agents/ask/stream/{conversation_id}` using a shared `_stream_active_run` SSE generator that atomically replays prior execution steps and continues streaming live events (or emits `sync_required` if the turn finished right before attachment).
- Guarded `POST /api/agents/ask/stream` with an `HTTP 409` duplicate-run check per conversation and unified active-run cancellation across `POST /api/agents/stop-and-revert` and `DELETE /api/agents/ask/conversations/{conversation_id}` (`_cancel_active_run_record`).
- Added `_sanitize_for_json` and `_safe_json_dumps` across SSE stream emission (`_stream_active_run` and `reattach_brain_stream` `sync_required`) so non-finite floats (`NaN`, `Infinity`) and non-JSON objects serialize safely instead of breaking browser `JSON.parse()` or aborting streams before `"done"`.
- **Chat GUI Active-Run Discovery, Re-Attachment, Live Indicators & Auto-Completion Recovery (`gui/`):**
- Extended `gui/src/lib/api/stream.ts` (`attachBrainStream`, shared `consumeBrainSseStream`, `"sync_required"` event, `onActivity` callback, `/\r?\n\r?\n/` SSE block framing, and a 35s `SSE_HEARTBEAT_TIMEOUT_MS` inactivity watchdog so silent/half-open sockets trigger recovery instead of hanging indefinitely) and `gui/src/lib/api/agents.ts` (`getActiveRuns`, `getActiveRunStatus`, `ActiveRunStatus`).
- Updated `gui/src/app/chat/page.tsx` to detect active background runs when opening/switching chats, returning to `/chat`, or regaining focus/visibility/network (`visibilitychange`, `window.focus`, `window.online`), restore the live thinking banner + `Stop & Revert` + replayed steps seamlessly, auto-reattach on transient disconnects with 12-attempt bounded exponential backoff and `getActiveRunStatus` probe retries, reconcile finished turns via a 3s loading/active-run watchdog (`historyMatchesMessages`, `minReplyHistoryLength`) even when a `done` frame is missed, and show sidebar active badges.
- Updated `gui/src/components/chat/ChatMessageThread.tsx` (conversation-scoped `key` on live `ThinkingPanel`), `gui/src/components/chat/ChatSidebar.tsx` (`activeRunConvIds` pulsing cyan dots), and `gui/src/components/AgentTraceVisualizer.tsx` (React 19 state derivation cleanup).
- **Automated Verification (`tests/test_chat_stream_reattach.py`):**
- Added tests covering mid-turn trace backlog replay + live continuation, inactive-thread `sync_required`, `409 Conflict` duplicate run rejection, active-run cancellation on conversation deletion, and `_safe_json_dumps` sanitization of non-finite floats and `Path` objects.
**Cost Optimization: Subagent Blackboard Removal, `gemini-3.8-flash` Low-Tier Restoration, Model Dropdown Menu, Anthropic Prompt Caching & User-Message Temporal Injection:**
- **Zero-Vestige Subagent Blackboard Removal (`src/nexus/`, `gui/`, `tests/`):** Removed `blackboard.py`, `/api/board` (`board.py`), `post_to_board`/`read_board` tools, automatic `post_bulletin` in `spawn_subagent`, `BlackboardDrawer.tsx`, `board.ts`, and `test_blackboard.py` to eliminate redundant output-token generation and dead UI/DB surface.
- **Restore `gemini-3.8-flash` as `"low"` Default & Switch UI Model Selector to Dropdown (`config.py`, `constants.py`, `cost.py`, `ChatInputBar.tsx`):** Reverted `"low"` and `"medium"` defaults and tier fallback pricing to `gemini-3.8-flash` while keeping `gemini-4-hydrogen` selectable as an explicit catalog option, and replaced the segmented model pills in `ChatInputBar.tsx` with an accessible dropdown menu.
- **Anthropic Prompt Caching & Subagent Prefix Stability (`constants.py`, `graph.py`):** Enabled top-level `model_kwargs={"cache_control": {"type": "ephemeral"}}` on `ChatAnthropic`, added block-level `cache_control` on Anthropic `SystemMessage` payloads (`_build_system_message`), and removed per-subagent `(Subagent #{serial})` variation from `spawn_subagent` system prompts so subagents hit the Turn-1 prefix cache.
- **User-Message Temporal Injection (`Master Instructions.md`, `engine_constitution.py`, `api.py`):** Removed `{current_time}` from `SystemMessage` and attached `[Current Time: YYYY-MM-DD HH:MM]` idempotently to each newly sent `HumanMessage` (`prepend_current_time_to_prompt`) so historical threads stay cache-stable across hour boundaries while keeping `chats.db` UI bubbles clean.
- **Ultra-Lean Chat History Retrieval (`get_chat_history`):** Updated `get_chat_history()` to default to `include_trace=False`, selecting only lightweight message metadata and returning `trace: []`. Reduced standard chat history HTTP payloads from multi-megabytes down to ~13 KB for a 50-turn conversation (a 99.5% reduction).
- **Trace Event String Duplication Elimination (`AgentTracer` in `trace.py`):** Formatted bounded summary previews in `tool_call` and `tool_result` string messages and terminal prints, while preserving 100% untruncated arguments and results in `event.data` for the DAG visualizer.
- **Automatic Migration & SQLite Vacuum:** `init_db()` automatically migrates legacy `messages.trace` blobs into `message_traces`, populates scalar metadata columns, sets `messages.trace = NULL`, and executes SQLite `VACUUM;` to reclaim disk space.
- Upgraded `POST /api/agents/upload` in `src/nexus/api/routers/agents.py` to persist the full raw PDF file to `logs/uploads/` and cap visual thumbnail rendering to the first 10 pages, eliminating artificial upload rejections on multi-page manuals and reference documents.
- Updated Next.js chat composer (`gui/src/components/chat/ChatInputBar.tsx`) and API client (`gui/src/lib/api/agents.ts`) to accept PDF document uploads, drag-and-drop, and staging of all rendered page thumbnails into the multimodal vision stream.
- Updated `README.md`, `Build Log - Nexus Agentic Engine.md`, and engineering ADRs in `Vault/6. Engineering/Log.md`.
- **SQLite `chats.db` Lineage Schema (`src/nexus/core/chats_db.py`):** Added idempotent schema migrations (`parent_conversation_id`, `parent_message_id`, `branch_mode`, `merged_at`) to `conversations`, exposed `id` (`messages.id`) in `get_chat_history()`, returned inserted row IDs from `log_message()` (emitted in SSE `done` packets), and promoted child branches to root level on parent deletion.
- **Session Transcript Exporter (`src/nexus/shared_tools/export_conversation.py`):** Updated `load_conversation_source()` to prefer `transcript_full.jsonl` over `transcript.jsonl` when resolving brain directories and conversation UUIDs so long assistant turns are exported in full without mid-response `<truncated ... bytes>` placeholders.
- Updated `AGENTS.md` and `.agents/rules/builder_work_tracking.md` to reference `Vault/Gameplan.md` (`# Today` → `## Tasks`) instead of the retired `Vault/1. Core/1.1. Philosophy & Personal North Star/Plan.md` (`## Career & Technical`) path.
- Isolated `chats_db.DB_PATH`, `blackboard.BOARD_DB_PATH`, and `hitl_queue.DB_PATH` to `tmp_path` across conversation and SQLite unit tests so test runs never pollute live databases.
- Upgraded the Anthropic Claude strong-tier model default from Claude Opus 4.5 (`claude-opus-4-5`) to Claude Opus 5.5 (`claude-opus-5-5`) in `src/nexus/core/config.py` and `src/nexus/core/constants.py`.
- Extended `_normalize_anthropic_model_name()` to normalize `claude-opus-5.5`, `opus-5.5`, `opus-5-5`, and `opus 5.5` to canonical `claude-opus-5-5` while preserving `claude-opus-4-5` backwards-compatibility for legacy invocations.
- Handled Anthropic frontier sampling deprecations in `src/nexus/core/constants.py` by omitting `temperature` for models like `claude-opus-5-5` that deprecate custom sampling parameters, preventing HTTP 400 (`temperature is deprecated for this model`). Added automatic sampling parameter self-healing to `_invoke_llm_with_resilience` in `src/nexus/agent/graph.py`.
- Updated `get_available_models()` so the side-by-side Anthropic Strong card reflects `Opus 5.5 (claude-opus-5-5)`.
- Added `claude-opus-5-5` and `claude-opus-5.5` to `MODEL_PRICING` in `src/nexus/core/cost.py` with $4.00 input, $0.20 cached (95% prompt cache discount), and $20.00 output rates per 1M tokens. Preserved legacy `claude-opus-4-5` pricing in the catalog for retrospective auditing and re-routed fuzzy "opus" matches to `claude-opus-5-5`.
- Updated `FALLBACK_MODEL_OPTIONS` in `gui/src/components/chat/types.ts` and `gui/src/lib/api/agents.ts` to present Opus 5.5 (`claude-opus-5-5`). Enhanced `extractTurnCost()` to differentiate between Opus 5.5 ($4/$0.20/$20) and legacy Opus 4.5 ($5/$0.50/$25) when estimating token costs.
- Updated reasoning model backfill targets in `scripts/audit_run_costs.py` and comments in `src/nexus/agent/graph.py` to reference `claude-opus-5-5`.
- Updated test suites in `tests/test_cost_tracking.py` and `tests/test_model_config_and_resilience.py` to validate `claude-opus-5-5` pricing, catalog exposure, and ChatAnthropic client instantiation (213/213 full suite passing).
- **Gemini Low/Medium Tier Upgrade (`src/nexus/core/config.py`, `src/nexus/core/constants.py`):** Replaced `gemini-3.8-flash` with `gemini-4-hydrogen` across `gemini_model_low` and `gemini_model_medium` defaults in `EngineSettings`. Updated `resolve_model_config()` to recognize `"hydrogen"` tokens under the `"gemini"` provider and `"low"` fast-family classification, and updated `get_available_models()` so the Chat UI `Fast` preset presents `Fast (gemini-4-hydrogen)` with a dynamic `Hydrogen` description.
- **Inference Pricing & Context Window Guard (`src/nexus/core/cost.py`):** Added `gemini-4-hydrogen` to `MODEL_PRICING` ($1.50/1M input, $0.075/1M cached [95% implicit caching discount], $7.50/1M output including reasoning tokens), updated `TIER_FALLBACK_PRICING["low"]` to `gemini-4-hydrogen`, prioritized `"hydrogen"` in fuzzy family heuristics, and excluded `"hydrogen"` from the >128k 2x step-up multiplier so pricing remains flat across its 1M context window. Retained legacy `gemini-3.8-flash` pricing ($0.10/$0.025/$0.40) for accurate retrospective auditing of historical runs.
- **Shared Tools, Backend & Audit Sync (`src/nexus/shared_tools/transcribe_media.py`, `src/nexus/shared_tools/telegram_bridge.py`, `src/nexus/agent/graph.py`, `src/nexus/api/routers/agents.py`, `src/nexus/core/blackboard.py`, `scripts/audit_run_costs.py`):** Updated `transcribe_media.py` fallback model to `"gemini-4-hydrogen"` (65,536 max output tokens), updated `scripts/audit_run_costs.py` fallback inference to recognize `gemini-4-hydrogen` while preserving legacy `gemini-3.8-flash` audits, and updated engine/tool comments and docstrings.
- **Next.js Chat UI (`gui/src/components/chat/types.ts`, `gui/src/lib/api/agents.ts`):** Updated `FALLBACK_MODELS` to `gemini-4-hydrogen` and updated `extractTurnCost()` to calculate Gemini 4 Hydrogen rates ($1.50/$0.075/$7.50) while preserving legacy Flash trace rates ($0.10/$0.025/$0.40).
- **Documentation & Tests (`README.md`, `tests/`):** Updated `README.md` tool descriptions and expanded regression coverage in `tests/test_cost_tracking.py`, `tests/test_model_config_and_resilience.py`, `tests/test_transcribe_media.py`, `tests/test_telegram_bridge.py`, and `tests/test_chat_titles.py` (218 passed, 1 skipped; `npm run build` passed).
- **Rich Markdown Reading Surface in Vault Explorer (`gui/src/app/vault/page.tsx`):**
  - Replaced the plaintext `<pre>` block with a glassmorphic reader surface powered by `MarkdownMessage`.
  - Integrated auto-collapsed `NoteFrontmatter` at the top of notes containing YAML fences, resetting to collapsed on every note selection.
  - Added an interactive action toolbar with folder breadcrumbs, reading time and word count metrics, a raw/preview mode toggle (`Preview` vs `Raw`), one-click note markdown copy, and in-place Obsidian `[[Wiki-Link]]` switching.
- **Obsidian Callouts & Deep-Linking (`gui/src/components/MarkdownMessage.tsx`):**
  - Added support for Obsidian callout syntax (`> [!NOTE]`, `> [!TIP]`, `> [!WARNING]`, `> [!IMPORTANT]`, `> [!CAUTION]`, etc.) with themed accent borders, translucent backgrounds, and custom icons.
  - Connected `WikiLinkContext` so clicking note pills switches the active note in-place when inside the Vault Explorer or navigates via Next.js client router deep-linking from chat or other workspaces.
  - Refined task list item alignment so checkboxes (`- [ ]`, `- [x]`) do not duplicate bullet points.
- **Cleaned Home Page Pinned Notes Reader & Grid Cards (`gui/src/components/home/`):**
  - Updated `PinnedNotesReader.tsx` and `PinnedNoteCard.tsx` to strip tool header wrappers and auto-collapse YAML frontmatter, revealing note bodies cleanly.

### Fixed
- Configured LangGraph `ToolNode` instances (`tool_node` for parent agent and `sub_tool_node` for dynamic subagents in `src/nexus/agent/graph.py`) with `handle_tool_errors=True`. Unhandled tool exceptions (such as Google API `HttpError` 404/500, network disconnects, or unexpected tool faults) now convert into structured `ToolMessage(content=..., status="error")` instead of bubbling uncaught through `ToolNode.invoke()` and abruptly terminating the user's turn.
- Patched `update_calendar_event` and `create_calendar_event` in `src/nexus/shared_tools/shared.py` and `calendar_engine.py` with defensive `HttpError` interception so nonexistent event IDs or API errors emit clear, actionable feedback rather than fatal trace crashes.
- **Unbounded SQLite Chat History Retrieval (`chats_db.py`, `agents.py`):** Fixed long-thread message truncation where `get_chat_history()` defaulted to `limit=50`, causing conversation threads exceeding 50 turns to omit newer messages and visual image attachments when fetching history or re-syncing on tab focus.
- **FastAPI Endpoint History Limit Parameter (`/api/agents/ask/history`):** Added optional `limit: Optional[int] = None` query parameter defaulting to unbounded chronological retrieval (`ORDER BY id ASC`), ensuring full fidelity for long-running chat sessions while preserving limit functionality for specialized callers (e.g. title generation).
- **Regression Unit Tests:** Added unit test coverage verifying that conversation threads with >50 turns and image attachments are retrieved in full without message truncation.
- **Chat & External Note Links Opened in New Browser Tabs (`gui/src/components/MarkdownMessage.tsx`, `gui/src/components/chat/ChatMessageItem.tsx`, `gui/src/components/chat/BlackboardDrawer.tsx`, `gui/src/components/AgentTraceVisualizer.tsx`):** Resolved an issue where clicking Obsidian wiki-links (`[[Note]]`, `[[Note|Alias]]`) or backticked note titles (`` `Note.md` ``) rendered within chat message bubbles, subagent blackboard bulletins, or thinking trace panels performed Next.js in-app client-side navigation within the same window, abruptly replacing the active `/chat` workspace and interrupting ongoing SSE streams, conversation focus, or prompt drafts.
  - Enhanced `MarkdownMessage` and `VaultNotePill` to accept an `openInNewTab` policy via context and props (defaulting to `true` whenever an in-place `onWikiLinkClick` handler is not supplied).
  - Wired `target="_blank"` and `rel="noopener noreferrer"` attributes onto the underlying Next.js `<Link>` component for safe, isolated multi-tab browsing.
  - Added an external link glyph indicator (`↗`) with hover transition and clear tooltip (`Vault Note: <Target> (Click to open in new tab)`) to visually signal multi-tab navigation to the user.
  - Extended `ChatMessageItem` user message prompt rendering to use `MarkdownMessage` with preserved whitespace (`whitespace-pre-wrap`), enabling users to click note links referenced in their own prompt history into new tabs.
  - Intercepted standard Markdown links targeting `.md` files or `/vault?note=...` in `MARKDOWN_COMPONENTS.a`, automatically converting relative paths (e.g. `[Tasks](Vault/Tasks.md)` or `[Log](Log.md)`) into `VaultNotePill` badges that open into new tabs instead of failing with `/chat/*.md` 404 errors.
  - Sanitized target path resolution by cleanly stripping heading anchors (`#Heading`) from query parameters (`/vault?note=<baseTarget>`) so anchor links navigate directly to the target markdown note file.
- **Deep-Linked URL Search Parameter Sanitization (`gui/src/app/vault/page.tsx`):** Updated the initial URL query param listener on mount in the Vault explorer to strip heading anchors and automatically normalize `.md` extensions on linked target notes, preventing file resolution errors when opening notes with section anchors from external tabs.
- **Chat Feed Sticky Auto-Scroll & Viewport Hijack Prevention (`gui/src/components/chat/ChatMessageThread.tsx`, `gui/src/app/chat/page.tsx`):** Resolved an issue where streaming telemetry events from `AgentTracer` repeatedly pulled the chat view to the bottom while an agent was working, preventing users from scrolling up to read earlier messages, notes, or execution steps. Introduced scroll-stickiness invariant tracking (`SCROLL_BOTTOM_THRESHOLD = 80px`) via `isAtBottomRef` and `onScroll` listener: incoming messages and live trace events now only scroll to bottom if the user was already pinned to the bottom. If the user scrolls up, auto-scroll is immediately disengaged, preserving their scroll position uninterrupted.
- **Scroll-to-Bottom Floating Affordance (`gui/src/components/chat/ChatMessageThread.tsx`):** Added a floating pill button that appears whenever the viewport is detached from the bottom. Features a pulsating cyan badge and `"New activity"` indicator when live telemetry arrives while scrolled up, and smoothly scrolls to bottom upon click while re-engaging sticky auto-scrolling.
- **ThinkingPanel Compact Scroll Guard (`gui/src/components/AgentTraceVisualizer.tsx`):** Added user scroll detection to `ThinkingPanel` in compact scroll mode (`fullHeight: false`) so inspecting earlier tool calls or thinking steps while an agent is live does not jump to the bottom on subsequent events.
- **Thread-Scoped Subagent Swarms & Active Turn Provider Isolation (`src/nexus/agent/graph.py`, `src/nexus/agent/api.py`):** Eliminated process-level race conditions where concurrent conversations executing subagents clobbered each other's state. Replaced global `_subagent_serial_counter` and `_active_turn_provider` with thread-safe registries (`_thread_subagent_counters`, `_thread_active_providers`), scoped `reset_subagent_counter(active_thread)` strictly to the active turn's conversation, and ensured spawned subagents resolve their model provider family from their parent conversation context.
- **SQLite Concurrency & WAL Hardening (`src/nexus/core/chats_db.py`, `src/nexus/core/blackboard.py`, `src/nexus/core/hitl_queue.py`, `src/nexus/agent/graph.py`):** Enabled Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and 30-second engine busy timeouts (`PRAGMA busy_timeout = 30000;`, `timeout=30.0`) across all SQLite databases (`memory.sqlite`, `chats.db`, `blackboard.db`, `hitl.db`). Prevents `sqlite3.OperationalError: database is locked` during concurrent chat logging, subagent bulletin posting, or checkpoint updates.
- **Automated Regression Suite (`tests/test_sqlite_concurrency.py`, `tests/test_agent_tracking_and_graph.py`):** Authored 6 unit and multi-threaded integration tests verifying WAL mode, busy timeouts, concurrent chat logging (10 parallel workers), concurrent blackboard bulletin posting (8 parallel workers), and thread-isolated subagent counter allocation (164 total pytest tests passing, 0 failures).
- Fixed uncatchable native C++ access violation (SEH `0xc0000005` segfault) in PyMuPDF (`mupdfcpp64.dll`) triggered during `page.find_tables()` table extraction. The default layout analyzer (`use_layout=True` -> `page.get_layout()`) dereferenced null pointers on vector-drawn PDFs (such as financial and student loan payment receipts), abruptly killing the Uvicorn worker process and leaving port 8000 orphaned in `CloseWait`.
- Configured `find_tables(use_layout=False)` in `src/nexus/shared_tools/vault_reader.py` (`_read_pdf_content`), restricting detection to memory-safe, deterministic line- and edge-based vector algorithms.
- Updated `tests/test_pdf_support.py` with `test_read_pdf_layout_segfault_resilience` validating receipt PDFs with vector drawings ingest cleanly without process termination.
- Resolved ambiguous path resolution in `tests/test_pdf_support.py` across duplicate vault files.
- **Mobile HITL Diff Viewer Container Collapse (`gui/src/app/hitl/page.tsx`):** Resolved an issue where Monaco `DiffEditor` collapsed to a 0px / 18px tiny sliver on mobile screens (< 768px). Because outer flex containers used unconstrained `min-h-[...]` rather than definite CSS heights on mobile, Monaco's internal percentage height wrapper resolved to 0px. Configured explicit responsive container and editor heights (`62vh` / `min-h-[460px]` for diff review, `60vh` / `min-h-[420px]` for 3-way conflict view), enabled `automaticLayout: true` in Monaco options, tuned mobile typography (`fontSize: 12`, `lineNumbersMinChars: 3`, `padding: 8px`), added viewport-keyed remounting, and auto-collapsed the queue sidebar and reasoning cards on mobile viewports to grant full screen real estate to the active unified diff.
- **KaTeX Mathematical Typesetting Across GUI (`gui/src/components/MarkdownMessage.tsx`, `gui/src/app/layout.tsx`, `gui/src/app/globals.css`):** Fixed a Markdown rendering flaw where complex LaTeX equations (e.g. `$$\text{Spread} = 0.4 \times \text{edge\_weight} \times (0.5^{\text{hop\_distance}})$$`) rendered as raw broken text with stray `$` delimiters due to an ad-hoc regex symbol preprocessor that lacked math AST parsing. Installed `remark-math`, `rehype-katex`, and `katex`, added `remarkMath` and `rehypeKatex` (configured with `strict: false, throwOnError: false`) to `MarkdownMessage.tsx`, imported `katex/dist/katex.min.css` in `layout.tsx`, and added horizontal scroll overflow styling for `.katex-display` blocks in `globals.css`.
- **Prose Currency Delimiter Protection (`gui/src/components/MarkdownMessage.tsx`):** Added deterministic regex escaping for conversational currency figures (`$41.20`, `$150k`, `$50–$100`) so `remark-math` does not mistakenly pair prose dollar amounts into broken inline math spans, while preserving single-number math literals (e.g. `$0.4$`).
- **LaTeX snake_case Variable Protection (`gui/src/components/MarkdownMessage.tsx`):** Added automatic underscore escaping inside `\text{...}` math tags (e.g. `\text{edge_weight}`) so programmatic variable names parse without triggering KaTeX `Expected 'EOF', got '_'` syntax errors.
- **Zero-Vestige Refactoring (`gui/src/components/MarkdownMessage.tsx`):** Excised legacy symbol substitution code (`MATH_INNER_LATEX_PATTERN`, `replaceLatexInMath`) that previously attempted to unwrap math into flat Unicode characters, preserving `BARE_PROSE_LATEX_PATTERN` exclusively for un-delimited prose arrow shortcuts (`\rightarrow` $\to$ `→`).
- **LLM Markdown Code Fence Sanitization & Inversion Prevention (`gui/src/components/MarkdownMessage.tsx`):** Added `sanitizeMarkdownFences` and `splitFencedCodeBlocks` to deterministically heal malformed LLM markdown outputs. When LLMs generate prompts, templates, or documentation containing nested code snippets using standard triple backticks (` ``` `), CommonMark (§4.5) prematurely terminates the outer block on the inner closing fence, spilling subsequent prompt steps into regular prose and inverting subsequent fences into unintended code blocks. `sanitizeMarkdownFences` tracks fence depth, auto-promotes enclosing outer fences to 4+ backticks (` ```` `) so inner fences are safely treated as literal text, and auto-closes unclosed streaming blocks. `splitFencedCodeBlocks` cleanly preserves arbitrary length fences (3, 4, 5+ backticks/tildes) so Obsidian wiki-links, note pills, and LaTeX math formatting apply only to prose segments without mutating or slicing code blocks.
- Configured dynamic `allowedDevOrigins` via `os.networkInterfaces()` and `devIndicators: false` in `gui/next.config.ts` to permit `/_next/*` dev assets from Tailscale/LAN clients and hide the floating bottom-left Next.js dev tools badge that overlapped the mobile bottom navigation bar.
- Integrated official Nexus logo assets into `gui/src/components/Sidebar.tsx` and generated standard 192px/512px PWA and maskable icons in `gui/public/icons/`.
- Added pass-through Service Worker (`gui/public/sw.js`) and `<ServiceWorkerRegister />` to fulfill Android Chrome WebAPK criteria.
- Explicitly configured `scope: "/"`, `start_url: "/"`, and `display_override: ["standalone", "minimal-ui"]` in `gui/src/app/manifest.ts` to prevent Chrome from dropping out of standalone mode when navigating across pages.
- **Control Panel Startup Wildcard Expansion & Healthcheck Race (`start.ps1`):** Fixed an issue where `Start-Process` joined `-ArgumentList` items without quotes, causing Windows C runtime (MSVCRT `setargv`) to expand unquoted wildcards (`*.db*`, `*.sqlite*`) into filenames present in the project directory (e.g. `chats.db`, `hitl.db`). This passed extra unexpected positional arguments to Uvicorn/Click, silently crashing the FastAPI backend immediately on launch. Escaped wildcards as literal double quotes (`\"*.db*\"`, `\"*.sqlite*\"`), redirected Uvicorn stdout and stderr to `logs/uvicorn.log` and `logs/uvicorn_err.log`, added a 15-second polling healthcheck loop with immediate crash detection (`$backend.HasExited`), and added pre-flight stale listener cleanup on port 8000.
- **Chat Page Initial Load Rejection Guard (`gui/src/app/chat/page.tsx`):** Added `.catch()` handler to `getConversations()` promise on page mount to prevent Next.js `unhandledRejection` browser errors when the backend is restarting or unreachable.
- Fixed Telegram voice note download SSL handshake timeout (`_ssl.c:993`) by implementing a thread-safe singleton connection pool (`get_telegram_http_client` / `close_telegram_http_client`) with HTTP keepalive, connection limits, and granular timeouts in `src/nexus/shared_tools/telegram_bridge.py`.
- Reused established keepalive sockets across `download_telegram_file`, `send_chat_action`, `send_telegram_message`, and `verify_telegram_bot`, eliminating repeated TLS 1.3 renegotiation on Windows and dropping subsequent request latency from ~900ms to ~90ms.
- Added exponential backoff retry logic (up to 3 attempts with 0.5s base delay) in `download_telegram_file` for transient network errors, timeouts, and SSL handshake glitches (`TimeoutException`, `NetworkError`, `SSLError`, `ConnectionError`).
- Added retry resilience to `send_telegram_message` for outbound message delivery during transient connection blips.
- Differentiated voice note download errors from transcription errors in logs and Telegram ping-back responses (`❌ *Voice Download Error:*` vs. `❌ *Voice Transcription Error:*`) with full exception tracebacks in `logger.exception`.
- Added 4 unit tests in `tests/test_telegram_bridge.py` verifying connection pool singleton lifecycle, transient SSL timeout retries, retry exhaustion handling, and error differentiation.
- Fixed Telegram Mobile Bridge default model tier: changed `telegram_default_tier` in `src/nexus/core/config.py` from `"strong"` to `"low"`, enabling sub-second mobile turns on `gemini-3.8-flash` with >99% cost reduction while preserving `/strong` or `/argon` per-turn overrides.
- Enhanced voice note and audio memo transcription in `src/nexus/shared_tools/telegram_bridge.py`: prioritized ultra-fast OpenAI Whisper API (`whisper-1`, ~1.2s latency) with automatic fallback to Gemini Flash multimodal audio (`gemini-3.8-flash`), and normalized audio extensions and clean MIME types.
- Expanded Telegram media ingestion to recognize audio payloads across native voice notes (`message.voice`), audio tracks (`message.audio`), circular video notes (`message.video_note`), and audio files uploaded as documents (`message.document`).
- Extended background `'typing...'` status heartbeat across the entire turn lifecycle (audio download, speech-to-text transcription, and agent reasoning) to eliminate silent timeouts on mobile devices.
- Hardened Loguru console logging on Windows in `src/nexus/core/logger.py` with UTF-8 stream reconfiguration to prevent `charmap` `UnicodeEncodeError` exceptions on emoji log messages.
- **Multi-Thread Pub/Sub Telemetry Isolation (`src/nexus/core/trace.py`, `src/nexus/api/routers/agents.py`, `src/nexus/agent/`):** Fixed cross-thread trace event pollution where opening multiple agent threads or browser tabs and executing queries concurrently caused telemetry events to leak across streams. Added execution-context-scoped `thread_id` tracking via Python `contextvars`, enhanced `AgentTracer` and subagent constructors with explicit `thread_id`, and updated `TraceEventBus.subscribe()` and `emit()` to enforce strict thread filtering so SSE streams and run logs receive only events belonging to their active conversation.
- **Next.js React Key Collision Prevention (`gui/src/components/AgentTraceVisualizer.tsx`):** Fixed the Next.js runtime error (`Encountered two children with the same key, ead90046`) by replacing raw `key={evt.id ?? idx}` with composite resilient keys `key={evt.id ? `${evt.id}-${idx}` : `step-${idx}`}` across both `AgentGraphView` and `ThinkingPanel`.
- **Chat Stream Abort & State Isolation (`gui/src/app/chat/page.tsx`):** Added automated stream teardown (`abortRef.current?.()`) upon thread switching, new chat creation, or conversation deletion, and added event-ID deduplication and active conversation ownership guards to streaming callbacks (`onTrace`, `onDone`, `onError`) to prevent stale or cross-convo mutations.
- **Automated Regression Suite (`tests/test_agent_tracking_and_graph.py`):** Added unit tests verifying strict pub/sub thread isolation and contextvar/explicit thread inheritance on `AgentTracer`.

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
