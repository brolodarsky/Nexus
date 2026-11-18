"""
google_auth.py — Centralized Google OAuth2 management for Nexus.
Handles token loading, refreshing, and browser-based authentication flows for Google services.
"""
import os
import sys
import tempfile
import threading
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Mutex lock protecting atomic token file writes when concurrent threads refresh the same OAuth credential
_token_write_lock = threading.Lock()


def _persist_refreshed_token(token_file: str, creds: Credentials) -> None:
    """Atomically write refreshed OAuth credentials back to `token_file` to avoid repeated refresh calls."""
    parent_dir = os.path.dirname(os.path.abspath(token_file))
    os.makedirs(parent_dir, exist_ok=True)
    with _token_write_lock:
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_token_", suffix=".json", dir=parent_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
                tmp_f.write(creds.to_json())
            os.replace(tmp_path, token_file)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise


# `allow_interactive: bool = False` prevents background worker threads/agents from blocking on a browser OAuth popup.
# `interactive_timeout_seconds: Optional[int] = 120` bounds the local OAuth callback server wait when interactive login is enabled.
# `auth_hint: Optional[str] = None` provides an actionable CLI command to include in error messages when headless auth fails.
def get_google_credentials(
    scopes: list[str],
    secrets_dir: str,
    token_filename: str = "token.json",
    allow_interactive: bool = False,
    interactive_timeout_seconds: Optional[int] = 120,
    auth_hint: Optional[str] = None,
) -> Credentials:
    """
    Generic Google OAuth2 credential handler.
    Loads existing tokens, refreshes them if expired (persisting refreshed tokens to disk),
    and either launches a bounded browser login flow (when `allow_interactive=True`) or raises
    an actionable `RuntimeError` in headless/agent contexts so worker threads never hang.

    Args:
        scopes: List of OAuth2 scopes required (e.g. Google Calendar, Gmail).
        secrets_dir: Path to the directory containing 'credentials.json' and where the token will be saved.
        token_filename: Name of the token cache file (defaults to 'token.json'; use 'token_calendar.json' for calendar).
        allow_interactive: Whether browser-based OAuth (`InstalledAppFlow.run_local_server`) is permitted if no valid token exists.
        interactive_timeout_seconds: Maximum seconds to wait for browser OAuth callback when `allow_interactive=True`.
        auth_hint: Optional terminal command hint surfaced in non-interactive auth failure errors.

    Returns:
        A valid google.oauth2.credentials.Credentials object.
    """
    token_file = os.path.join(secrets_dir, token_filename)
    credentials_file = os.path.join(secrets_dir, "credentials.json")

    creds = None

    # 1. Look for pre-existing local tokens
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)

    # 2. If token is missing or expired, resolve it
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Persist the refreshed token so subsequent API calls across threads skip redundant OAuth round-trips
                try:
                    _persist_refreshed_token(token_file, creds)
                except Exception as write_exc:
                    print(f"Warning: failed to cache refreshed token to '{token_file}': {write_exc}", file=sys.stderr)
            except Exception as e:
                # If refresh fails (e.g. revoked), clear creds so missing/invalid handling triggers cleanly
                print(f"Token refresh failed for '{token_filename}': {e}.", file=sys.stderr, flush=True)
                creds = None

        if not creds:
            # Headless / background worker guard: never block a server thread or subprocess on browser OAuth
            env_noninteractive = os.environ.get("NEXUS_NONINTERACTIVE_AUTH", "").strip().lower() in ("1", "true", "yes")
            if not allow_interactive or env_noninteractive:
                hint = auth_hint or f"Re-authenticate interactively (e.g. python -m nexus.shared_tools.gmail_engine --auth)."
                raise RuntimeError(
                    f"Google OAuth token '{token_filename}' is missing, expired without refresh, or revoked, "
                    f"and interactive browser login is disabled in non-interactive execution. {hint}"
                )

            # Requires credentials.json from Google Console
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"OAuth client credentials '{credentials_file}' not found. "
                    f"Download Desktop Client OAuth credentials from Google Cloud Console and save them in '{secrets_dir}'."
                )

            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, scopes)
            creds = flow.run_local_server(port=0, timeout_seconds=interactive_timeout_seconds)

            # Save structural tokens atomically for subsequent headless calls
            _persist_refreshed_token(token_file, creds)

    return creds
