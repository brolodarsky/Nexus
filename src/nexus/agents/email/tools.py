"""
tools.py — Core email fetching and parsing logic for the Nexus Engine's Email Agent.
Provides functions to connect to IMAP mailboxes, search emails, batch-fetch headers,
and convert rich multipart HTML emails into clean, link-preserving Markdown.
"""
import imaplib
import email as email_lib
import email.header
import html
import json
import os
import re
import sys
from html.parser import HTMLParser
from typing import Optional
from langchain_core.tools import tool

# Engine configurations & OAuth provider
from nexus.core.google_auth import get_google_credentials
from nexus.core.config import settings
from nexus.core.constants import PROJECT_ROOT

# Full IMAP permissions scope for Google Accounts
SCOPES = ['https://mail.google.com/']
SECRETS_DIR = str(PROJECT_ROOT / ".secrets")


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


# ── IMAP Helpers ──────────────────────────────────────────────────────────────
def _connect() -> imaplib.IMAP4_SSL:
    """Establish and authenticate a TLS connection to the IMAP server via OAuth2 XOAUTH2."""
    server = settings.imap_server
    port = settings.imap_port
    address = settings.email_address

    if not address:
        raise ValueError("EMAIL_ADDRESS environment variable must be set.")

    creds = get_google_credentials(SCOPES, SECRETS_DIR)
    auth_string = f"user={address}\x01auth=Bearer {creds.token}\x01\x01"

    mail = imaplib.IMAP4_SSL(server, port)
    try:
        mail.authenticate('XOAUTH2', lambda x: auth_string.encode('utf-8'))
    except Exception as exc:
        raise ConnectionError(f"Google OAuth2 authentication step rejected: {exc}")

    # Select mailbox folder (e.g. INBOX)
    folder = settings.imap_folder
    mail.select(f'"{folder}"')
    return mail


def _decode_header(raw_header: str) -> str:
    """Decodes MIME encoded header strings (RFC 2047) into Unicode strings."""
    parts = email_lib.header.decode_header(raw_header or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded)


def _build_imap_query(query: str) -> str:
    """
    Translates natural language or freeform terms into valid RFC-3501 IMAP search strings.
    If standard IMAP operators (e.g. FROM, SUBJECT, TEXT, OR) are detected, returns as-is.
    """
    q = query.strip()
    if not q:
        return "ALL"
    
    imap_keywords = {"ALL", "FROM", "TO", "SUBJECT", "BODY", "TEXT", "SINCE", "BEFORE", "UNSEEN", "SEEN", "FLAGGED", "OR", "NOT"}
    first_token = q.split()[0].upper() if q.split() else ""
    if first_token in imap_keywords:
        return q
    
    # Wrap natural text into a composite search covering sender, subject, and body text
    escaped_term = q.replace('"', '\\"')
    return f'(OR (FROM "{escaped_term}") (OR (SUBJECT "{escaped_term}") (TEXT "{escaped_term}")))'


def _fetch_headers_batch(mail: imaplib.IMAP4_SSL, uids: list[str]) -> list[dict]:
    """
    Batch-fetches headers (FROM, SUBJECT, DATE) for multiple UIDs in a SINGLE network round-trip.
    Replaces N+1 sequential fetches with a single RFC-3501 UID command.
    """
    if not uids:
        return []
    
    # Comma-separated UID set for batch fetch
    uid_set = ",".join(uids)
    status, data = mail.uid("fetch", uid_set, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] UID)")
    if status != "OK" or not data:
        return []

    meta_by_uid = {}
    for item in data:
        if isinstance(item, tuple) and len(item) == 2:
            desc = item[0].decode("utf-8", errors="replace")
            # Parse the UID returned in the IMAP response header
            uid_match = re.search(r'UID\s+(\d+)', desc)
            if uid_match:
                uid_str = uid_match.group(1)
                msg = email_lib.message_from_bytes(item[1])
                meta_by_uid[uid_str] = {
                    "uid": uid_str,
                    "subject": _decode_header(msg.get("Subject", "(No Subject)")),
                    "sender": _decode_header(msg.get("From", "(Unknown)")),
                    "date": msg.get("Date", ""),
                }

    # Return items maintaining the input UID order
    return [meta_by_uid[uid] for uid in uids if uid in meta_by_uid]


def _extract_body(msg: email_lib.message.Message) -> str:
    """
    Extracts and converts email content to markdown.
    Prioritizes rich HTML markdown conversion, falling back to clean plain text.
    Handles multipart/alternative and multipart/related MIME trees safely.
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []

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


# ── Public Tools ──────────────────────────────────────────────────────────────
@tool
def fetch_email_by_uid(uid: str) -> Optional[str]:
    """Fetch a single email by IMAP UID and return its full content as clean markdown."""
    try:
        mail = _connect()
        status, data = mail.uid("fetch", uid, "(RFC822)")
        if status != "OK" or not data or data[0] is None:
            mail.logout()
            return f"Error: Email UID {uid} not found."
        
        raw = data[0][1]
        msg = email_lib.message_from_bytes(raw)
        subject = _decode_header(msg.get("Subject", "(No Subject)"))
        sender = _decode_header(msg.get("From", "(Unknown)"))
        date = msg.get("Date", "")
        body = _extract_body(msg)
        mail.logout()

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
        return f"Exception while reading email UID {uid}: {exc}"


@tool
def list_recent_emails(count: int = 5) -> str:
    """List metadata for the N most recent emails in the mailbox in a single batch call."""
    try:
        mail = _connect()
        status, data = mail.uid("search", None, "ALL")
        if status != "OK" or not data or not data[0]:
            mail.logout()
            return json.dumps([])
        
        all_uids = [u.decode() for u in data[0].split()]
        recent_uids = all_uids[-count:][::-1]  # Newest first
        
        # Batch fetch all headers in one round trip
        results = _fetch_headers_batch(mail, recent_uids)
        mail.logout()
        return json.dumps(results)
    except Exception as exc:
        return json.dumps([{"error": f"Exception while listing emails: {exc}"}])


@tool
def search_emails(query: str, count: int = 5) -> str:
    """
    Search mailbox emails by sender, subject, or content.
    Accepts natural terms (e.g. 'palantir', 'interview offer') or IMAP syntax (e.g. FROM 'google').
    Returns a JSON string list of matching email metadata objects.
    """
    try:
        mail = _connect()
        imap_query = _build_imap_query(query)
        status, data = mail.uid("search", None, imap_query)
        
        # If composite query returned no matches, try broad TEXT search as fallback
        if (status != "OK" or not data or not data[0]) and not query.strip().startswith(("FROM", "SUBJECT", "TEXT", "ALL")):
            escaped = query.strip().replace('"', '\\"')
            status, data = mail.uid("search", None, f'TEXT "{escaped}"')
            
        if status != "OK" or not data or not data[0]:
            mail.logout()
            return json.dumps([])
            
        all_uids = [u.decode() for u in data[0].split()]
        recent_uids = all_uids[-count:][::-1]  # Newest first
        
        # Batch fetch all matching headers in one round trip
        results = _fetch_headers_batch(mail, recent_uids)
        mail.logout()
        return json.dumps(results)
    except Exception as exc:
        return json.dumps([{"error": f"Exception while searching emails: {exc}"}])

