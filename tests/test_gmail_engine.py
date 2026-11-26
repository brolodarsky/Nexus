"""
test_gmail_engine.py — Unit tests for Gmail Engine account-alias safety, headless OAuth guards, and fetch_emails resilience.
"""

import base64
import email as email_lib
import json
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nexus.core import chats_db, conversation_cache
from nexus.core.google_auth import get_google_credentials
from nexus.core.hitl_queue import reset_hitl_execution_context, set_hitl_execution_context
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


def test_list_messages_all_deduplicates_by_id_and_prefers_email_alias(monkeypatch: pytest.MonkeyPatch):
    """Verify list_messages(account='all') deduplicates identical IDs across aliased tokens without halving max_results."""
    monkeypatch.setattr(
        gmail_engine,
        "list_available_accounts",
        lambda: ["default", "williamvolodarsky@gmail.com"],
    )

    # Simulate two aliased tokens pointing to the same mailbox returning overlapping messages
    def fake_single_list(query="", max_results=10, account="default", service=None, include_archived=False):
        if account == "default":
            return [
                {"id": "m1", "account": "default", "date": "2026-11-25T10:00:00-05:00", "subject": "One"},
                {"id": "m2", "account": "default", "date": "2026-11-24T10:00:00-05:00", "subject": "Two"},
            ]
        return [
            {"id": "m1", "account": "williamvolodarsky@gmail.com", "date": "2026-11-25T10:00:00-05:00", "subject": "One"},
            {"id": "m2", "account": "williamvolodarsky@gmail.com", "date": "2026-11-24T10:00:00-05:00", "subject": "Two"},
            {"id": "m3", "account": "williamvolodarsky@gmail.com", "date": "2026-11-23T10:00:00-05:00", "subject": "Three"},
        ]

    # Only intercept recursive single-account calls; let account='all' execute real aggregation logic
    orig_list = gmail_engine.list_messages

    def wrapper(query="", max_results=10, account="default", service=None, include_archived=False):
        if account.lower() == "all":
            return orig_list(query=query, max_results=max_results, account=account, service=service, include_archived=include_archived)
        return fake_single_list(query=query, max_results=max_results, account=account, service=service, include_archived=include_archived)

    monkeypatch.setattr(gmail_engine, "list_messages", wrapper)

    results = gmail_engine.list_messages(max_results=3, account="all")
    assert [r["id"] for r in results] == ["m1", "m2", "m3"]
    # Overlapping 'default' alias entries upgraded in place to verified email address
    assert results[0]["account"] == "williamvolodarsky@gmail.com"
    assert results[1]["account"] == "williamvolodarsky@gmail.com"


