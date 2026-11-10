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
    # timeout=30.0: Waits up to 30s for any transient lock to release before raising OperationalError
    # PRAGMA journal_mode=WAL: Enables Write-Ahead Logging so concurrent readers never block active writers
    # PRAGMA busy_timeout=30000: Configures SQLite engine-level busy handler timeout in milliseconds
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    migrated_count = 0
    with _get_conn() as conn:
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT,
                last_updated TEXT,
                parent_conversation_id TEXT,
                parent_message_id INTEGER,
                branch_mode TEXT,
                merged_at TEXT
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
                model_tier TEXT,
                model_name TEXT,
                cost_usd REAL,
                has_trace INTEGER DEFAULT 0,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        # Schema migration: check if columns exist for existing `messages` tables and alter if missing
        msg_cols = [col[1] for col in conn.execute("PRAGMA table_info(messages)").fetchall()]
        if "images" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN images TEXT")
        if "model_tier" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN model_tier TEXT")
        if "model_name" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN model_name TEXT")
        if "cost_usd" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN cost_usd REAL")
        if "has_trace" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN has_trace INTEGER DEFAULT 0")

        # Create separate message_traces table to isolate heavy execution telemetry from primary chat messages
        # Keeping trace blobs decoupled prevents SQLite overflow page chaining and ensures chat history queries stay ~1KB/turn
        conn.execute("""
            CREATE TABLE IF NOT EXISTS message_traces (
                message_id INTEGER PRIMARY KEY,
                trace TEXT,
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
            )
        """)

        # Schema migration: check if there are legacy unmigrated trace blobs stored directly in `messages.trace`
        legacy_rows = conn.execute("""
            SELECT id, trace, agent
            FROM messages
            WHERE trace IS NOT NULL AND length(trace) > 10
        """).fetchall()

        if legacy_rows:
            for row in legacy_rows:
                msg_id = row["id"]
                raw_trace = row["trace"]
                extracted_tier = None
                extracted_model = None
                extracted_cost = 0.0
                try:
                    events = json.loads(raw_trace)
                    for e in events:
                        t = e.get("type")
                        data = e.get("data") if isinstance(e.get("data"), dict) else {}
                        if not extracted_tier and "model_tier" in data:
                            extracted_tier = data.get("model_tier")
                        if not extracted_model and "model_name" in data:
                            extracted_model = data.get("model_name")
                        if t == "info" and "cost_usd" in data:
                            extracted_cost += float(data.get("cost_usd", 0.0) or 0.0)
                except Exception:
                    pass

                conn.execute(
                    "INSERT OR REPLACE INTO message_traces (message_id, trace) VALUES (?, ?)",
                    (msg_id, raw_trace),
                )
                conn.execute(
                    """
                    UPDATE messages 
                    SET has_trace = 1,
                        model_tier = coalesce(model_tier, ?),
                        model_name = coalesce(model_name, ?),
                        cost_usd = coalesce(cost_usd, ?),
                        trace = NULL
                    WHERE id = ?
                    """,
                    (extracted_tier, extracted_model, extracted_cost if extracted_cost > 0 else None, msg_id),
                )
                migrated_count += 1
            conn.commit()

        # Schema migration: add Universal Conversation Branching (DAG lineage) columns to existing `conversations` tables
        conv_cols = [col[1] for col in conn.execute("PRAGMA table_info(conversations)").fetchall()]
        if "parent_conversation_id" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN parent_conversation_id TEXT")
        if "parent_message_id" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN parent_message_id INTEGER")
        if "branch_mode" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN branch_mode TEXT")
        if "merged_at" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN merged_at TEXT")

    # If legacy rows were migrated out of the primary messages table, vacuum the database file to reclaim disk space
    if migrated_count > 0:
        with _get_conn() as vacuum_conn:
            vacuum_conn.isolation_level = None
            vacuum_conn.execute("VACUUM;")


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


def create_branch_conversation(
    title: str,
    parent_conversation_id: str,
    parent_message_id: int | None = None,
    branch_mode: str = "tangent",
) -> str:
    """
    Creates a new branched child conversation in `chats.db` linked to its parent thread and fork message.

    Parameters:
      title: Display title for the newly forked child branch.
      parent_conversation_id: UUID of the parent conversation from which this branch was spawned.
      parent_message_id: Optional SQLite `messages.id` in the parent conversation where the fork occurred.
      branch_mode: Either `'tangent'` (context-sliced fresh ALU) or `'fork'` (full history clone up to branch point).

    Returns:
      The newly generated UUID string for the child conversation.
    """
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO conversations (
                id, title, created_at, last_updated,
                parent_conversation_id, parent_message_id, branch_mode, merged_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (conv_id, title, now, now, parent_conversation_id, parent_message_id, branch_mode),
        )
        conn.commit()
    return conv_id


