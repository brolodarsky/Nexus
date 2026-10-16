"""
gmail_engine.py — Core Gmail REST API (v1) integration for Nexus Engine.

Provides deterministic Python functions to search, read, thread, label, archive, trash,
and draft Gmail messages using local OAuth credentials stored in .secrets/.

Standing Architectural Directives:
- Pure data access layer (No LangChain @tool decorators here; see agents/router/tools.py for an LLM wrapper).
- Uses token_gmail.json to isolate Gmail OAuth tokens from calendar tokens.
- Search uses native Gmail query syntax (e.g. 'from:recruiter newer_than:7d is:unread').
- No send function by design: outbound mail is drafted, then sent by a human (Playbook HITL).

Usage:
    python -m nexus.shared_tools.gmail_engine --auth
    python -m nexus.shared_tools.gmail_engine --list 10
    python -m nexus.shared_tools.gmail_engine --search "from:greenhouse.io newer_than:14d"
    python -m nexus.shared_tools.gmail_engine --read <MESSAGE_ID> [-o Vault/0. Inbox/email.md]
    python -m nexus.shared_tools.gmail_engine --thread <THREAD_ID>
    python -m nexus.shared_tools.gmail_engine --draft "to@x.com" "Subject" "Body" [--reply-to <MESSAGE_ID>]
"""

import argparse
import base64
import email as email_lib
import email.header
import html
import json
import re
import sys
from datetime import datetime
from email.message import EmailMessage
from html.parser import HTMLParser
from typing import Any, Optional

from googleapiclient.discovery import build, Resource

# Reconfigure stdout/stderr to UTF-8 on Windows so emoji-laden subjects don't crash cp1252 consoles
if sys.platform == "win32" and sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Nexus absolute imports
from nexus.core.constants import PROJECT_ROOT
from nexus.core.google_auth import get_google_credentials

# gmail.modify = read + labels + archive + trash + drafts. Excludes permanent delete (needs full mail.google.com scope).
GMAIL_SCOPES: list[str] = ["https://www.googleapis.com/auth/gmail.modify"]
SECRETS_DIR: str = str(PROJECT_ROOT / ".secrets")
TOKEN_FILENAME: str = "token_gmail.json"  # Separate cache: changing Gmail scopes never invalidates calendar auth
USER_ID: str = "me"  # Gmail API alias for "the authenticated account" (no EMAIL_ADDRESS env var needed)