def test_fetch_emails_two_phase_scan_selective_hydration_and_body_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Verify default metadata scan, explicit include_body=True 20-cap, and message_ids=[...] batch hydration."""
    monkeypatch.setattr(chats_db, "DB_PATH", tmp_path / "test_chats.db")
    chats_db.init_db()
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
    monkeypatch.setattr(gmail_engine, "list_available_accounts", lambda: ["acc1@x.com", "acc2@x.com"])

    service_calls = 0

    def fake_get_service(account="default"):
        nonlocal service_calls
        service_calls += 1
        return MagicMock()

    def fake_get_message(message_id, account="default", service=None):
        assert service is not None, "fetch_emails must pass cached service into get_message"
        if message_id == "msg_3":
            raise RuntimeError("HttpError 403 rateLimitExceeded")
        if message_id == "msg_acc2" and account == "acc1@x.com":
            raise RuntimeError("HttpError 404 Not Found")
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

    # 1. Default scan mode returns metadata + snippets without calling get_message or creating services
    scan_items = json.loads(fetch_emails.invoke({"count": 25, "account": "all"}))
    assert len(scan_items) == 25
    assert service_calls == 0
    assert "body" not in scan_items[0]
    assert "body_omitted_reason" not in scan_items[0]
    assert scan_items[0]["snippet"] == "Snippet 0"

    # 2. Explicit include_body=True hydrates up to 20 bodies, caches service, and degrades msg_3 cleanly
    raw_json = fetch_emails.invoke({"count": 25, "account": "all", "include_body": True})
    items = json.loads(raw_json)

    assert recorded_list_calls == [
        {"query": "", "max_results": 25, "account": "all", "include_archived": False},
        {"query": "", "max_results": 25, "account": "all", "include_archived": False},
    ]
    assert len(items) == 25
    # Only 1 service built for all 20 hydrated messages on 'default'
    assert service_calls == 1
    assert items[0]["body"] == "Body for msg_0"
    assert items[0]["labels"] == ["INBOX", "UNREAD"]
    assert items[0]["cache_key"] == "cache://email/msg_0"
    assert "body_error" in items[3]
    assert items[3]["snippet"] == "Snippet 3"
    # Items 20..24 omitted body cleanly with message_ids hint
    assert "body" not in items[20]
    assert items[20]["snippet"] == "Snippet 20"
    assert "message_ids=['msg_20']" in items[20]["body_omitted_reason"]

    # 3. Selective batch hydration via message_ids skips list_messages, deduplicates IDs, and resolves across accounts
    batch_items = json.loads(
        fetch_emails.invoke({"message_ids": ["msg_0", "msg_acc2", "msg_0", "msg_3"], "account": "all"})
    )
    assert len(recorded_list_calls) == 2  # list_messages NOT called again
    assert [b["id"] for b in batch_items] == ["msg_0", "msg_acc2", "msg_3"]
    assert batch_items[0]["body"] == "Body for msg_0"
    assert batch_items[0]["account"] == "acc1@x.com"
    assert batch_items[1]["body"] == "Body for msg_acc2"
    assert batch_items[1]["account"] == "acc2@x.com"
    assert "body_error" in batch_items[2]


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


def _make_raw_gmail_response(mime_msg: EmailMessage, msg_id: str = "msg_mime_1") -> dict:
    """Encode an EmailMessage into the base64url payload shape returned by Gmail `format='raw'`."""
    encoded = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")
    return {
        "id": msg_id,
        "threadId": "th_mime_1",
        "internalDate": "1764000000000",
        "labelIds": ["INBOX", "UNREAD"],
        "raw": encoded,
    }


def test_get_message_surfaces_attachments_inline_media_html_images_and_skips_pixels(
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify non-plain-text MIME parts, meaningful HTML images/media, and pixel filtering."""
    msg = EmailMessage()
    msg["From"] = "Recruiter <recruiter@example.com>"
    msg["To"] = "williamvolodarsky@gmail.com"
    msg["Subject"] = "Offer & Onboarding Packet"
    msg["Message-ID"] = "<offer-1@example.com>"
    msg.set_content("Plain fallback body.")

    html_body = """
    <html><body>
      <p>Hi William, please review the chart below:</p>
      <img src="https://track.example.com/open.png" width="1" height="1" alt="">
      <img src="https://track.example.com/hidden.png" style="display:none; width:10px; height:10px;">
      <img src="https://example.com/chart.png" alt="Q4 Growth Chart">
      <a href="https://example.com/portal"><img src="https://example.com/btn.png" alt="Open Portal"></a>
      <img src="cid:img123">
      <iframe title="Onboarding Walkthrough" src="https://example.com/embed"></iframe>
      <svg role="img" aria-label="Company Crest"><path d="M0 0"/></svg>
    </body></html>
    """
    msg.add_alternative(html_body, subtype="html")
    # Attach inline PNG referenced by cid:img123 on the HTML alternative part
    html_part = msg.get_payload()[1]
    html_part.add_related(
        b"\x89PNG\r\n\x1a\n" + b"0" * 120,
        maintype="image",
        subtype="png",
        cid="<img123>",
        filename="screenshot.png",
    )
    # Explicit PDF attachment
    msg.add_attachment(
        b"%PDF-1.4\n" + b"x" * 2048,
        maintype="application",
        subtype="pdf",
        filename="Offer_Letter.pdf",
    )
    # Unnamed text/calendar invite part (no filename)
    msg.add_attachment(
        "BEGIN:VCALENDAR\nMETHOD:REQUEST\nEND:VCALENDAR",
        subtype="calendar",
    )

    fake_svc = MagicMock()
    fake_svc.users.return_value.messages.return_value.get.return_value.execute.return_value = (
        _make_raw_gmail_response(msg)
    )
    monkeypatch.setattr(gmail_engine, "get_token_filename", lambda account="default": "token_gmail.json")
    monkeypatch.setattr(gmail_engine, "resolve_account_display_name", lambda acc, tf: acc)

    parsed = gmail_engine.get_message("msg_mime_1", account="default", service=fake_svc)

    # 1. Structured attachments include both Offer_Letter.pdf and unnamed text/calendar
    assert len(parsed["attachments"]) == 2
    by_mime = {a["mime_type"]: a for a in parsed["attachments"]}
    assert by_mime["application/pdf"]["filename"] == "Offer_Letter.pdf"
    assert by_mime["application/pdf"]["size_bytes"] > 2000
    assert by_mime["text/calendar"]["filename"] == "(unnamed)"

    # 2. Inline MIME media carries Content-ID and size metadata
    assert len(parsed["inline_media"]) == 1
    assert parsed["inline_media"][0]["filename"] == "screenshot.png"
    assert parsed["inline_media"][0]["content_id"] == "img123"

    # 3. Markdown body includes meaningful image/media placeholders and preserves link text, while skipping pixels
    assert "[Image: Q4 Growth Chart]" in parsed["body"]
    assert "[Open Portal](https://example.com/portal)" in parsed["body"]
    assert "[Inline Image: screenshot.png (image/png," in parsed["body"]
    assert "[Embedded Iframe: Onboarding Walkthrough]" in parsed["body"]
    assert "[SVG Graphic: Company Crest]" in parsed["body"]
    assert "track.example.com" not in parsed["body"]

    # 4. Non-text notice summarizes all non-plain-text elements and caveats binary/visual inspection
    assert parsed["has_non_text_content"] is True
    notice = parsed["non_text_notice"]
    assert "Offer_Letter.pdf (application/pdf" in notice
    assert "calendar invite: (unnamed) (text/calendar" in notice
    assert "screenshot.png (image/png" in notice
    assert "HTML image(s)" in notice
    assert "embedded HTML media" in notice
    assert "not extracted or visually inspected" in notice

    # 5. Markdown rendering surfaces Attachments and Non-Text Notice headers
    rendered_md = gmail_engine.message_to_markdown(parsed)
    assert "**Attachments:** Offer_Letter.pdf (application/pdf," in rendered_md
    assert "**Non-Text Notice:** Email contains non-plain-text content" in rendered_md