def mark_branch_merged(conversation_id: str) -> str:
    """
    Marks a child branch conversation as distilled and merged back into its parent thread.

    Parameters:
      conversation_id: UUID of the child branch conversation.

    Returns:
      The ISO-8601 UTC timestamp recorded in `merged_at`.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET merged_at = ?, last_updated = ? WHERE id = ?",
            (now, now, conversation_id),
        )
        conn.commit()
    return now


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
        # Promote any child branches to root level so deleting a parent never orphans child threads
        conn.execute(
            "UPDATE conversations SET parent_conversation_id = NULL WHERE parent_conversation_id = ?",
            (conversation_id,),
        )
        # Purge diagnostic execution traces linked to messages in this conversation
        conn.execute(
            "DELETE FROM message_traces WHERE message_id IN (SELECT id FROM messages WHERE conversation_id = ?)",
            (conversation_id,),
        )
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
    model_tier: str | None = None,
    model_name: str | None = None,
    cost_usd: float | None = None,
) -> int | None:
    if not conversation_id:
        return None
    
    with _get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        # Serialize list of image URLs/paths to a JSON string for lightweight column storage
        images_json = json.dumps(images) if images else None
        has_trace = 1 if (trace and len(trace) > 0) else 0

        # Primary messages table row is kept strictly lean: trace column remains NULL,
        # preventing large JSON blobs from triggering SQLite overflow page chaining during chat queries.
        cursor = conn.execute("""
            INSERT INTO messages (
                conversation_id, role, content, agent, domain, confidence,
                trace, timestamp, images, model_tier, model_name, cost_usd, has_trace
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
        """, (
            conversation_id, role, content, agent, domain, confidence,
            now, images_json, model_tier, model_name, cost_usd, has_trace
        ))
        
        msg_id = int(cursor.lastrowid) if cursor.lastrowid is not None else None

        # Isolate heavy diagnostic execution traces into dedicated message_traces table
        if trace and msg_id is not None:
            trace_json = json.dumps(trace)
            conn.execute("""
                INSERT OR REPLACE INTO message_traces (message_id, trace)
                VALUES (?, ?)
            """, (msg_id, trace_json))

        conn.execute("UPDATE conversations SET last_updated = ? WHERE id = ?", (now, conversation_id))
        conn.commit()
        return msg_id

def get_chat_history(
    conversation_id: str,
    limit: int | None = None,
    include_trace: bool = False,
) -> list[dict]:
    """
    Retrieves the chronological chat history for a given conversation UUID.

    Parameters:
    - conversation_id: The UUID of the conversation thread.
    - limit: Optional maximum number of messages to fetch from the start of the thread.
             Defaults to None (unbounded), ensuring active conversations with >50 turns
             never drop recent messages or attachments.
    - include_trace: Whether to eager-load complete diagnostic trace JSON arrays.
                     Defaults to False, ensuring standard chat queries stay fast and lightweight (~1KB/turn)
                     without pulling multi-megabyte trace blobs into memory.
    """
    with _get_conn() as conn:
        if include_trace:
            query = """
                SELECT m.id, m.role, m.content, m.agent, m.domain, m.confidence,
                       m.timestamp, m.images, m.model_tier, m.model_name, m.cost_usd, m.has_trace,
                       t.trace AS trace_payload
                FROM messages m
                LEFT JOIN message_traces t ON t.message_id = m.id
                WHERE m.conversation_id = ? 
                ORDER BY m.id ASC
            """
        else:
            query = """
                SELECT id, role, content, agent, domain, confidence,
                       timestamp, images, model_tier, model_name, cost_usd, has_trace
                FROM messages 
                WHERE conversation_id = ? 
                ORDER BY id ASC
            """

        params = (conversation_id, limit) if limit is not None else (conversation_id,)
        if limit is not None:
            query += " LIMIT ?"

        rows = conn.execute(query, params).fetchall()
        
        history = []
        for r in rows:
            # Safely extract and deserialize optional images JSON array
            raw_images = r["images"] if "images" in r.keys() else None
            parsed_images = json.loads(raw_images) if raw_images else []

            if include_trace:
                raw_trace = r["trace_payload"] if "trace_payload" in r.keys() else None
                trace_events = json.loads(raw_trace) if raw_trace else []
            else:
                trace_events = []

            has_trace = bool(r["has_trace"]) if "has_trace" in r.keys() else bool(trace_events)

            history.append({
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "agent": r["agent"],
                "domain": r["domain"],
                "confidence": r["confidence"],
                "trace": trace_events,
                "timestamp": r["timestamp"],
                "images": parsed_images,
                "model_tier": r["model_tier"] if "model_tier" in r.keys() else None,
                "model_name": r["model_name"] if "model_name" in r.keys() else None,
                "cost_usd": r["cost_usd"] if "cost_usd" in r.keys() else None,
                "has_trace": has_trace,
            })
        return history


def get_message_trace(message_id: int) -> list[dict]:
    """
    Retrieves the full, untruncated trace events array for a specific message ID on demand.
    Checks `message_traces` table first, with fallback to legacy `messages.trace`.

    Parameters:
      message_id: The SQLite primary key of the target assistant message.

    Returns:
      Deserialized list of trace event dictionaries, or an empty list if none exist.
    """
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT trace FROM message_traces WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        if row and row["trace"]:
            try:
                return json.loads(row["trace"])
            except Exception:
                return []
        
        # Fallback check on legacy messages column if not yet migrated
        legacy_row = conn.execute(
            "SELECT trace FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if legacy_row and legacy_row["trace"]:
            try:
                return json.loads(legacy_row["trace"])
            except Exception:
                return []
        return []


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
            # Purge corresponding diagnostic traces from message_traces table
            conn.execute(f"DELETE FROM message_traces WHERE message_id IN ({placeholders})", ids_to_delete)
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