# ── HTML → Markdown Stream Parser ─────────────────────────────────────────────
class HTMLToMarkdownParser(HTMLParser):
    """
    Robust stream parser converting raw email HTML into clean GitHub-flavored Markdown.
    
    Key mechanisms:
    1. Container Suppression: Skips non-visual blocks (<style>, <script>, <head>, <svg>, <noscript>).
    2. Link Preservation: Converts <a href="...">text</a> into [text](url) format.
    3. Structural Layout: Maps block tags (<p>, <div>, <tr>, <h1>-<h6>, <hr>, <li>) to markdown spacing.
    4. Inline Styles: Applies bold/italic formatting to text without producing empty asterisks (****).
    5. Entity Decoding: Unescapes HTML entities (&amp;, &nbsp;, &#39;) and normalizes inter-tag whitespace.
    """
    # Non-void container tags whose inner text/children should be completely discarded
    IGNORE_CONTAINER_TAGS = {"style", "script", "head", "svg", "noscript", "template"}

    def __init__(self):
        super().__init__()
        self.output: list[str] = []              # Accumulator for markdown tokens
        self._ignore_stack: list[str] = []       # Tracks active ignored container tags
        self._current_href: str | None = None    # Active hyperlink URL if inside an <a> tag
        self._link_text_acc: list[str] = []      # Buffer for text inside an <a> tag
        self._bold_depth: int = 0                # Nesting level for <b> and <strong> tags
        self._italic_depth: int = 0              # Nesting level for <i> and <em> tags

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag_lower = tag.lower()
        # Convert list of (name, value) tuples into a case-insensitive lookup dict
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        # 1. Ignore script/style/head container elements
        if tag_lower in self.IGNORE_CONTAINER_TAGS:
            self._ignore_stack.append(tag_lower)
            return

        if self._ignore_stack:
            return

        # 2. Block structural elements (ensure vertical separation)
        if tag_lower in ["p", "div", "section", "article", "tr"]:
            self.output.append("\n\n")
        elif tag_lower in ["td", "th"]:
            self.output.append("  ")             # Space separation for table cells
        elif tag_lower in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag_lower[1])
            self.output.append(f"\n\n{'#' * level} ")
        elif tag_lower == "br":
            self.output.append("\n")
        elif tag_lower == "hr":
            self.output.append("\n\n---\n\n")
        elif tag_lower == "li":
            self.output.append("\n- ")
        elif tag_lower in ["b", "strong"]:
            self._bold_depth += 1
        elif tag_lower in ["i", "em"]:
            self._italic_depth += 1
        elif tag_lower == "a":
            href = attr_dict.get("href", "").strip()
            # Ignore empty hrefs, internal hash anchors, and javascript: links
            if href and not href.startswith("javascript:") and not href.startswith("#"):
                self._current_href = href
                self._link_text_acc = []

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()

        # Handle container tag exit
        if self._ignore_stack:
            if tag_lower in self._ignore_stack:
                for i in range(len(self._ignore_stack) - 1, -1, -1):
                    if self._ignore_stack[i] == tag_lower:
                        self._ignore_stack.pop(i)
                        break
            return

        # Handle inline formatting close
        if tag_lower in ["b", "strong"]:
            if self._bold_depth > 0:
                self._bold_depth -= 1
        elif tag_lower in ["i", "em"]:
            if self._italic_depth > 0:
                self._italic_depth -= 1
        elif tag_lower == "a" and self._current_href is not None:
            raw_text = "".join(self._link_text_acc).strip()
            # Wrap link text in bold/italic if enclosed in formatting tags
            if self._bold_depth > 0 and raw_text:
                raw_text = f"**{raw_text}**"
            if self._italic_depth > 0 and raw_text:
                raw_text = f"*{raw_text}*"
            
            # Render as [text](url) or autolink <url> if no inner text
            if raw_text:
                self.output.append(f"[{raw_text}]({self._current_href})")
            else:
                self.output.append(f"<{self._current_href}>")
            self._current_href = None
            self._link_text_acc = []
        elif tag_lower in ["p", "div", "section", "article", "tr"]:
            self.output.append("\n\n")
        elif tag_lower in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            self.output.append("\n\n")

    def handle_data(self, data: str):
        if self._ignore_stack:
            return

        # Discard whitespace between HTML block tags
        if not data.strip():
            if self._current_href is not None:
                self._link_text_acc.append(" ")
            return

        # Decode HTML entities (e.g. &amp; -> &, &quot; -> ", &#39; -> ')
        unescaped = html.unescape(data)
        # Collapse internal runs of whitespace/tabs into a single space
        cleaned = re.sub(r'\s+', ' ', unescaped)

        if self._current_href is not None:
            self._link_text_acc.append(cleaned)
        else:
            text = cleaned
            if self._bold_depth > 0 and text.strip():
                text = f"**{text.strip()}** "
            elif self._italic_depth > 0 and text.strip():
                text = f"*{text.strip()}* "
            self.output.append(text)

    def get_markdown(self) -> str:
        """Collapse redundant vertical blank lines and strip trailing whitespace."""
        raw = "".join(self.output)
        lines = [l.strip() for l in raw.splitlines()]
        cleaned_lines: list[str] = []
        for line in lines:
            if line:
                cleaned_lines.append(line)
            # Allow at most one blank line between text blocks
            elif cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
        return "\n".join(cleaned_lines).strip()


def _html_to_markdown(html_content: str) -> str:
    """Helper converting raw HTML body into clean markdown."""
    parser = HTMLToMarkdownParser()
    parser.feed(html_content)
    return parser.get_markdown()


# ── MIME Helpers (shared by raw-message parsing) ──────────────────────────────
def _decode_header(raw_header: str) -> str:
    """Decodes MIME encoded header strings (RFC 2047) into Unicode strings."""
    # e.g. '=?UTF-8?B?8J+Ugg==?= Offer' -> '🔂 Offer'; returns list of (bytes|str, charset) tuples
    parts = email_lib.header.decode_header(raw_header or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded)