def test_get_message_plain_text_has_no_notice_and_image_only_has_placeholder(monkeypatch: pytest.MonkeyPatch):
    """Verify pure plain-text emails stay clean while image-only MIME emails avoid misleading empty-body messages."""
    monkeypatch.setattr(gmail_engine, "get_token_filename", lambda account="default": "token_gmail.json")
    monkeypatch.setattr(gmail_engine, "resolve_account_display_name", lambda acc, tf: acc)

    plain_msg = EmailMessage()
    plain_msg["From"] = "friend@example.com"
    plain_msg["To"] = "me@example.com"
    plain_msg["Subject"] = "Quick check-in"
    plain_msg.set_content("Just plain text here.")

    svc_plain = MagicMock()
    svc_plain.users.return_value.messages.return_value.get.return_value.execute.return_value = (
        _make_raw_gmail_response(plain_msg, "msg_plain")
    )
    res_plain = gmail_engine.get_message("msg_plain", service=svc_plain)
    assert res_plain["attachments"] == []
    assert res_plain["inline_media"] == []
    assert res_plain["has_non_text_content"] is False
    assert res_plain["non_text_notice"] == ""

    img_only = EmailMessage()
    img_only["From"] = "flyer@example.com"
    img_only["To"] = "me@example.com"
    img_only["Subject"] = "Event Flyer"
    img_only.set_content(b"\x89PNG\r\n\x1a\n" + b"1" * 64, maintype="image", subtype="png", filename="flyer.png")

    svc_img = MagicMock()
    svc_img.users.return_value.messages.return_value.get.return_value.execute.return_value = (
        _make_raw_gmail_response(img_only, "msg_img_only")
    )
    res_img = gmail_engine.get_message("msg_img_only", service=svc_img)
    assert res_img["has_non_text_content"] is True
    assert "non_text_notice" in res_img["body"]
    assert "flyer.png (image/png" in res_img["non_text_notice"]


