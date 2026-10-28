"""
blackboard.py — Shared Inter-Agent Blackboard / Message Board (`blackboard.db`).

Provides a persistent, zero-contention SQLite bulletin board where the primary orchestrator (`NexusAgent` / Astra)
and parallel Flash subagents (`spawn_subagent` on `gemini-3.8-flash`) can post and read structured situational
findings (e.g. Gmail sweeps, Google Calendar audits, Vault file inspections, and mission status updates).

Why a Shared Blackboard?
  1. Prevents Redundant API & Disk Sweeps: Once a Flash subagent sweeps Gmail or Google Calendar and posts its
     distilled bulletin to the board, Astra and peer subagents can read the board (`read_board`) across turns without
     re-fetching external APIs.
  2. Parallel Swarm Coordination: When Astra spawns 3–5 Flash subagents concurrently in a single turn, every
     subagent's completed findings are automatically recorded onto the Message Board with timestamps and author
     attribution, eliminating artificial channel partitioning in favor of a unified bulletin stream.
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
    """Opens a SQLite connection to `blackboard.db` with `sqlite3.Row` dictionary-style row access.
    
    `sqlite3.Row` provides key-based column lookups (e.g. `row["author"]`) alongside tuple indexing,
    making database query results drop-in compatible with standard Python dictionaries.
    """
    conn = sqlite3.connect(BOARD_DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_board_db() -> None:
    """Creates the `bulletins` table if it does not exist, or migrates legacy schema by dropping `channel`."""
    conn = get_board_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bulletins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            pinned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Schema Migration: If the table was previously created with a legacy `channel` column,
    # drop that column using SQLite's native `ALTER TABLE ... DROP COLUMN` (supported in SQLite >=3.35.0).
    columns = [row["name"] for row in cursor.execute("PRAGMA table_info(bulletins)").fetchall()]
    if "channel" in columns:
        cursor.execute("ALTER TABLE bulletins DROP COLUMN channel")

    conn.commit()
    conn.close()


def post_bulletin(
    author: str,
    title: str,
    content: str,
    pinned: bool = False,
    **kwargs: Any,  # Safely absorb any legacy kwargs (such as deprecated `channel`) without raising TypeError
) -> int:
    """Inserts a new bulletin onto the Shared Agent Blackboard and returns its integer ID.

    Args:
        author: Identifier for the posting agent (e.g. "Subagent #1 (low)" or "Astra").
        title: Short descriptive headline for the finding or sweep.
        content: Markdown summary containing distilled observations and actionable takeaways.
        pinned: When True, pins the bulletin to the top of the board digest across turns.
        **kwargs: Absorbs legacy parameters (e.g. `channel`) for backward compatibility.
    """
    conn = get_board_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO bulletins (author, title, content, pinned)
        VALUES (?, ?, ?, ?)
        """,
        (
            author.strip() or "Subagent",
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
    limit: int = 20,
    *args: Any,
    **kwargs: Any,  # Safely absorb any legacy positional or keyword args (e.g. `channel`)
) -> List[Dict[str, Any]]:
    """Fetches recent bulletins from the Shared Agent Blackboard, ordered pinned-first then newest-first.

    Args:
        limit: Maximum number of bulletins to retrieve (bounded between 1 and 100).
    """
    conn = get_board_connection()
    cursor = conn.cursor()
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


def clear_bulletins(*args: Any, **kwargs: Any) -> int:
    """Clears all unpinned bulletins from the Shared Agent Blackboard. Returns count deleted."""
    conn = get_board_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bulletins WHERE pinned = 0")
    count = int(cursor.rowcount)
    conn.commit()
    conn.close()
    return count


def format_board_digest(limit: int = 12, **kwargs: Any) -> str:
    """Formats recent Blackboard bulletins as a structured Markdown digest for agent consumption.

    Eliminates artificial channel tags so bulletins read as a unified chronological briefing.
    """
    items = get_bulletins(limit=limit)
    if not items:
        return "📋 Shared Agent Blackboard is currently empty."

    lines = [f"### 📋 Shared Agent Blackboard ({len(items)} recent bulletin(s))"]
    for item in items:
        pin_badge = "📌 " if item.get("pinned") else ""
        lines.append(
            f"\n#### {pin_badge}[#{item['id']}] {item['title']} "
            f"*(by {item['author']} at {item['created_at']})*\n{item['content']}"
        )
    return "\n".join(lines)


# Ensure `blackboard.db` schema exists and is migrated on module import
init_board_db()
