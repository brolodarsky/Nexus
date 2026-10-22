"""
blackboard.py — Shared Inter-Agent Blackboard / Message Board (`blackboard.db`).

Provides a persistent, zero-contention SQLite bulletin board where the primary orchestrator (`NexusAgent` / Astra)
and parallel Flash subagents (`spawn_subagent` on `gemini-3.8-flash`) can post and read structured situational
findings (e.g. Gmail sweeps, Google Calendar audits, Vault file inspections, and mission status updates).

Why a Shared Blackboard?
  1. Prevents Redundant API & Disk Sweeps: Once a Flash subagent sweeps Gmail or Google Calendar and posts its
     distilled bulletin to the board (`channel="email"` or `channel="calendar"`), Astra and peer subagents can
     read the board (`read_board`) across turns without re-fetching external APIs.
  2. Parallel Swarm Coordination: When Astra spawns 3–5 Flash subagents concurrently in a single turn, every
     subagent's completed findings are automatically recorded onto the Message Board with channel tags,
     timestamps, and author attribution.
  3. Live GUI Bulletin Feed: The Next.js Control Panel (`/ask` & `/api/board`) renders a live situational feed
     of all subagent bulletins alongside the main conversation thread.
"""
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

# Separate SQLite database file (`src/nexus/blackboard.db`) so parallel subagent bulletin writes
# never contend with `hitl.db` or `memory.sqlite`.
BOARD_DB_PATH = Path(__file__).resolve().parent.parent / "blackboard.db"


def get_board_connection() -> sqlite3.Connection:
    """Opens a SQLite connection to `blackboard.db` with `sqlite3.Row` dictionary-style row access."""
    conn = sqlite3.connect(BOARD_DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_board_db() -> None:
    """Creates the `bulletins` table if it does not exist."""
    conn = get_board_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bulletins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'general',
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            pinned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


def infer_channel(text: str) -> str:
    """Infers a semantic board channel (`email`, `calendar`, `vault`, `mission`, `general`) from task/title text."""
    lower = (text or "").lower()
    if any(k in lower for k in ("gmail", "email", "inbox", "unread", "message")):
        return "email"
    if any(k in lower for k in ("calendar", "schedule", "appointment", "event", "gcal")):
        return "calendar"
    if any(k in lower for k in ("mission", "resume", "job", "application", "career", "outreach")):
        return "mission"
    if any(k in lower for k in ("vault", "plan.md", "tasks.md", "section", "note", "file")):
        return "vault"
    return "general"


def post_bulletin(
    author: str,
    title: str,
    content: str,
    channel: Optional[str] = None,
    pinned: bool = False,
) -> int:
    """Inserts a new bulletin onto the Shared Agent Blackboard and returns its integer ID."""
    resolved_channel = (channel or infer_channel(f"{title} {content}")).strip().lower() or "general"
    conn = get_board_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO bulletins (author, channel, title, content, pinned)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            author.strip() or "Subagent",
            resolved_channel,
            title.strip() or "Subagent Report",
            content.strip(),
            1 if pinned else 0,
        ),
    )
    bulletin_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()
    return bulletin_id


def get_bulletins(
    channel: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Fetches recent bulletins from the Shared Agent Blackboard, ordered pinned-first then newest-first."""
    conn = get_board_connection()
    cursor = conn.cursor()
    if channel and channel.strip().lower() not in ("all", ""):
        cursor.execute(
            """
            SELECT * FROM bulletins
            WHERE LOWER(channel) = ?
            ORDER BY pinned DESC, id DESC
            LIMIT ?
            """,
            (channel.strip().lower(), max(1, min(limit, 100))),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM bulletins
            ORDER BY pinned DESC, id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 100)),),
        )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def delete_bulletin(bulletin_id: int) -> bool:
    """Deletes a single bulletin by ID. Returns True if a row was deleted."""
    conn = get_board_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bulletins WHERE id = ?", (bulletin_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def clear_bulletins(channel: Optional[str] = None) -> int:
    """Clears all unpinned bulletins (or all bulletins in a specific `channel`). Returns count deleted."""
    conn = get_board_connection()
    cursor = conn.cursor()
    if channel and channel.strip().lower() not in ("all", ""):
        cursor.execute("DELETE FROM bulletins WHERE LOWER(channel) = ?", (channel.strip().lower(),))
    else:
        cursor.execute("DELETE FROM bulletins WHERE pinned = 0")
    count = int(cursor.rowcount)
    conn.commit()
    conn.close()
    return count


def format_board_digest(channel: Optional[str] = None, limit: int = 12) -> str:
    """Formats recent Blackboard bulletins as a structured Markdown digest for agent consumption."""
    items = get_bulletins(channel=channel, limit=limit)
    if not items:
        scope = f" in channel `{channel}`" if channel else ""
        return f"📋 Shared Agent Blackboard is currently empty{scope}."

    lines = [f"### 📋 Shared Agent Blackboard ({len(items)} recent bulletin(s))"]
    for item in items:
        pin_badge = "📌 " if item.get("pinned") else ""
        lines.append(
            f"\n#### {pin_badge}[#{item['id']}] [{item['channel'].upper()}] {item['title']} "
            f"*(by {item['author']} at {item['created_at']})*\n{item['content']}"
        )
    return "\n".join(lines)


# Ensure `blackboard.db` schema exists on module import
init_board_db()
