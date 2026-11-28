"""
conversation_cache.py — Universal Per-Conversation External Capture Cache for Nexus.

Solves cross-turn and subagent external capture amnesia without vendor-specific regexes or
global flat JSON files:
  - Stores verbatim raw captures (`read_browser_tabs`, `read_webpage`, `fetch_emails`) in
    SQLite WAL (`conversation_captures` table in `logs/chats.db`) scoped by `conversation_id`.
  - Exposes short, deterministic human-readable handles (`cache://tab/<slug>`, `cache://web/<slug>`,
    `cache://email/<id>`) that survive across turns, subagent boundaries, and conversation forks.
  - Propagates cleanly across `fork_conversation` / `spawn_seeded_conversation` and purges
    automatically inside `chats_db.delete_conversation()`.
"""

from datetime import datetime, timezone
import os
import re
import sqlite3
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from nexus.core import chats_db
from nexus.core.hitl_queue import get_hitl_execution_context

DEFAULT_CONVERSATION_ID = "nexus_primary"
CACHE_SCHEME = "cache://"
# Minimum character length for surfacing fenced code/draft blocks in `cache://chat` manifests
CHAT_BLOCK_MIN_CHARS = 200
# Matches canonical `chat/m<message_id>-b<block_index>` keys (with `cache://` stripped)
_CHAT_KEY_RE = re.compile(r"^chat/m(\d+)-b(\d+)$", re.IGNORECASE)
# CommonMark fenced code block opener (`>=3` backticks or tildes with optional leading indent <= 3)
_FENCE_OPEN_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})([^\r\n]*)$")

# Universal analytics/tracking query parameter prefixes & names stripped during URL normalization.
# Zero site-specific or ATS-specific regexes: strictly standard web tracking parameters.
_TRACKING_QUERY_PREFIXES = ("utm_", "trk")
_TRACKING_QUERY_PARAMS = frozenset({
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "_gl",
    "_ga",
    "_gac",
    "gh_src",
    "alid",
    "xpse",
    "xfps",
    "rgtk",
    "xkcb",
    "from_page",
    "apppublicid",
    "igshid",
    "yclid",
    "ref_src",
})


def _ensure_table(conn: sqlite3.Connection) -> None:
    """Idempotently creates the `conversation_captures` table and lookup indexes on `conn`."""
    # Note: No FOREIGN KEY on conversations(id) because headless CLI/eval runs default to
    # `conversation_id="nexus_primary"` (which has no conversations row); lifecycle cleanup
    # runs explicitly inside `chats_db.delete_conversation()` in the same transaction.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            cache_key TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_url TEXT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(conversation_id, cache_key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conv_captures_conv_id ON conversation_captures (conversation_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conv_captures_conv_url ON conversation_captures (conversation_id, source_url)"
    )


def init_cache_table() -> None:
    """Initializes the `conversation_captures` table in `chats.db`."""
    with chats_db._get_conn() as conn:
        _ensure_table(conn)


def get_active_conversation_id() -> str:
    """Resolves the active `conversation_id` from HITL ContextVar, CLI subprocess env, or CLI fallback.

    Order of precedence:
      1. `get_hitl_execution_context().get("conversation_id")` (set per turn, subagent, or MCP session)
      2. `os.environ.get("NEXUS_CONVERSATION_ID")` (explicit CLI subprocess override)
      3. `DEFAULT_CONVERSATION_ID` (`"nexus_primary"`) for standalone CLI/eval executions
    """
    ctx = get_hitl_execution_context()
    ctx_convo = (ctx.get("conversation_id") or "").strip()
    if ctx_convo:
        return ctx_convo
    env_convo = (os.environ.get("NEXUS_CONVERSATION_ID") or "").strip()
    if env_convo:
        return env_convo
    return DEFAULT_CONVERSATION_ID


