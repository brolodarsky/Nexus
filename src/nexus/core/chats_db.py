"""
chats_db.py — Unified UI chat persistence.
"""
import sqlite3
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent.parent.parent / "logs" / "chats.db"

def _get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _get_conn() as conn:
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                last_updated TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                role TEXT,
                content TEXT,
                agent TEXT,
                domain TEXT,
                confidence REAL,
                trace TEXT,
                timestamp TEXT,
                images TEXT,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        # Schema migration: check if `images` column exists for existing tables and alter if missing
        cols = [col[1] for col in conn.execute("PRAGMA table_info(messages)").fetchall()]
        if "images" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN images TEXT")


init_db()

def create_conversation(title: str = "New Chat") -> str:
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, last_updated) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now)
        )
        conn.commit()
    return conv_id

def get_conversations() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM conversations ORDER BY last_updated DESC").fetchall()
        return [dict(r) for r in rows]

def get_conversation(conversation_id: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return dict(row) if row else None

def delete_conversation(conversation_id: str):
    with _get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()

def update_conversation_title(conversation_id: str, title: str):
    with _get_conn() as conn:
        conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))
        conn.commit()

# `images: list[str] | None` accepts an optional array of image file URLs/paths (e.g. `/api/agents/uploads/<uuid>.png`)
def log_message(
    role: str,
    content: str,
    agent: str = None,
    domain: str = None,
    confidence: float = None,
    trace: list = None,
    conversation_id: str = None,
    images: list[str] | None = None,
):
    if not conversation_id:
        return
    
    with _get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        trace_json = json.dumps(trace) if trace else None
        # Serialize list of image URLs/paths to a JSON string for lightweight column storage
        images_json = json.dumps(images) if images else None
        conn.execute("""
            INSERT INTO messages (conversation_id, role, content, agent, domain, confidence, trace, timestamp, images)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (conversation_id, role, content, agent, domain, confidence, trace_json, now, images_json))
        
        conn.execute("UPDATE conversations SET last_updated = ? WHERE id = ?", (now, conversation_id))
        conn.commit()

def get_chat_history(conversation_id: str, limit: int | None = None) -> list[dict]:
    """
    Retrieves the chronological chat history for a given conversation UUID.

    Parameters:
    - conversation_id: The UUID of the conversation thread.
    - limit: Optional maximum number of messages to fetch from the start of the thread.
             Defaults to None (unbounded), ensuring active conversations with >50 turns
             never drop recent messages or attachments.
    """
    with _get_conn() as conn:
        if limit is not None:
            rows = conn.execute("""
                SELECT role, content, agent, domain, confidence, trace, timestamp, images 
                FROM messages 
                WHERE conversation_id = ? 
                ORDER BY id ASC
                LIMIT ?
            """, (conversation_id, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT role, content, agent, domain, confidence, trace, timestamp, images 
                FROM messages 
                WHERE conversation_id = ? 
                ORDER BY id ASC
            """, (conversation_id,)).fetchall()
        
        history = []
        for r in rows:
            # Safely extract and deserialize optional images JSON array
            raw_images = r["images"] if "images" in r.keys() else None
            parsed_images = json.loads(raw_images) if raw_images else []
            history.append({
                "role": r["role"],
                "content": r["content"],
                "agent": r["agent"],
                "domain": r["domain"],
                "confidence": r["confidence"],
                "trace": json.loads(r["trace"]) if r["trace"] else [],
                "timestamp": r["timestamp"],
                "images": parsed_images,
            })
        return history


def revert_last_turn(conversation_id: str) -> dict | None:
    """
    Reverts the latest turn in a conversation by deleting its messages from SQLite `chats.db`.
    
    Handles two operational states:
      1. Mid-turn Abort (Stop & Revert): Only the user prompt was persisted when execution was stopped;
         deletes the solitary user message and restores its text and attached images.
      2. Completed Turn Rollback: Both user prompt and assistant response were persisted;
         deletes both messages in reverse chronological order and restores the user's prompt text.
         
    Parameters:
      conversation_id: The UUID of the conversation thread.
      
    Returns:
      Dictionary with restored user prompt, image URLs, and deleted message count:
      `{"restored_query": str, "images": list[str], "deleted_count": int}`
      or None if the conversation thread contains no messages.
    """
    if not conversation_id:
        return None

    with _get_conn() as conn:
        # Fetch all messages for this conversation ordered chronologically
        rows = conn.execute("""
            SELECT id, role, content, images
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
        """, (conversation_id,)).fetchall()

        if not rows:
            return None

        last_row = rows[-1]
        ids_to_delete: list[int] = []
        restored_query = ""
        restored_images: list[str] = []

        if last_row["role"] == "assistant":
            ids_to_delete.append(last_row["id"])
            # Search backwards for the corresponding user message that prompted this assistant reply
            for r in reversed(rows[:-1]):
                if r["role"] == "user":
                    ids_to_delete.append(r["id"])
                    restored_query = r["content"] or ""
                    raw_images = r["images"] if "images" in r.keys() else None
                    restored_images = json.loads(raw_images) if raw_images else []
                    break
        elif last_row["role"] == "user":
            # Mid-turn abort: only the user prompt exists at the tail of the message log
            ids_to_delete.append(last_row["id"])
            restored_query = last_row["content"] or ""
            raw_images = last_row["images"] if "images" in last_row.keys() else None
            restored_images = json.loads(raw_images) if raw_images else []

        if ids_to_delete:
            placeholders = ",".join("?" for _ in ids_to_delete)
            conn.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", ids_to_delete)
            # Update last_updated timestamp on parent conversation row
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE conversations SET last_updated = ? WHERE id = ?", (now, conversation_id))
            conn.commit()

            return {
                "restored_query": restored_query,
                "images": restored_images,
                "deleted_count": len(ids_to_delete),
            }

        return None

