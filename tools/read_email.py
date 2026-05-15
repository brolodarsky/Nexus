"""
read_email.py — Lightweight IMAP email reader for Brain 2 Engine.

Fetches a single email by UID from a configured IMAP mailbox and
returns its content as clean markdown — analogous to read_webpage.py.

Usage:
    python tools/read_email.py <UID>
    python tools/read_email.py <UID> -o Vault/Inbox/email_note.md
    python tools/read_email.py --list-recent 10

Environment variables (recommended: store in a .env file):
    EMAIL_ADDRESS   — your email address (e.g. you@gmail.com)
    EMAIL_PASSWORD  — app password (NOT your main password; use an App Password for Gmail)
    IMAP_SERVER     — IMAP host (default: imap.gmail.com)
    IMAP_PORT       — IMAP port (default: 993)
    IMAP_FOLDER     — Mailbox folder to read from (default: INBOX)

Gmail setup: Settings → Security → 2FA → App Passwords → generate one for "Brain 2".
"""

import imaplib
import email as email_lib
import email.header
import os
import sys
import argparse
from datetime import datetime
from typing import Optional
from html.parser import HTMLParser

# ── Dependency: python-dotenv (soft) ─────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env loading is optional; env vars can be set manually


# ── HTML → plain text stripper ────────────────────────────────────────────────
class _HTMLStripper(HTMLParser):
    """Minimal HTML → plain text converter. No external deps."""
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
    port   = int(os.environ.get("IMAP_PORT", 993))
    address  = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("EMAIL_PASSWORD")

    if not address or not password:
        print(
            "Error: EMAIL_ADDRESS and EMAIL_PASSWORD environment variables must be set.\n"
            "  Tip: create a .env file in the project root with those values.\n"
            "  For Gmail, generate an App Password at myaccount.google.com/apppasswords.",
            file=sys.stderr,
        )
        sys.exit(1)

    mail = imaplib.IMAP4_SSL(server, port)
    mail.login(address, password)
    folder = os.environ.get("IMAP_FOLDER", "INBOX")
    mail.select(f'"{folder}"')
    return mail


def _decode_header(raw_header: str) -> str:
    """Decode RFC-2047 encoded email header values."""
    parts = email.header.decode_header(raw_header or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _extract_body(msg: email_lib.message.Message) -> str:
    """Walk the MIME tree and return the best plain-text body available."""
    plain_parts = []
    html_parts  = []

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


# ── Public API ────────────────────────────────────────────────────────────────
def fetch_email_by_uid(uid: str) -> Optional[str]:
    """
    Fetch a single email by IMAP UID and return it as a markdown string.
    Returns None on failure.
    """
    try:
        mail = _connect()
        status, data = mail.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            print(f"Error: Could not fetch UID {uid}. Check that the UID exists in the configured folder.", file=sys.stderr)
            mail.logout()
            return None

        raw = data[0][1]
        msg = email_lib.message_from_bytes(raw)

        subject = _decode_header(msg.get("Subject", "(No Subject)"))
        sender  = _decode_header(msg.get("From", "(Unknown)"))
        date    = msg.get("Date", "")
        body    = _extract_body(msg)

        mail.logout()

        # Format as a clean markdown block
        md = (
            f"# {subject}\n\n"
            f"**From:** {sender}  \n"
            f"**Date:** {date}  \n"
            f"**UID:** {uid}\n\n"
            f"---\n\n"
            f"{body}"
        )
        return md

    except Exception as exc:
        print(f"Exception while reading email UID {uid}: {exc}", file=sys.stderr)
        return None


def list_recent_emails(count: int = 10) -> list[dict]:
    """
    List the most recent `count` emails. Returns a list of dicts with
    keys: uid, subject, sender, date.
    """
    try:
        mail = _connect()
        status, data = mail.uid("search", None, "ALL")
        if status != "OK":
            mail.logout()
            return []

        uids = data[0].split()
        recent_uids = uids[-count:][::-1]  # newest first

        results = []
        for uid in recent_uids:
            uid_str = uid.decode()
            status, data = mail.uid("fetch", uid_str, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status != "OK" or not data or data[0] is None:
                continue
            msg = email_lib.message_from_bytes(data[0][1])
            results.append({
                "uid":     uid_str,
                "subject": _decode_header(msg.get("Subject", "(No Subject)")),
                "sender":  _decode_header(msg.get("From", "(Unknown)")),
                "date":    msg.get("Date", ""),
            })

        mail.logout()
        return results

    except Exception as exc:
        print(f"Exception while listing emails: {exc}", file=sys.stderr)
        return []


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Lightweight IMAP email reader for Brain 2 Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python tools/read_email.py 4821\n"
            "  python tools/read_email.py 4821 -o Vault/Inbox/job_lead.md\n"
            "  python tools/read_email.py --list-recent 5\n"
        ),
    )
    parser.add_argument("uid", nargs="?", help="IMAP UID of the email to fetch")
    parser.add_argument("-o", "--output", help="Path to save the markdown output (optional)")
    parser.add_argument(
        "--list-recent",
        metavar="N",
        type=int,
        help="List the N most recent emails (shows UID, subject, sender, date)",
    )

    args = parser.parse_args()

    # ── List mode ──────────────────────────────────────────────────────────
    if args.list_recent:
        emails = list_recent_emails(args.list_recent)
        if not emails:
            print("No emails found or connection failed.", file=sys.stderr)
            sys.exit(1)
        col_w = 60
        print(f"{'UID':<8} {'Date':<32} {'From':<35} Subject")
        print("-" * 140)
        for e in emails:
            subj = e["subject"][:col_w] + ("…" if len(e["subject"]) > col_w else "")
            print(f"{e['uid']:<8} {e['date']:<32} {e['sender'][:35]:<35} {subj}")
        return

    # ── Fetch mode ─────────────────────────────────────────────────────────
    if not args.uid:
        parser.print_help()
        sys.exit(1)

    content = fetch_email_by_uid(args.uid)

    if content:
        if args.output:
            os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Saved email UID {args.uid} → {args.output}")
        else:
            if sys.stdout.encoding != "utf-8":
                sys.stdout.reconfigure(encoding="utf-8")
            print(content)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