def _extract_body(msg: email_lib.message.Message) -> str:
    """
    Extracts and converts email content to markdown.
    Prioritizes rich HTML markdown conversion, falling back to clean plain text.
    Handles multipart/alternative and multipart/related MIME trees safely.
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        # .walk() is a generator: depth-first traversal of every nested MIME part
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)  # decode=True undoes base64/quoted-printable transfer encoding
            if payload is None:
                continue
            
            text = payload.decode(charset, errors="replace")
            # Only append if non-empty to prevent empty plain-text from masking HTML parts
            if ct == "text/plain" and text.strip():
                plain_parts.append(text.strip())
            elif ct == "text/html" and text.strip():
                html_parts.append(text.strip())
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        text = payload.decode(charset, errors="replace") if payload else ""
        if msg.get_content_type() == "text/html" and text.strip():
            html_parts.append(text.strip())
        elif text.strip():
            plain_parts.append(text.strip())

    # 1. Prefer rich HTML converted to link-preserving Markdown
    if html_parts:
        converted = [_html_to_markdown(h) for h in html_parts if h]
        combined = "\n\n---\n\n".join([c for c in converted if c])
        if combined.strip():
            return combined

    # 2. Fall back to plain text parts
    if plain_parts:
        return "\n\n".join(plain_parts).strip()

    return "(No readable body found)"


def _list_attachments(msg: email_lib.message.Message) -> list[str]:
    """Return filenames of attachment parts (metadata only; bytes are not downloaded to the agent)."""
    names: list[str] = []
    for part in msg.walk():
        filename = part.get_filename()
        if filename:
            names.append(_decode_header(filename))
    return names


def _header_map(payload: dict[str, Any]) -> dict[str, str]:
    """Flatten Gmail's [{'name': 'From', 'value': '...'}] header list into a {'from': '...'} dict."""
    # Dict comprehension; lowercase keys because header names are case-insensitive per RFC 5322
    return {h["name"].lower(): h["value"] for h in payload.get("headers", [])}


def _internal_date_iso(internal_date_ms: Optional[str]) -> str:
    """Convert Gmail's internalDate (epoch milliseconds as a string) into a local ISO-8601 timestamp."""
    if not internal_date_ms:
        return ""
    # / 1000: ms -> seconds; .astimezone() attaches the machine's local tz (e.g. -04:00)
    return datetime.fromtimestamp(int(internal_date_ms) / 1000).astimezone().isoformat(timespec="seconds")


