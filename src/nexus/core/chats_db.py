"""
chats_db.py — Unified UI chat persistence and Sticky Session state.
"""
import sqlite3
import json
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
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                active_agent TEXT,
                last_updated TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                agent TEXT,
                domain TEXT,
                confidence REAL,
                trace TEXT,
                timestamp TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
        """)
        # Create default session if not exists
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, active_agent, last_updated) VALUES (?, ?, ?)",
            ("default", None, datetime.now(timezone.utc).isoformat())
        )

init_db()

def get_active_agent(session_id: str = "default") -> str | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT active_agent FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return row["active_agent"] if row else None

def set_active_agent(agent: str | None, session_id: str = "default"):
    with _get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE sessions SET active_agent = ?, last_updated = ? WHERE id = ?",
            (agent, now, session_id)
        )

def log_message(role: str, content: str, agent: str = None, domain: str = None, confidence: float = None, trace: list = None, session_id: str = "default"):
    with _get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        trace_json = json.dumps(trace) if trace else None
        conn.execute("""
            INSERT INTO messages (session_id, role, content, agent, domain, confidence, trace, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, role, content, agent, domain, confidence, trace_json, now))

def get_chat_history(session_id: str = "default", limit: int = 50) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT role, content, agent, domain, confidence, trace, timestamp 
            FROM messages 
            WHERE session_id = ? 
            ORDER BY id ASC
            LIMIT ?
        """, (session_id, limit)).fetchall()
        
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