def test_fetch_emails_propagates_non_text_metadata_and_caches_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Verify fetch_emails surfaces non-text notices/attachments in JSON + cache:// while keeping plain text lean."""
    monkeypatch.setattr(chats_db, "DB_PATH", tmp_path / "test_chats.db")
    chats_db.init_db()

    monkeypatch.setattr(
        gmail_engine,
        "list_messages",
        lambda **_kw: [
            {"id": "msg_att", "account": "default", "thread_id": "th_1", "subject": "With PDF", "labels": ["INBOX"]},
            {"id": "msg_txt", "account": "default", "thread_id": "th_2", "subject": "Plain", "labels": ["INBOX"]},
        ],
    )
    monkeypatch.setattr(gmail_engine, "get_gmail_service", lambda account="default": MagicMock())

    def fake_get_msg(message_id, account="default", service=None):
        if message_id == "msg_att":
            return {
                "id": "msg_att",
                "account": "default",
                "thread_id": "th_1",
                "subject": "With PDF",
                "sender": "hr@example.com",
                "date": "2026-11-25",
                "labels": ["INBOX"],
                "attachments": [{"filename": "contract.pdf", "mime_type": "application/pdf", "size_bytes": 1024, "size": "1.0 KB", "disposition": "attachment"}],
                "inline_media": [{"filename": "logo.png", "mime_type": "image/png", "size_bytes": 500, "size": "500 B", "disposition": "inline", "content_id": "logo1"}],
                "has_non_text_content": True,
                "non_text_notice": "Email contains non-plain-text content — 1 attachment(s): contract.pdf (application/pdf, 1.0 KB).",
                "body": "See attached contract.",
            }
        return {
            "id": "msg_txt",
            "account": "default",
            "thread_id": "th_2",
            "subject": "Plain",
            "sender": "bob@example.com",
            "date": "2026-11-25",
            "labels": ["INBOX"],
            "attachments": [],
            "inline_media": [],
            "has_non_text_content": False,
            "non_text_notice": "",
            "body": "Hello world.",
        }

    monkeypatch.setattr(gmail_engine, "get_message", fake_get_msg)
    tok = set_hitl_execution_context(conversation_id="conv-att-test", thread_id="conv-att-test")
    try:
        items = json.loads(fetch_emails.invoke({"count": 2, "include_body": True}))
        assert len(items) == 2
        assert items[0]["attachments"][0]["filename"] == "contract.pdf"
        assert items[0]["inline_media"][0]["filename"] == "logo.png"
        assert "contract.pdf" in items[0]["non_text_notice"]
        # Pure plain-text email omits empty non-text keys
        assert "attachments" not in items[1]
        assert "non_text_notice" not in items[1]

        cached = conversation_cache.get_capture("conv-att-test", "cache://email/msg_att")
        assert cached is not None
        assert "**Attachments:** contract.pdf (application/pdf, 1.0 KB)" in cached["content"]
        assert "**Non-Text Notice:**" in cached["content"]

        # Verify message_ids batch mode also preserves attachments & non-text notices
        batch_items = json.loads(fetch_emails.invoke({"message_ids": ["msg_att"]}))
        assert len(batch_items) == 1
        assert batch_items[0]["attachments"][0]["filename"] == "contract.pdf"
        assert "contract.pdf" in batch_items[0]["non_text_notice"]
    finally:
        reset_hitl_execution_context(tok)


