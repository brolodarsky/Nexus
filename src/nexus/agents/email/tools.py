"""
tools.py — Core email fetching and parsing logic for the Nexus Engine's Email Agent.
Provides functions to connect to IMAP mailboxes, search emails, and fetch content.
"""
import imaplib
import email as email_lib
import email.header
import os
import sys
from typing import Optional
from html.parser import HTMLParser
from langchain_core.tools import tool

# Add engine root to sys.path for internal imports

from nexus.core.google_auth import get_google_credentials

# Full IMAP permissions scope for Google Accounts
SCOPES = ['https://mail.google.com/']

# ── HTML → plain text stripper ────────────────────────────────────────────────
class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
    def handle_data(self, data):
        stripped = data.strip()
        if stripped:
            self.text_parts.append(stripped)
    def get_text(self) -> str:
        return "\n".join(self.text_parts)

def _strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()

# ── IMAP helpers ──────────────────────────────────────────────────────────────
def _connect() -> imaplib.IMAP4_SSL:
    server = os.environ.get("IMAP_SERVER", "imap.gmail.com")
    port = int(os.environ.get("IMAP_PORT", 993))
    address = os.environ.get("EMAIL_ADDRESS")

    if not address:
        raise ValueError("EMAIL_ADDRESS environment variable must be set.")

    creds = get_google_credentials(SCOPES, SECRETS_DIR)
    auth_string = f"user={address}\x01auth=Bearer {creds.token}\x01\x01"

    mail = imaplib.IMAP4_SSL(server, port)
    try:
        mail.authenticate('XOAUTH2', lambda x: auth_string.encode('utf-8'))
    except Exception as exc:
        raise ConnectionError(f"Google OAuth2 authentication step rejected: {exc}")

    # Use the "Jobs" folder as requested
    folder = os.environ.get("IMAP_FOLDER", "Jobs")
    mail.select(f'"{folder}"')
    return mail

def _decode_header(raw_header: str) -> str:
    parts = email_lib.header.decode_header(raw_header or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)

def _extract_body(msg: email_lib.message.Message) -> str:
    plain_parts = []
    html_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = payload.decode(charset, errors="replace")
            if ct == "text/plain":
                plain_parts.append(text)
            elif ct == "text/html":
                html_parts.append(text)
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        text = payload.decode(charset, errors="replace") if payload else ""
        if msg.get_content_type() == "text/html":
            html_parts.append(text)
        else:
            plain_parts.append(text)

    if plain_parts:
        return "\n\n".join(plain_parts).strip()
    if html_parts:
        return _strip_html("\n".join(html_parts)).strip()
    return "(No readable body found)"

# ── Public API / Tools ────────────────────────────────────────────────────────
@tool
def fetch_email_by_uid(uid: str) -> Optional[str]:
    """Fetch a single email by IMAP UID and return it as a markdown string."""
    try:
        mail = _connect()
        status, data = mail.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            mail.logout()
            return None
        raw = data[0][1]
        msg = email_lib.message_from_bytes(raw)
        subject = _decode_header(msg.get("Subject", "(No Subject)"))
        sender = _decode_header(msg.get("From", "(Unknown)"))
        date = msg.get("Date", "")
        body = _extract_body(msg)
        mail.logout()

        md = (
            f"# {subject}\n\n"
            f"**From:** {sender} \n"
            f"**Date:** {date} \n"
            f"**UID:** {uid}\n\n"
            f"---\n\n"
            f"{body}"
        )
        return md
    except Exception as exc:
        return f"Exception while reading email UID {uid}: {exc}"

import json

@tool
def list_recent_emails(count: int = 5) -> str:
    """List recent emails from the mailbox."""
    try:
        mail = _connect()
        status, data = mail.uid("search", None, "ALL")
        if status != "OK":
            mail.logout()
            return []
        uids = data[0].split()
        recent_uids = uids[-count:][::-1]
        results = []
        for uid in recent_uids:
            uid_str = uid.decode()
            status, data = mail.uid("fetch", uid_str, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status != "OK" or not data or data[0] is None:
                continue
            msg = email_lib.message_from_bytes(data[0][1])
            results.append({
                "uid": uid_str,
                "subject": _decode_header(msg.get("Subject", "(No Subject)")),
                "sender": _decode_header(msg.get("From", "(Unknown)")),
                "date": msg.get("Date", ""),
            })
        mail.logout()
        return json.dumps(results)
    except Exception as exc:
        return json.dumps([{"error": f"Exception while listing emails: {exc}"}])

@tool
def search_emails(query: str, count: int = 5) -> str:
    """Search the mailbox using IMAP search syntax (e.g. SUBJECT "offer" or FROM "google"). Returns metadata of matching emails."""
    try:
        mail = _connect()
        status, data = mail.uid("search", None, query)
        if status != "OK":
            mail.logout()
            return []
        uids = data[0].split()
        recent_uids = uids[-count:][::-1]
        results = []
        for uid in recent_uids:
            uid_str = uid.decode()
            status, data = mail.uid("fetch", uid_str, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status != "OK" or not data or data[0] is None:
                continue
            msg = email_lib.message_from_bytes(data[0][1])
            results.append({
                "uid": uid_str,
                "subject": _decode_header(msg.get("Subject", "(No Subject)")),
                "sender": _decode_header(msg.get("From", "(Unknown)")),
                "date": msg.get("Date", ""),
            })
        mail.logout()
        return json.dumps(results)
    except Exception as exc:
        return json.dumps([{"error": f"Exception while searching emails: {exc}"}])