def _summarize(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a messages.get(format='metadata') resource into Nexus's lightweight summary shape."""
    headers = _header_map(raw.get("payload", {}))
    return {
        "id": raw.get("id"),
        "thread_id": raw.get("threadId"),
        "date": _internal_date_iso(raw.get("internalDate")),
        "sender": headers.get("from", "(Unknown)"),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", "(No Subject)"),
        "snippet": html.unescape(raw.get("snippet", "")),  # Gmail returns snippets HTML-escaped (&#39; etc.)
        "labels": raw.get("labelIds", []),
    }


# ── Service ───────────────────────────────────────────────────────────────────
def get_gmail_service() -> Resource:
    """
    Authenticate and build the Gmail API v1 Resource client.

    Returns:
        googleapiclient.discovery.Resource: Authorized Gmail API v1 service instance.
    """
    # 1. Retrieve or refresh credentials via isolated token file (browser consent on first run)
    creds = get_google_credentials(
        scopes=GMAIL_SCOPES,
        secrets_dir=SECRETS_DIR,
        token_filename=TOKEN_FILENAME,
    )
    # 2. Build the discovery client; cache_discovery=False silences the oauth2client file-cache warning
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ── Read Operations ───────────────────────────────────────────────────────────
def list_messages(
    query: str = "in:inbox",
    max_results: int = 10,
    service: Optional[Resource] = None,
) -> list[dict[str, Any]]:
    """
    Search messages with native Gmail query syntax and return lightweight summaries (newest first).

    Args:
        query: Gmail search string, identical to the Gmail search bar
               (e.g. 'from:openai.com', 'subject:interview newer_than:30d', 'is:unread label:Jobs').
        max_results: Max messages to return (clamped 1–100).
        service: Optional pre-built client (reuse across calls to skip re-auth).

    Returns:
        list[dict]: Summaries with id, thread_id, date, sender, to, subject, snippet, labels.
    """
    service = service or get_gmail_service()
    max_results = max(1, min(max_results, 100))

    # Step 1: messages.list returns ONLY {id, threadId} stubs, never headers
    resp = service.users().messages().list(userId=USER_ID, q=query, maxResults=max_results).execute()
    stubs = resp.get("messages", [])
    if not stubs:
        return []

    # Step 2: hydrate headers for every stub in ONE HTTP round-trip via a batch request (avoids N+1 calls)
    results_by_id: dict[str, dict[str, Any]] = {}

    def _on_response(request_id: str, response: dict, exception: Exception | None) -> None:
        # Batch callback signature fixed by googleapiclient: (request_id, response, exception)
        if exception is None and response:
            results_by_id[response["id"]] = _summarize(response)

    batch = service.new_batch_http_request(callback=_on_response)
    for stub in stubs:
        batch.add(
            service.users().messages().get(
                userId=USER_ID,
                id=stub["id"],
                format="metadata",  # headers + snippet only; skips body bytes
                metadataHeaders=["From", "To", "Subject", "Date"],
            )
        )
    batch.execute()

    # Preserve Gmail's original (newest-first) ordering; batch responses may arrive out of order
    return [results_by_id[s["id"]] for s in stubs if s["id"] in results_by_id]


def get_message(message_id: str, service: Optional[Resource] = None) -> dict[str, Any]:
    """
    Fetch a full message and convert its body into clean markdown.

    Args:
        message_id: Gmail message ID (hex string from list_messages, e.g. '18f2a9c3d4e5b6a7').

    Returns:
        dict: id, thread_id, date, sender, to, cc, subject, labels, attachments, body (markdown).
    """
    service = service or get_gmail_service()
    # format='raw' returns the entire RFC 822 message as base64url, so stdlib `email` can parse any MIME tree
    raw = service.users().messages().get(userId=USER_ID, id=message_id, format="raw").execute()
    msg = email_lib.message_from_bytes(base64.urlsafe_b64decode(raw["raw"]))

    return {
        "id": raw.get("id"),
        "thread_id": raw.get("threadId"),
        "date": _internal_date_iso(raw.get("internalDate")),
        "sender": _decode_header(msg.get("From", "(Unknown)")),
        "to": _decode_header(msg.get("To", "")),
        "cc": _decode_header(msg.get("Cc", "")),
        "subject": _decode_header(msg.get("Subject", "(No Subject)")),
        "message_id_header": msg.get("Message-ID", ""),  # RFC 5322 ID; needed for reply threading
        "labels": raw.get("labelIds", []),
        "attachments": _list_attachments(msg),
        "body": _extract_body(msg),
    }


def get_thread(thread_id: str, service: Optional[Resource] = None) -> list[dict[str, Any]]:
    """
    Fetch every message in a conversation thread (oldest first), each with a markdown body.

    Args:
        thread_id: Gmail thread ID (the 'thread_id' field from list_messages/get_message).
    """
    service = service or get_gmail_service()
    # threads.get has no 'raw' format, so grab IDs cheaply ('minimal') then reuse get_message's MIME parser
    thread = service.users().threads().get(userId=USER_ID, id=thread_id, format="minimal").execute()
    return [get_message(m["id"], service=service) for m in thread.get("messages", [])]


def list_labels(service: Optional[Resource] = None) -> list[dict[str, str]]:
    """Return all labels as [{'id': 'Label_12', 'name': 'Jobs', 'type': 'user'}, ...]."""
    service = service or get_gmail_service()
    labels = service.users().labels().list(userId=USER_ID).execute().get("labels", [])
    return [{"id": l["id"], "name": l["name"], "type": l.get("type", "")} for l in labels]


# ── Write Operations (HITL: confirm with the user before calling) ─────────────
def _resolve_label_ids(names: list[str], service: Resource) -> list[str]:
    """Map human label names ('Jobs', 'UNREAD') to Gmail label IDs ('Label_12', 'UNREAD')."""
    lookup = {l["name"].lower(): l["id"] for l in list_labels(service)}
    resolved: list[str] = []
    for name in names:
        label_id = lookup.get(name.lower())
        if not label_id:
            raise ValueError(f"Unknown Gmail label: '{name}'. Run --labels to see valid names.")
        resolved.append(label_id)
    return resolved


def modify_labels(
    message_id: str,
    add: Optional[list[str]] = None,
    remove: Optional[list[str]] = None,
    service: Optional[Resource] = None,
) -> list[str]:
    """
    Add/remove labels on a message by label NAME. System labels work too
    (e.g. remove=['INBOX'] archives, remove=['UNREAD'] marks read, add=['STARRED'] stars).

    Returns:
        list[str]: The message's label IDs after modification.
    """
    service = service or get_gmail_service()
    body = {
        "addLabelIds": _resolve_label_ids(add or [], service),
        "removeLabelIds": _resolve_label_ids(remove or [], service),
    }
    res = service.users().messages().modify(userId=USER_ID, id=message_id, body=body).execute()
    return res.get("labelIds", [])


def archive_message(message_id: str, service: Optional[Resource] = None) -> list[str]:
    """Archive = remove the INBOX label (message stays searchable under All Mail)."""
    return modify_labels(message_id, remove=["INBOX"], service=service)


def mark_read(message_id: str, service: Optional[Resource] = None) -> list[str]:
    """Mark as read = remove the UNREAD system label."""
    return modify_labels(message_id, remove=["UNREAD"], service=service)


def trash_message(message_id: str, service: Optional[Resource] = None) -> bool:
    """Move a message to Trash (Gmail auto-purges after 30 days; recoverable until then)."""
    service = service or get_gmail_service()
    service.users().messages().trash(userId=USER_ID, id=message_id).execute()
    return True


def create_draft(
    to: str,
    subject: str,
    body: str,
    reply_to_message_id: Optional[str] = None,
    service: Optional[Resource] = None,
) -> dict[str, Any]:
    """
    Create a Gmail draft (never sends). The user reviews and hits Send in Gmail.

    Args:
        to: Recipient address(es), comma-separated.
        subject: Subject line ('Re: ' is auto-prefixed for replies if missing).
        body: Plain-text body.
        reply_to_message_id: Optional Gmail message ID to reply to; threads the draft into that conversation.

    Returns:
        dict: draft_id, message_id, thread_id.
    """
    service = service or get_gmail_service()
    mime = EmailMessage()  # Modern stdlib MIME builder (handles UTF-8 headers/body encoding for us)
    mime["To"] = to
    mime.set_content(body)

    thread_id: Optional[str] = None
    if reply_to_message_id:
        # Reply threading needs BOTH Gmail's threadId AND RFC 5322 In-Reply-To/References headers
        original = get_message(reply_to_message_id, service=service)
        thread_id = original["thread_id"]
        if original["message_id_header"]:
            mime["In-Reply-To"] = original["message_id_header"]
            mime["References"] = original["message_id_header"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject or original['subject']}"
    mime["Subject"] = subject

    # Gmail expects the full RFC 822 bytes as base64url text in the 'raw' field
    message_body: dict[str, Any] = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}
    if thread_id:
        message_body["threadId"] = thread_id

    draft = service.users().drafts().create(userId=USER_ID, body={"message": message_body}).execute()
    return {
        "draft_id": draft.get("id"),
        "message_id": draft.get("message", {}).get("id"),
        "thread_id": draft.get("message", {}).get("threadId"),
    }


