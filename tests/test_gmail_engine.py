"""
test_gmail_engine.py — Unit tests for Gmail Engine account-alias safety, headless OAuth guards, and fetch_emails resilience.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nexus.core.google_auth import get_google_credentials
from nexus.shared_tools import gmail_engine
from nexus.shared_tools.shared import fetch_emails


def test_reserved_all_alias_ignored_in_discovery_and_rejected_for_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Ensure token_gmail_all.json and 'all' entries can never register as a real account or trigger recursion."""
    secrets_dir = tmp_path / ".secrets"
    secrets_dir.mkdir()
    (secrets_dir / "token_gmail.json").write_text("{}", encoding="utf-8")
    (secrets_dir / "token_gmail_all.json").write_text("{}", encoding="utf-8")
    (secrets_dir / "token_gmail_work@example.com.json").write_text("{}", encoding="utf-8")
    (secrets_dir / "gmail_accounts.json").write_text(
        json.dumps({"all": "token_gmail_all.json", "work@example.com": "token_gmail_work@example.com.json"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(gmail_engine, "SECRETS_DIR", str(secrets_dir))
    monkeypatch.setattr(gmail_engine, "ACCOUNTS_MAP_FILE", str(secrets_dir / "gmail_accounts.json"))

    acct_map = gmail_engine.load_accounts_map()
    assert "all" not in {k.lower() for k in acct_map}
    assert "work@example.com" in acct_map

    available = gmail_engine.list_available_accounts(secrets_dir=str(secrets_dir))
    assert "all" not in {a.lower() for a in available}
    assert "work@example.com" in available
    assert "default" in available

    with pytest.raises(ValueError, match="reserved"):
        gmail_engine.get_token_filename("all")
    with pytest.raises(ValueError, match="reserved"):
        gmail_engine.authenticate_account("ALL")
    with pytest.raises(ValueError, match="concrete account"):
        gmail_engine.get_gmail_service("all")


def test_list_messages_and_list_labels_all_aggregate_without_recursion(monkeypatch: pytest.MonkeyPatch):
    """Verify account='all' aggregates concrete accounts safely and surfaces errors when all accounts fail."""
    # Even if list_available_accounts were somehow mocked to include 'all', list_messages must filter it out
    monkeypatch.setattr(gmail_engine, "list_available_accounts", lambda: ["all", "acc1@x.com", "acc2@x.com"])

    fake_svc = MagicMock()
    fake_svc.users.return_value.labels.return_value.list.return_value.execute.return_value = {
        "labels": [{"id": "Label_1", "name": "Jobs", "type": "user"}]
    }
    monkeypatch.setattr(gmail_engine, "get_gmail_service", lambda account="default": fake_svc)
    monkeypatch.setattr(gmail_engine, "get_token_filename", lambda account="default": f"token_gmail_{account}.json")
    monkeypatch.setattr(gmail_engine, "resolve_account_display_name", lambda acc, tf: acc)

    labels = gmail_engine.list_labels(account="all")
    assert len(labels) == 2
    assert {l["account"] for l in labels} == {"acc1@x.com", "acc2@x.com"}

    # Test real list_messages('all') delegating to failing single-account calls via get_gmail_service error
    monkeypatch.setattr(
        gmail_engine,
        "get_gmail_service",
        lambda account="default": (_ for _ in ()).throw(RuntimeError(f"auth failed for {account}")),
    )
    with pytest.raises(RuntimeError, match="failed across all accounts"):
        gmail_engine.list_messages(query="from:recruiter", max_results=5, account="all")


def test_google_auth_headless_guard_and_refresh_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify non-interactive auth raises cleanly instead of launching a browser, and refreshed tokens persist."""
    secrets_dir = tmp_path / ".secrets"
    secrets_dir.mkdir()

    # 1. Missing token with allow_interactive=False must raise RuntimeError immediately
    with pytest.raises(RuntimeError, match="interactive browser login is disabled"):
        get_google_credentials(
            scopes=["https://www.googleapis.com/auth/gmail.modify"],
            secrets_dir=str(secrets_dir),
            token_filename="token_missing.json",
            allow_interactive=False,
        )

    # 2. Expired token with refresh_token refreshes and writes updated JSON back to disk
    token_path = secrets_dir / "token_gmail.json"
    token_path.write_text("{}", encoding="utf-8")

    fake_creds = MagicMock()
    fake_creds.valid = False
    fake_creds.expired = True
    fake_creds.refresh_token = "refresh_123"
    fake_creds.to_json.return_value = json.dumps({"token": "fresh_tok", "refresh_token": "refresh_123"})

    def do_refresh(_req):
        fake_creds.valid = True
        fake_creds.expired = False

    fake_creds.refresh.side_effect = do_refresh

    with patch("nexus.core.google_auth.Credentials.from_authorized_user_file", return_value=fake_creds):
        res = get_google_credentials(
            scopes=["https://www.googleapis.com/auth/gmail.modify"],
            secrets_dir=str(secrets_dir),
            token_filename="token_gmail.json",
            allow_interactive=False,
        )

    assert res is fake_creds
    assert json.loads(token_path.read_text(encoding="utf-8"))["token"] == "fresh_tok"


def test_fetch_emails_caps_bodies_caches_service_and_degrades_per_message(monkeypatch: pytest.MonkeyPatch):
    """Verify fetch_emails reuses Gmail service clients, caps auto-body hydration at 20, and handles per-msg errors."""
    summaries = [
        {
            "id": f"msg_{i}",
            "account": "default",
            "thread_id": f"th_{i}",
            "date": f"2026-11-16T12:{i:02d}:00-05:00",
            "sender": f"sender{i}@example.com",
            "subject": f"Subject {i}",
            "snippet": f"Snippet {i}",
            "labels": ["INBOX", "UNREAD"] if i % 2 == 0 else ["INBOX"],
        }
        for i in range(25)
    ]

    recorded_list_calls: list[dict] = []

    def fake_list_messages(query="", max_results=10, account="default", include_archived=False):
        recorded_list_calls.append({
            "query": query,
            "max_results": max_results,
            "account": account,
            "include_archived": include_archived,
        })
        return summaries

    monkeypatch.setattr(gmail_engine, "list_messages", fake_list_messages)

    service_calls = 0

    def fake_get_service(account="default"):
        nonlocal service_calls
        service_calls += 1
        return MagicMock()

    def fake_get_message(message_id, account="default", service=None):
        assert service is not None, "fetch_emails must pass cached service into get_message"
        if message_id == "msg_3":
            raise RuntimeError("HttpError 403 rateLimitExceeded")
        return {
            "id": message_id,
            "account": account,
            "thread_id": f"th_{message_id}",
            "subject": f"Full {message_id}",
            "sender": "sender@example.com",
            "date": "2026-11-16T12:00:00-05:00",
            "labels": ["INBOX", "UNREAD"],
            "body": f"Body for {message_id}",
        }

    monkeypatch.setattr(gmail_engine, "get_gmail_service", fake_get_service)
    monkeypatch.setattr(gmail_engine, "get_message", fake_get_message)

    raw_json = fetch_emails.invoke({"count": 25, "account": "all"})
    items = json.loads(raw_json)

    assert recorded_list_calls == [{"query": "", "max_results": 25, "account": "all", "include_archived": False}]
    assert len(items) == 25
    # Only 1 service built for all 20 hydrated messages on 'default'
    assert service_calls == 1
    # First 20 hydrated (with msg_3 gracefully degraded to snippet + body_error)
    assert items[0]["body"] == "Body for msg_0"
    assert items[0]["labels"] == ["INBOX", "UNREAD"]
    assert "body_error" in items[3]
    assert items[3]["snippet"] == "Snippet 3"
    # Items 20..24 omitted body cleanly with metadata + snippet preserved
    assert "body" not in items[20]
    assert items[20]["snippet"] == "Snippet 20"
    assert "Summary only in sweep mode" in items[20]["body_omitted_reason"]


def test_build_effective_query_and_list_messages_archive_options(monkeypatch: pytest.MonkeyPatch):
    """Verify inbox-default (all labels, no archived) and include_archived=True (all mail)."""
    assert gmail_engine._build_effective_query("", include_archived=False) == "in:inbox"
    assert (
        gmail_engine._build_effective_query("from:openai.com newer_than:7d", include_archived=False)
        == "in:inbox (from:openai.com newer_than:7d)"
    )
    assert (
        gmail_engine._build_effective_query("from:a OR from:b", include_archived=False)
        == "in:inbox (from:a OR from:b)"
    )
    assert gmail_engine._build_effective_query("in:sent", include_archived=False) == "in:sent"
    assert gmail_engine._build_effective_query("in:anywhere from:x", include_archived=False) == "in:anywhere from:x"
    assert gmail_engine._build_effective_query("from:openai.com", include_archived=True) == "from:openai.com"
    assert gmail_engine._build_effective_query("", include_archived=True) == ""

    captured_kwargs: list[dict] = []

    def fake_list_call(**kwargs):
        captured_kwargs.append(kwargs)
        mock_exec = MagicMock()
        mock_exec.execute.return_value = {"messages": []}
        return mock_exec

    fake_svc = MagicMock()
    fake_svc.users.return_value.messages.return_value.list.side_effect = fake_list_call

    monkeypatch.setattr(gmail_engine, "list_available_accounts", lambda: ["acc1@x.com"])
    monkeypatch.setattr(gmail_engine, "get_gmail_service", lambda account="default": fake_svc)
    monkeypatch.setattr(gmail_engine, "get_token_filename", lambda account="default": f"token_gmail_{account}.json")
    monkeypatch.setattr(gmail_engine, "resolve_account_display_name", lambda acc, tf: acc)

    # Default call: sweeps all of in:inbox regardless of labels
    gmail_engine.list_messages(account="all")
    # Explicit query with include_archived=True: passes raw query with no inbox restriction
    gmail_engine.list_messages(query="from:recruiter", account="all", include_archived=True)
    # Empty query with include_archived=True: omits `q` entirely to fetch all non-spam/trash mail
    gmail_engine.list_messages(query="", account="all", include_archived=True)

    assert captured_kwargs == [
        {"userId": "me", "maxResults": 10, "q": "in:inbox"},
        {"userId": "me", "maxResults": 10, "q": "from:recruiter"},
        {"userId": "me", "maxResults": 10},
    ]


def test_fetch_emails_and_cli_forward_include_archived(monkeypatch: pytest.MonkeyPatch, capsys):
    """Verify fetch_emails and CLI --list/--search/--include-archived forward query & archive flags cleanly."""
    seen: list[dict] = []

    def fake_list_messages(query="", max_results=10, account="default", include_archived=False):
        seen.append({
            "query": query,
            "max_results": max_results,
            "account": account,
            "include_archived": include_archived,
        })
        return []

    monkeypatch.setattr(gmail_engine, "list_messages", fake_list_messages)

    res = json.loads(fetch_emails.invoke({"query": "subject:offer", "count": 7, "include_archived": True}))
    assert res == []

    monkeypatch.setattr("sys.argv", ["gmail_engine", "--list", "12", "--account", "all"])
    gmail_engine.main()
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        ["gmail_engine", "--search", "from:greenhouse.io", "--max", "15", "--include-archived"],
    )
    gmail_engine.main()
    capsys.readouterr()

    assert seen == [
        {"query": "subject:offer", "max_results": 7, "account": "all", "include_archived": True},
        {"query": "", "max_results": 12, "account": "all", "include_archived": False},
        {"query": "from:greenhouse.io", "max_results": 15, "account": "default", "include_archived": True},
    ]
