---
type: patch
---
### Fixed
- Guarded reserved `"all"` account alias across `gmail_engine.py` (`load_accounts_map`, `list_available_accounts`, `get_token_filename`, `authenticate_account`, `get_gmail_service`) and removed poisoned `.secrets/token_gmail_all.json` so `list_messages(..., account="all")` can no longer enter a `RecursionError` multiplier loop.
- Added multi-account support to `gmail_engine.list_labels(account="all")` and `--labels --account all` so label discovery aggregates across concrete accounts without triggering an interactive OAuth login for `"all"`.
- Updated `google_auth.get_google_credentials` to persist refreshed tokens atomically to disk, default `allow_interactive=False` (raising an actionable `RuntimeError` in headless/agent contexts instead of hanging on `flow.run_local_server`), and bound interactive `--auth` waits (`timeout_seconds=120`).
- Updated `shared.fetch_emails` to cache per-account Gmail Discovery clients, cap automatic full-body hydration to the newest 20 emails in sweep mode (`include_body=None`), include `labels`, and degrade gracefully per message instead of failing the entire batch on `HttpError 403 rateLimitExceeded`.
- Added 30s `AuthorizedHttp` socket timeouts in `gmail_engine.py`, bounded tool/subagent timeouts (`nexus_tool_timeout=120`, `nexus_subagent_timeout=900`) with detached `ThreadPoolExecutor` cleanup and `tool_error` tracing in `graph.py`, and assistant error + trace persistence in `agents.py` `_run_pipeline` so failed/timed-out runs always terminate cleanly for both the agent and GUI.