# ── Formatting ────────────────────────────────────────────────────────────────
def message_to_markdown(msg: dict[str, Any]) -> str:
    """Render a get_message() dict as a Vault-ready markdown block."""
    attachments = ", ".join(msg.get("attachments", [])) or "None"
    cc_line = f"**Cc:** {msg['cc']}  \n" if msg.get("cc") else ""
    return (
        f"# {msg['subject']}\n\n"
        f"**From:** {msg['sender']}  \n"
        f"**To:** {msg['to']}  \n"
        f"{cc_line}"
        f"**Date:** {msg['date']}  \n"
        f"**Gmail ID:** {msg['id']} (thread {msg['thread_id']})  \n"
        f"**Attachments:** {attachments}\n\n"
        f"---\n\n"
        f"{msg['body']}"
    )


def format_messages_table(messages: list[dict[str, Any]]) -> str:
    """Fixed-width terminal table of message summaries."""
    if not messages:
        return "No messages found."
    col_sender_w, col_subj_w = 32, 60
    lines = [f"{'ID':<18} {'Date':<26} {'From':<{col_sender_w}} Subject", "-" * 140]
    for m in messages:
        # Truncate long fields with an ellipsis so columns stay aligned
        sender = m["sender"][:col_sender_w] + ("…" if len(m["sender"]) > col_sender_w else "")
        subject = m["subject"][:col_subj_w] + ("…" if len(m["subject"]) > col_subj_w else "")
        lines.append(f"{m['id']:<18} {m['date']:<26} {sender:<{col_sender_w}} {subject}")
    return "\n".join(lines)