def normalize_capture_url(url: Optional[str]) -> Optional[str]:
    """Canonicalizes an external URL universally by stripping fragments and analytics tracking query params."""
    cleaned = (url or "").strip()
    if not cleaned:
        return None

    parts = urlsplit(cleaned)
    if not parts.scheme or not parts.netloc:
        return cleaned

    clean_path = parts.path.rstrip("/")
    kept_params = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith(_TRACKING_QUERY_PREFIXES)
        and k.lower() not in _TRACKING_QUERY_PARAMS
    )
    clean_query = urlencode(kept_params, doseq=True)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), clean_path, clean_query, ""))


def is_cache_ref(ref: Optional[str]) -> bool:
    """Returns True when `ref` explicitly uses the `cache://` capture scheme."""
    return (ref or "").strip().lower().startswith(CACHE_SCHEME)


def normalize_cache_key(ref: str, default_source_type: Optional[str] = None) -> str:
    """Normalizes a cache reference (with or without `cache://` prefix) into canonical `cache://...` form."""
    cleaned = (ref or "").strip()
    if not cleaned:
        return CACHE_SCHEME
    if cleaned.lower().startswith(CACHE_SCHEME):
        body = cleaned[len(CACHE_SCHEME) :].strip("/")
        return f"{CACHE_SCHEME}{body}"
    body = cleaned.strip("/")
    if "/" in body:
        return f"{CACHE_SCHEME}{body}"
    if default_source_type:
        clean_type = re.sub(r"[^a-z0-9_-]+", "", default_source_type.strip().lower()) or "capture"
        return f"{CACHE_SCHEME}{clean_type}/{body}"
    return f"{CACHE_SCHEME}{body}"