def test_list_send_as_aliases_and_create_draft_send_as(monkeypatch: pytest.MonkeyPatch, capsys):
    """Verify Send-As listing, verification guards, auto-account routing with 'all', and CLI flags."""
    aliases_by_account = {
        "williamvolodarsky@gmail.com": [
            {
                "sendAsEmail": "williamvolodarsky@gmail.com",
                "displayName": "",
                "isDefault": True,
                "isPrimary": True,
            },
            {
                "sendAsEmail": "bill@williamvolodarsky.com",
                "displayName": "William Volodarsky",
                "isDefault": False,
                "isPrimary": False,
                "verificationStatus": "accepted",
            },
            {
                "sendAsEmail": "pending@williamvolodarsky.com",
                "displayName": "Pending",
                "isDefault": False,
                "isPrimary": False,
                "verificationStatus": "pending",
            },
        ],
        "wv@fordham.edu": [
            {
                "sendAsEmail": "wv@fordham.edu",
                "displayName": "William V",
                "isDefault": True,
                "isPrimary": True,
            }
        ],
    }
    draft_payloads: list[tuple[str, dict]] = []

    def make_service(acc_name: str):
        svc = MagicMock()
        svc.users.return_value.settings.return_value.sendAs.return_value.list.return_value.execute.return_value = {
            "sendAs": aliases_by_account[acc_name]
        }

        def fake_create_draft(userId="me", body=None):
            draft_payloads.append((acc_name, body))
            mock_exec = MagicMock()
            mock_exec.execute.return_value = {
                "id": f"draft_{len(draft_payloads)}",
                "message": {"id": f"msg_{len(draft_payloads)}", "threadId": "th_new"},
            }
            return mock_exec

        svc.users.return_value.drafts.return_value.create.side_effect = fake_create_draft
        return svc

    monkeypatch.setattr(
        gmail_engine,
        "list_available_accounts",
        lambda: ["all", "williamvolodarsky@gmail.com", "wv@fordham.edu"],
    )
    monkeypatch.setattr(gmail_engine, "get_gmail_service", lambda account="default": make_service(account))
    monkeypatch.setattr(gmail_engine, "get_token_filename", lambda account="default": f"token_gmail_{account}.json")
    monkeypatch.setattr(gmail_engine, "resolve_account_display_name", lambda acc, tf: acc)

    # 1. list_send_as_aliases(account="all") aggregates across accounts cleanly
    all_aliases = gmail_engine.list_send_as_aliases(account="all")
    assert len(all_aliases) == 4
    assert {a["account"] for a in all_aliases} == {"williamvolodarsky@gmail.com", "wv@fordham.edu"}

    # 2. create_draft with account="all" + send_as auto-routes to owning account and sets formatted From header
    res = gmail_engine.create_draft(
        to="recruiter@company.com",
        subject="Hello",
        body="Body text",
        account="all",
        send_as="bill@williamvolodarsky.com",
    )
    assert res["account"] == "williamvolodarsky@gmail.com"
    assert res["send_as"] == "William Volodarsky <bill@williamvolodarsky.com>"
    raw_bytes = base64.urlsafe_b64decode(draft_payloads[-1][1]["message"]["raw"])
    parsed_draft = email_lib.message_from_bytes(raw_bytes)
    assert parsed_draft["From"] == "William Volodarsky <bill@williamvolodarsky.com>"

    # 3. Caller-supplied display name overrides Gmail's stored displayName
    res_custom = gmail_engine.create_draft(
        to="recruiter@company.com",
        subject="Hello",
        body="Body text",
        account="williamvolodarsky@gmail.com",
        send_as="Bill V <bill@williamvolodarsky.com>",
    )
    assert res_custom["send_as"] == "Bill V <bill@williamvolodarsky.com>"

    # 4. Unverified / unknown aliases raise clear ValueError
    with pytest.raises(ValueError, match="not verified"):
        gmail_engine.create_draft(
            to="x@y.com", subject="S", body="B", account="all", send_as="pending@williamvolodarsky.com"
        )
    with pytest.raises(ValueError, match="not found"):
        gmail_engine.create_draft(
            to="x@y.com", subject="S", body="B", account="all", send_as="unknown@example.com"
        )

    # 5. CLI --list-send-as and --draft ... --send-as flags wire cleanly
    monkeypatch.setattr("sys.argv", ["gmail_engine", "--list-send-as", "--account", "all", "--json"])
    gmail_engine.main()
    out_aliases = json.loads(capsys.readouterr().out)
    assert len(out_aliases) == 4

    monkeypatch.setattr(
        "sys.argv",
        [
            "gmail_engine",
            "--draft",
            "to@example.com",
            "Subj",
            "Body",
            "--account",
            "all",
            "--send-as",
            "bill@williamvolodarsky.com",
        ],
    )
    gmail_engine.main()
    draft_out = capsys.readouterr().out
    assert "as 'William Volodarsky <bill@williamvolodarsky.com>'" in draft_out