# ── Interactive CLI Entrypoint ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Gmail REST API (v1) CLI for Nexus Engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m nexus.shared_tools.gmail_engine --auth\n"
            "  python -m nexus.shared_tools.gmail_engine --list 10\n"
            "  python -m nexus.shared_tools.gmail_engine --search \"from:greenhouse.io newer_than:14d\" --json\n"
            "  python -m nexus.shared_tools.gmail_engine --read 18f2a9c3d4e5b6a7 -o \"Vault/0. Inbox/lead.md\"\n"
            "  python -m nexus.shared_tools.gmail_engine --draft \"a@b.com\" \"Hello\" \"Body\" --reply-to 18f2a9c3d4e5b6a7\n"
            "  python -m nexus.shared_tools.gmail_engine --modify 18f2a9c3d4e5b6a7 --add Jobs --remove INBOX\n"
        ),
    )
    # Read
    parser.add_argument("--auth", action="store_true", help="Run the one-time OAuth browser consent")
    parser.add_argument("--list", metavar="N", type=int, help="List the N most recent inbox messages")
    parser.add_argument("--search", metavar="QUERY", help="Search with Gmail syntax (from:, subject:, newer_than:, is:unread)")
    parser.add_argument("--max", type=int, default=10, help="Max results for --search (default: 10)")
    parser.add_argument("--read", metavar="MESSAGE_ID", help="Print a full message as markdown")
    parser.add_argument("--thread", metavar="THREAD_ID", help="Print every message in a thread as markdown")
    parser.add_argument("--labels", action="store_true", help="List all label names and IDs")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of tables/markdown")
    parser.add_argument("-o", "--output", help="Save --read/--thread markdown to this path")
    # Write (HITL)
    parser.add_argument("--draft", nargs=3, metavar=("TO", "SUBJECT", "BODY"), help="Create a draft (never sends)")
    parser.add_argument("--reply-to", metavar="MESSAGE_ID", help="Thread the --draft as a reply to this message")
    parser.add_argument("--modify", metavar="MESSAGE_ID", help="Change labels on a message (use with --add/--remove)")
    parser.add_argument("--add", nargs="*", default=[], help="Label names to add (with --modify)")
    parser.add_argument("--remove", nargs="*", default=[], help="Label names to remove (with --modify)")
    parser.add_argument("--archive", metavar="MESSAGE_ID", help="Archive a message (remove INBOX)")
    parser.add_argument("--mark-read", metavar="MESSAGE_ID", help="Mark a message as read")
    parser.add_argument("--trash", metavar="MESSAGE_ID", help="Move a message to Trash")
    args = parser.parse_args()

    def _emit(text: str) -> None:
        # Write markdown to disk when -o is given, otherwise stream to stdout
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"[Nexus] Saved to {args.output}", file=sys.stderr)
        else:
            print(text)

    if args.auth:
        get_gmail_service()
        print(f"[Nexus] Gmail authentication successful. Token stored at .secrets/{TOKEN_FILENAME}")
        return

    if args.list or args.search:
        query = args.search or "in:inbox"
        count = args.list or args.max
        msgs = list_messages(query=query, max_results=count)
        print(json.dumps(msgs, indent=2, ensure_ascii=False) if args.json else format_messages_table(msgs))
        return

    if args.read:
        msg = get_message(args.read)
        _emit(json.dumps(msg, indent=2, ensure_ascii=False) if args.json else message_to_markdown(msg))
        return

    if args.thread:
        msgs = get_thread(args.thread)
        if args.json:
            _emit(json.dumps(msgs, indent=2, ensure_ascii=False))
        else:
            _emit("\n\n---\n\n".join(message_to_markdown(m) for m in msgs))
        return

    if args.labels:
        for l in list_labels():
            print(f"{l['id']:<24} {l['type']:<8} {l['name']}")
        return

    if args.draft:
        to, subject, body = args.draft
        res = create_draft(to=to, subject=subject, body=body, reply_to_message_id=args.reply_to)
        print(f"[Nexus] Draft created (draft {res['draft_id']}, thread {res['thread_id']}). Review and send in Gmail.")
        return

    if args.modify:
        labels = modify_labels(args.modify, add=args.add, remove=args.remove)
        print(f"[Nexus] Labels now: {', '.join(labels)}")
        return

    if args.archive:
        archive_message(args.archive)
        print(f"[Nexus] Archived {args.archive}.")
        return

    if args.mark_read:
        mark_read(args.mark_read)
        print(f"[Nexus] Marked {args.mark_read} as read.")
        return

    if args.trash:
        trash_message(args.trash)
        print(f"[Nexus] Moved {args.trash} to Trash (recoverable for 30 days).")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