def make_capture_slug(title: str, source_url: Optional[str] = None, max_len: int = 48) -> str:
    """Generates a short, lowercase URL-safe slug from `title` (or `source_url` fallback)."""
    raw_seed = (title or "").strip()
    if not raw_seed and source_url:
        parts = urlsplit(source_url)
        raw_seed = f"{parts.netloc}-{parts.path}".strip("-")
    slug = re.sub(r"[^a-z0-9]+", "-", raw_seed.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "item"


# `conversation_id`: Active conversation scope (defaults via `get_active_conversation_id()` if None).
# `source_type`: Category token used in generated `cache://<source_type>/<slug>` handles (`"tab"`, `"web"`, `"email"`).
# `title`: Human-readable capture title used in manifests and slug generation.
# `content`: Unabridged verbatim capture text (Markdown or plain text).
# `source_url`: Optional origin URL (normalized before matching/storing).
# `cache_key`: Optional explicit key override (e.g. `"cache://email/<msg_id>"`).
# `-> str`: Returns the canonical `cache://...` handle assigned to this capture.
def put_capture(
    conversation_id: Optional[str],
    source_type: str,
    title: str,
    content: str,
    source_url: Optional[str] = None,
    cache_key: Optional[str] = None,
) -> str:
    """Stores or upserts an external capture in SQLite scoped strictly to `conversation_id`."""
    convo_id = (conversation_id or "").strip() or get_active_conversation_id()
    src_type = re.sub(r"[^a-z0-9_-]+", "", (source_type or "").strip().lower()) or "capture"
    norm_url = normalize_capture_url(source_url)
    clean_title = (title or "").strip() or norm_url or "Untitled Capture"
    raw_content = content if content is not None else ""
    char_count = len(raw_content)
    now = datetime.now(timezone.utc).isoformat()

    with chats_db._get_conn() as conn:
        _ensure_table(conn)

        # Path 1: Upsert on matching `(conversation_id, source_url)` when a source URL is provided
        if norm_url is not None:
            existing = conn.execute(
                "SELECT id, cache_key FROM conversation_captures WHERE conversation_id = ? AND source_url = ? LIMIT 1",
                (convo_id, norm_url),
            ).fetchone()
            if existing is not None:
                if cache_key:
                    final_key = normalize_cache_key(cache_key, default_source_type=src_type)
                    if final_key != existing["cache_key"]:
                        conn.execute(
                            "DELETE FROM conversation_captures WHERE conversation_id = ? AND cache_key = ? AND id != ?",
                            (convo_id, final_key, existing["id"]),
                        )
                else:
                    final_key = str(existing["cache_key"])
                conn.execute(
                    """
                    UPDATE conversation_captures
                    SET cache_key = ?, source_type = ?, title = ?, content = ?, char_count = ?, created_at = ?
                    WHERE id = ?
                    """,
                    (final_key, src_type, clean_title, raw_content, char_count, now, existing["id"]),
                )
                return final_key

        # Path 2: Explicit `cache_key` upsert (e.g. `cache://email/<msg_id>`)
        if cache_key:
            resolved_key = normalize_cache_key(cache_key, default_source_type=src_type)
            conn.execute(
                """
                INSERT INTO conversation_captures (
                    conversation_id, cache_key, source_type, source_url, title, content, char_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id, cache_key) DO UPDATE SET
                    source_type = excluded.source_type,
                    source_url = excluded.source_url,
                    title = excluded.title,
                    content = excluded.content,
                    char_count = excluded.char_count,
                    created_at = excluded.created_at
                """,
                (convo_id, resolved_key, src_type, norm_url, clean_title, raw_content, char_count, now),
            )
            return resolved_key

        # Path 3: Auto-generate a unique slug handle; disambiguate distinct URLs with `-2`, `-3`, ...
        base_slug = make_capture_slug(clean_title, norm_url)
        base_key = f"{CACHE_SCHEME}{src_type}/{base_slug}"
        candidate_key = base_key
        suffix = 2
        while True:
            conflict = conn.execute(
                "SELECT id, source_url FROM conversation_captures WHERE conversation_id = ? AND cache_key = ? LIMIT 1",
                (convo_id, candidate_key),
            ).fetchone()
            if conflict is None:
                break
            # If neither the existing row nor the incoming capture has a URL, update the non-URL capture in place
            if norm_url is None and conflict["source_url"] is None:
                conn.execute(
                    """
                    UPDATE conversation_captures
                    SET source_type = ?, title = ?, content = ?, char_count = ?, created_at = ?
                    WHERE id = ?
                    """,
                    (src_type, clean_title, raw_content, char_count, now, conflict["id"]),
                )
                return candidate_key
            candidate_key = f"{base_key}-{suffix}"
            suffix += 1

        conn.execute(
            """
            INSERT INTO conversation_captures (
                conversation_id, cache_key, source_type, source_url, title, content, char_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (convo_id, candidate_key, src_type, norm_url, clean_title, raw_content, char_count, now),
        )
        return candidate_key


def get_capture(conversation_id: Optional[str], ref: str) -> Optional[dict[str, Any]]:
    """Resolves a `cache://...` key (external or `cache://chat/m<id>-b<n>`) or URL within `conversation_id`."""
    convo_id = (conversation_id or "").strip() or get_active_conversation_id()
    raw_ref = (ref or "").strip()
    if not raw_ref:
        return None

    with chats_db._get_conn() as conn:
        _ensure_table(conn)

        if raw_ref.lower().startswith(("http://", "https://")):
            norm_url = normalize_capture_url(raw_ref)
            row = None
            if norm_url:
                row = conn.execute(
                    """
                    SELECT cache_key, conversation_id, source_type, source_url, title, content, char_count, created_at
                    FROM conversation_captures
                    WHERE conversation_id = ? AND source_url = ?
                    LIMIT 1
                    """,
                    (convo_id, norm_url),
                ).fetchone()
            if row is None and raw_ref != norm_url:
                row = conn.execute(
                    """
                    SELECT cache_key, conversation_id, source_type, source_url, title, content, char_count, created_at
                    FROM conversation_captures
                    WHERE conversation_id = ? AND source_url = ?
                    LIMIT 1
                    """,
                    (convo_id, raw_ref),
                ).fetchone()
            return dict(row) if row is not None else None

        norm_key = normalize_cache_key(raw_ref)
        body = norm_key[len(CACHE_SCHEME) :]
        if _CHAT_KEY_RE.match(body):
            return get_chat_block(convo_id, norm_key)

        row = conn.execute(
            """
            SELECT cache_key, conversation_id, source_type, source_url, title, content, char_count, created_at
            FROM conversation_captures
            WHERE conversation_id = ? AND cache_key = ?
            LIMIT 1
            """,
            (convo_id, norm_key),
        ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT cache_key, conversation_id, source_type, source_url, title, content, char_count, created_at
                FROM conversation_captures
                WHERE conversation_id = ? AND LOWER(cache_key) = LOWER(?)
                LIMIT 1
                """,
                (convo_id, norm_key),
            ).fetchone()
        return dict(row) if row is not None else None


def list_captures(conversation_id: Optional[str]) -> list[dict[str, Any]]:
    """Returns a lightweight metadata manifest (no raw `content` text) for all captures in `conversation_id`."""
    convo_id = (conversation_id or "").strip() or get_active_conversation_id()
    with chats_db._get_conn() as conn:
        _ensure_table(conn)
        rows = conn.execute(
            """
            SELECT cache_key, conversation_id, source_type, source_url, title, char_count, created_at
            FROM conversation_captures
            WHERE conversation_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (convo_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def _derive_block_title(lines: list[str], open_idx: int, inner_lines: list[str], block_index: int) -> str:
    """Derive a concise human-readable title from a preceding Markdown heading/title or block content."""
    heading_or_title_re = re.compile(
        r"^(?:#{1,6}\s+.+|\*\*[^*\n]+\*\*.*|\d+[.)]\s+\*\*[^*\n]+\*\*.*|\d+[.)]\s+.+)$"
    )
    for idx in range(open_idx - 1, max(-1, open_idx - 6), -1):
        candidate = lines[idx].strip()
        if not candidate:
            continue
        if heading_or_title_re.match(candidate):
            cleaned = re.sub(r"^#{1,6}\s+", "", candidate)
            cleaned = re.sub(r"^\d+[.)]\s+", "", cleaned)
            cleaned = cleaned.replace("**", "").replace("`", "").strip()
            return cleaned[:80] if cleaned else f"Block #{block_index}"

    for inner in inner_lines:
        stripped = inner.strip()
        if stripped and stripped != "---":
            cleaned = re.sub(r"^#{1,6}\s+", "", stripped).replace("`", "").strip()
            if cleaned:
                return cleaned[:80]

    return f"Block #{block_index}"


def extract_fenced_blocks(content: str, min_chars: int = 0) -> list[dict[str, Any]]:
    """Extract CommonMark fenced code/draft blocks verbatim from Markdown message text.

    Tracks variable-length fences (` ``` ` vs ```` ```` ```` or `~~~`) so nested 3-backtick
    code blocks inside a 4-backtick outer draft block remain intact. Assigns 1-indexed
    `block_index` across all closed blocks before applying `min_chars` filtering so handles
    (`m<id>-b<n>`) never shift.
    """
    if not content:
        return []

    lines = content.splitlines()
    blocks: list[dict[str, Any]] = []
    block_index = 0
    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_lang = "text"
    open_idx = 0
    inner_lines: list[str] = []

    for idx, line in enumerate(lines):
        if not in_fence:
            m = _FENCE_OPEN_RE.match(line)
            if m:
                seq = m.group(1)
                info = m.group(2)
                # CommonMark: backtick info strings cannot contain backticks (prevents inline ```` ```foo``` ```` false positives)
                if seq[0] == "`" and "`" in info:
                    continue
                in_fence = True
                fence_char = seq[0]
                fence_len = len(seq)
                info_tokens = info.strip().split()
                fence_lang = info_tokens[0] if info_tokens else "text"
                open_idx = idx
                inner_lines = []
        else:
            close_re = re.compile(rf"^[ \t]{{0,3}}{re.escape(fence_char)}{{{fence_len},}}[ \t]*$")
            if close_re.match(line):
                block_index += 1
                body = "\n".join(inner_lines)
                if len(body) >= min_chars:
                    blocks.append(
                        {
                            "block_index": block_index,
                            "lang": fence_lang,
                            "title": _derive_block_title(lines, open_idx, inner_lines, block_index),
                            "content": body,
                            "char_count": len(body),
                            "line_count": len(inner_lines),
                        }
                    )
                in_fence = False
            else:
                inner_lines.append(line)

    return blocks


def list_chat_blocks(
    conversation_id: Optional[str],
    *,
    min_chars: int = CHAT_BLOCK_MIN_CHARS,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return lightweight metadata (no raw `content`) for fenced draft/code blocks in prior chat messages."""
    convo_id = (conversation_id or "").strip() or get_active_conversation_id()
    results: list[dict[str, Any]] = []
    with chats_db._get_conn() as conn:
        try:
            rows = conn.execute(
                """
                SELECT id, role, content, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                """,
                (convo_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    for row in rows:
        msg_id = int(row["id"])
        role = str(row["role"] or "assistant")
        ts = row["timestamp"] or ""
        blocks = extract_fenced_blocks(row["content"] or "", min_chars=min_chars)
        for blk in blocks:
            results.append(
                {
                    "cache_key": f"{CACHE_SCHEME}chat/m{msg_id}-b{blk['block_index']}",
                    "conversation_id": convo_id,
                    "source_type": "chat",
                    "source_url": None,
                    "title": blk["title"],
                    "role": role,
                    "lang": blk["lang"],
                    "message_id": msg_id,
                    "block_index": blk["block_index"],
                    "char_count": blk["char_count"],
                    "line_count": blk["line_count"],
                    "created_at": ts,
                }
            )
            if len(results) >= limit:
                return results
    return results


def get_chat_block(conversation_id: Optional[str], ref: str) -> Optional[dict[str, Any]]:
    """Resolve a `cache://chat/m<id>-b<n>` reference strictly within `conversation_id`."""
    convo_id = (conversation_id or "").strip() or get_active_conversation_id()
    cleaned = (ref or "").strip()
    if cleaned.lower().startswith(CACHE_SCHEME):
        cleaned = cleaned[len(CACHE_SCHEME) :]
    cleaned = cleaned.strip("/")
    match = _CHAT_KEY_RE.match(cleaned)
    if not match:
        return None

    msg_id = int(match.group(1))
    block_idx = int(match.group(2))
    with chats_db._get_conn() as conn:
        try:
            row = conn.execute(
                """
                SELECT id, role, content, timestamp
                FROM messages
                WHERE conversation_id = ? AND id = ?
                LIMIT 1
                """,
                (convo_id, msg_id),
            ).fetchone()
        except sqlite3.OperationalError:
            return None

    if row is None:
        return None

    for blk in extract_fenced_blocks(row["content"] or "", min_chars=0):
        if blk["block_index"] == block_idx:
            return {
                "cache_key": f"{CACHE_SCHEME}chat/m{msg_id}-b{block_idx}",
                "conversation_id": convo_id,
                "source_type": "chat",
                "source_url": None,
                "title": blk["title"],
                "content": blk["content"],
                "char_count": blk["char_count"],
                "created_at": row["timestamp"],
            }
    return None


def format_chat_blocks_manifest(
    conversation_id: Optional[str],
    *,
    min_chars: int = CHAT_BLOCK_MIN_CHARS,
) -> str:
    """Format prior chat message fenced draft/code blocks as a concise Markdown manifest."""
    convo_id = (conversation_id or "").strip() or get_active_conversation_id()
    blocks = list_chat_blocks(convo_id, min_chars=min_chars)
    if not blocks:
        return (
            f"No fenced draft or code blocks (>= {min_chars} chars) were found in prior chat messages "
            f"for conversation `{convo_id}`."
        )

    lines = [
        f"# Cached Chat Draft Blocks ({len(blocks)} item(s) in conversation `{convo_id}`)",
        "Use `read_file(\"<cache_key>\")` to inspect, `spawn_subagent(..., context_files=[\"<cache_key>\"])` "
        "to pre-hydrate, or `{{cache:chat/m<id>-b<n>}}` inside `create_file` / `modify_file` to splice verbatim.",
        "",
    ]
    for item in blocks:
        key = item["cache_key"]
        short_key = key[len(CACHE_SCHEME) :] if key.startswith(CACHE_SCHEME) else key
        lines.append(
            f"- `{key}` — **{item['title']}** ({item['role']}, {item['lang']}, "
            f"{item['char_count']:,} chars, {item['line_count']} lines) · splice: `{{{{cache:{short_key}}}}}`"
        )
    return "\n".join(lines)


def format_captures_manifest(conversation_id: Optional[str]) -> str:
    """Formats available per-conversation capture metadata as a concise Markdown manifest."""
    convo_id = (conversation_id or "").strip() or get_active_conversation_id()
    entries = list_captures(convo_id)
    chat_blocks = list_chat_blocks(convo_id, limit=15)
    if not entries and not chat_blocks:
        return (
            f"No external captures or chat draft blocks are currently cached for conversation `{convo_id}`.\n"
            f"Call `read_browser_tabs`, `read_webpage`, `get_youtube_transcript`, or `fetch_emails` to populate external captures, "
            f"or check `read_file(\"cache://chat\")` after assistant messages contain fenced blocks (>= {CHAT_BLOCK_MIN_CHARS} chars)."
        )

    if not entries:
        return (
            f"No external captures are currently cached for conversation `{convo_id}`.\n\n"
            f"{format_chat_blocks_manifest(convo_id)}"
        )

    lines = [
        f"# Cached External Captures ({len(entries)} item(s) in conversation `{convo_id}`)",
        "Use `read_file(\"<cache_key>\")` to inspect, `spawn_subagent(..., context_files=[\"<cache_key>\"])` "
        "to pre-hydrate, or `{{cache:<type>/<slug>}}` inside `create_file` / `modify_file` to splice verbatim.",
        "",
    ]
    for item in entries:
        key = item["cache_key"]
        short_key = key[len(CACHE_SCHEME) :] if key.startswith(CACHE_SCHEME) else key
        url_part = f" | URL: {item['source_url']}" if item.get("source_url") else ""
        lines.append(
            f"- `{key}` — **{item['title']}** ({item['source_type']}, {item['char_count']:,} chars"
            f"{url_part}) · splice: `{{{{cache:{short_key}}}}}`"
        )
    if chat_blocks:
        lines.append("")
        lines.append(format_chat_blocks_manifest(convo_id))
    return "\n".join(lines)


def inherit_captures(parent_conversation_id: str, child_conversation_id: str) -> int:
    """Copies all cached captures from `parent_conversation_id` into `child_conversation_id`.

    Child threads receive an isolated snapshot so later reads in the child do not mutate
    the parent, and deleting the parent never deletes the child's inherited captures.
    """
    parent_id = (parent_conversation_id or "").strip()
    child_id = (child_conversation_id or "").strip()
    if not parent_id or not child_id or parent_id == child_id:
        return 0

    with chats_db._get_conn() as conn:
        _ensure_table(conn)
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO conversation_captures (
                conversation_id, cache_key, source_type, source_url, title, content, char_count, created_at
            )
            SELECT ?, cache_key, source_type, source_url, title, content, char_count, created_at
            FROM conversation_captures
            WHERE conversation_id = ?
            """,
            (child_id, parent_id),
        )
        return max(0, int(cursor.rowcount or 0))


def clear_captures(conversation_id: str) -> int:
    """Deletes all cached captures belonging to `conversation_id` and returns the deleted row count."""
    convo_id = (conversation_id or "").strip()
    if not convo_id:
        return 0
    with chats_db._get_conn() as conn:
        _ensure_table(conn)
        cursor = conn.execute(
            "DELETE FROM conversation_captures WHERE conversation_id = ?",
            (convo_id,),
        )
        return max(0, int(cursor.rowcount or 0))
