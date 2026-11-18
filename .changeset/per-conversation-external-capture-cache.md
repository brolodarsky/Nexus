---
type: minor
---
### Added
- Universal **Per-Conversation External Capture Cache** (`src/nexus/core/conversation_cache.py`, `conversation_captures` SQLite WAL table in `logs/chats.db`) providing `put_capture()`, `get_capture()`, `list_captures()`, `format_captures_manifest()`, `inherit_captures()`, `clear_captures()`, and universal tracking-param URL normalization (`normalize_capture_url()`).
- Automatic conversation inheritance across `fork_conversation()` and `spawn_seeded_conversation()` (`src/nexus/core/chat_branching.py`) and automatic capture purge inside `delete_conversation()` (`src/nexus/core/chats_db.py`).
- Universal `cache://` hydration (`read_file("cache://")`, `read_file("cache://<key>")`, cached URLs, and `spawn_subagent(..., context_files=["cache://..."])`) with fail-fast missing-key diagnostics and zero dynamic `SystemMessage` mutation (preserving KV prompt caching).
- Universal deterministic `{{cache:<key>}}` single-pass splicing across both `create_file` and `modify_file` (`src/nexus/shared_tools/shared.py`), plus `NEXUS_CONVERSATION_ID` propagation in `run_shared_tool_cli` and full untruncated email caching (`cache://email/<msg_id>`) in `fetch_emails`.
- Comprehensive regression test suite `tests/test_conversation_cache.py` and expanded Chrome Extension DOM deduplication tests in `tests/test_browser_extension_dom.js`.

### Fixed
- Chrome Extension DOM payload tripling in `extractTabMarkdownReadOnly()` (`src/nexus/shared_tools/browser_extension/background.js`): prioritizes live rendered DOM (`cleanMarkdown`) and includes JSON-LD schema (`jsonLdEntries`, up to `charBudget`) and `metaDescription` only when the rendered DOM is sparse or missing that content.
- Isolated `chats_db.DB_PATH` in `tests/test_gmail_engine.py` so email hydration tests never write to `logs/chats.db`.

### Changed
- `browser_bridge.read_tabs()` and `format_tab_reads_as_markdown()` now store captures in `conversation_cache` (`cache://tab/<slug>`) and emit `Cache Key` handles in tab headers.
- `read_webpage.py` (`scrape_url()` / `scrape_url_with_cache()`) now checks `conversation_cache.get_capture()` first, then falls back universally to `trafilatura` + generic Schema.org JSON-LD / `<meta>` extraction and caches the result under `cache://web/<slug>`.
- Updated `Vault/Master Instructions.md`, `Vault/3. Operations/3.1. Career Strategy & Revenue/Section Instructions.md`, `README.md`, and living Engineering docs.

### Removed
- All vendor-specific ATS regexes and API scrapers from `src/nexus/shared_tools/read_webpage.py` (`_ASHBY_RE`, `_GREENHOUSE_RE`, `_LEVER_RE`, `_fetch_json`, `_clean_plain_text`, `_scrape_ashby_job`, `_extract_greenhouse_candidates`, `_discover_greenhouse_board_from_html`, `_format_greenhouse_pay_ranges`, `_scrape_greenhouse_job`, `_format_lever_salary`, `_scrape_lever_job`, `_lookup_browser_cache`).
- The legacy global flat JSON tab cache (`logs/browser_tab_cache.json`, `TAB_CACHE_PATH`, `_TAB_CACHE_LOCK`, `_MAX_CACHED_TABS`, `_NOISY_QUERY_PARAMS`, `normalize_job_url`, `_load_tab_cache_unlocked`, `_save_tab_cache_unlocked`, `_cache_read_tabs`, `get_cached_tab_markdown`) from `src/nexus/shared_tools/browser_bridge.py`.
- The folder-specific `"saved job listings/"` hook (`_SYNTHETIC_JD_HEADINGS`, `_extract_frontmatter_source`, `_enforce_verbatim_saved_job_listing()`) from `src/nexus/shared_tools/shared.py` and obsolete `tests/test_job_listing_verbatim_guard.py`.
