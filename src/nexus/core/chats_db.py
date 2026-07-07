"""
chats_db.py — Unified UI chat persistence and Sticky Session state.
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
                active_agent TEXT,
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
                FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)

init_db()

def create_conversation(title: str = "New Chat") -> str:
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, active_agent, created_at, last_updated) VALUES (?, ?, ?, ?, ?)",
            (conv_id, title, None, now, now)
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

def get_active_agent(conversation_id: str) -> str | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT active_agent FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
        return row["active_agent"] if row else None

def set_active_agent(agent: str | None, conversation_id: str):
    with _get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE conversations SET active_agent = ?, last_updated = ? WHERE id = ?",
            (agent, now, conversation_id)
        )
        conn.commit()

def log_message(role: str, content: str, agent: str = None, domain: str = None, confidence: float = None, trace: list = None, conversation_id: str = None):
    if not conversation_id:
        return
    
    with _get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        trace_json = json.dumps(trace) if trace else None
        conn.execute("""
            INSERT INTO messages (conversation_id, role, content, agent, domain, confidence, trace, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (conversation_id, role, content, agent, domain, confidence, trace_json, now))
        
        conn.execute("UPDATE conversations SET last_updated = ? WHERE id = ?", (now, conversation_id))
        conn.commit()

def get_chat_history(conversation_id: str, limit: int = 50) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT role, content, agent, domain, confidence, trace, timestamp 
            FROM messages 
            WHERE conversation_id = ? 
            ORDER BY id ASC
            LIMIT ?
        """, (conversation_id, limit)).fetchall()
        
        history = []
        for r in rows:
            history.append({
                "role": r["role"],
                "content": r["content"],
                "agent": r["agent"],
                "domain": r["domain"],
                "confidence": r["confidence"],
                "trace": json.loads(r["trace"]) if r["trace"] else [],
                "timestamp": r["timestamp"]
            })
        return history
