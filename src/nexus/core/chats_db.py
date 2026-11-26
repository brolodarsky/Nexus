"""
chats_db.py — Unified UI chat, execution telemetry, content-addressed blobs, and canonical thread state.

Consolidates conversations, messages, execution telemetry, and graph state into a single WAL-mode SQLite database with:
  1. Normalized relational tables: `conversations`, `messages` (linked via `run_id`), `runs`, `trace_events`, `thread_messages`.
  2. Content-addressed `trace_blobs` (SHA-256 deduplicated after secret scrubbing) + `run_blob_refs`
     reference-counted garbage collection (`ON DELETE CASCADE` + immediate zero-ref sweep).
  3. Asset reference tracking (`upload_refs`) so deleted threads also clean up orphaned `logs/uploads/` files.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable, Optional
import uuid

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    messages_from_dict,
    messages_to_dict,
)

from nexus.core.cost import calculate_cache_savings, calculate_token_cost
from nexus.core.secret_scrubber import approx_token_count, scrub_secrets, scrub_structure

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_DB_PATH = PROJECT_ROOT / "logs" / "chats.db"
DB_PATH = _DEFAULT_DB_PATH
UPLOADS_DIR = PROJECT_ROOT / "logs" / "uploads"

# Strict hex digest validator (16–64 hex chars) preventing SQL injection or path traversal in blob lookups
_HEX_HASH_RE = re.compile(r"^[0-9a-fA-F]{16,64}$")
# Matches `data:image/<ext>;base64,<payload>` URLs so inline image payloads are never duplicated into SQLite
_DATA_IMAGE_URI_RE = re.compile(r"^data:image/([a-zA-Z0-9.+-]+);base64,(.+)$", re.DOTALL)


# @contextmanager: turns a generator into a `with`-statement resource guard that always closes the SQLite handle
@contextmanager
def _get_conn():
    """Yields a WAL-configured SQLite connection with FK enforcement, committing on clean exit and closing deterministically."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # timeout=30.0: Waits up to 30s for any transient lock to release before raising OperationalError
    # PRAGMA journal_mode=WAL: Enables Write-Ahead Logging so concurrent readers never block active writers
    # PRAGMA busy_timeout=30000: Configures SQLite engine-level busy handler timeout in milliseconds
    # PRAGMA foreign_keys=ON: Enforces ON DELETE CASCADE across messages, runs, trace_events, and run_blob_refs
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        # Commit pending writes if a transaction is open (skip when autocommit/VACUUM disabled transactions)
        if conn.in_transaction:
            conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        # Always close the OS file handle so concurrent threads never leak open descriptors on Windows
        conn.close()


def init_db():
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
                merged_at TEXT,
                title_source TEXT DEFAULT 'placeholder',
                last_model_tier TEXT,
                last_model_name TEXT
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
                run_id TEXT,
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
        if "run_id" not in msg_cols:
            conn.execute("ALTER TABLE messages ADD COLUMN run_id TEXT")

        # Drop retired legacy `message_traces` table now that all traces normalize onto `runs` + `trace_events`
        conn.execute("DROP TABLE IF EXISTS message_traces")

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
        # Track title provenance ('placeholder' | 'auto' | 'manual' | 'legacy') so background auto-titling never clobbers user edits
        if "title_source" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN title_source TEXT DEFAULT 'legacy'")
        # Track the last model tier & concrete model identifier used in each conversation for UI restoration and cache consistency
        added_last_model_cols = False
        if "last_model_tier" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN last_model_tier TEXT")
            added_last_model_cols = True
        if "last_model_name" not in conv_cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN last_model_name TEXT")
            added_last_model_cols = True

        # Index (conversation_id, id) so chronological history reads and latest-model lookups stay fast
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages (conversation_id, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_run_id ON messages (run_id)"
        )

        # One-time backfill for existing databases upgraded with `last_model_*` columns:
        # populate each conversation from its newest message carrying model metadata
        if added_last_model_cols:
            conn.execute(
                """
                UPDATE conversations
                SET
                    last_model_tier = (
                        SELECT m.model_tier
                        FROM messages m
                        WHERE m.conversation_id = conversations.id
                          AND (m.model_name IS NOT NULL OR m.model_tier IS NOT NULL)
                        ORDER BY m.id DESC
                        LIMIT 1
                    ),
                    last_model_name = (
                        SELECT m.model_name
                        FROM messages m
                        WHERE m.conversation_id = conversations.id
                          AND (m.model_name IS NOT NULL OR m.model_tier IS NOT NULL)
                        ORDER BY m.id DESC
                        LIMIT 1
                    )
                WHERE last_model_tier IS NULL AND last_model_name IS NULL
                """
            )

        # Per-conversation external capture cache (`conversation_cache.py`), kept independent of FK
        # cascade so CLI/eval `"nexus_primary"` runs can store captures while `delete_conversation` purges explicitly.
        conn.execute("""
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
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_captures_conv_id ON conversation_captures (conversation_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_captures_conv_url ON conversation_captures (conversation_id, source_url)"
        )

        # ── Unified Observability, Content-Addressed Blobs & Canonical Thread State ──
        # Content-addressed deduplicated payloads (system prompts, tool schemas, pre-hydrated files, wire messages)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trace_blobs (
                hash TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                char_count INTEGER NOT NULL,
                approx_tokens INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Normalized top-level execution ledger unifying Chat UI, Telegram, CLI, and Eval runs
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'running',
                source TEXT NOT NULL DEFAULT 'chat',
                thread_id TEXT,
                conversation_id TEXT,
                agent_name TEXT NOT NULL DEFAULT 'nexus',
                domain TEXT,
                confidence REAL,
                reasoning TEXT,
                input_query TEXT NOT NULL DEFAULT '',
                output_response TEXT NOT NULL DEFAULT '',
                model_tier TEXT,
                model_name TEXT,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cached_tokens INTEGER NOT NULL DEFAULT 0,
                reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL,
                cache_savings_usd REAL,
                latency_seconds REAL,
                dpfh_injected_files_json TEXT,
                tool_calls_json TEXT,
                subagents_count INTEGER NOT NULL DEFAULT 0,
                trace_events_count INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON runs (timestamp DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_conv ON runs (conversation_id, timestamp DESC)"
        )

        # Incremental live step log appended at emission time via AgentTracer -> trace_bus
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trace_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_trace_events_run_seq ON trace_events (run_id, seq)"
        )

        # Reference ledger tying runs to SHA-256 blobs so deleting a run reclaims only zero-ref blobs
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_blob_refs (
                run_id TEXT NOT NULL,
                blob_hash TEXT NOT NULL,
                PRIMARY KEY (run_id, blob_hash),
                FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
                FOREIGN KEY(blob_hash) REFERENCES trace_blobs(hash) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_run_blob_refs_hash ON run_blob_refs (blob_hash)"
        )

        # Asset reference ledger tying `logs/uploads/<filename>` files to messages and runs
        conn.execute("""
            CREATE TABLE IF NOT EXISTS upload_refs (
                owner_key TEXT NOT NULL,
                upload_filename TEXT NOT NULL,
                PRIMARY KEY (owner_key, upload_filename)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_upload_refs_filename ON upload_refs (upload_filename)"
        )

        # Canonical LangChain message state replacing LangGraph's 1.49 GB `memory.sqlite` SqliteSaver
        conn.execute("""
            CREATE TABLE IF NOT EXISTS thread_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                turn_id TEXT,
                msg_type TEXT NOT NULL,
                msg_json TEXT NOT NULL,
                blob_hash TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_thread_messages_thread_id ON thread_messages (thread_id, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_thread_messages_turn_id ON thread_messages (thread_id, turn_id)"
        )


init_db()


# ── Content-Addressed Blob Store & Upload Reference Helpers ──────────────────

# `ref: str` is an image URL, upload route (`/api/agents/uploads/<file>`), or local filename.
# `-> str | None` returns the safe filename if `ref` points to a local upload asset, else None.
def _normalize_upload_filename(ref: str) -> str | None:
    """Extract the local upload basename when `ref` refers to a `logs/uploads/` asset."""
    if not isinstance(ref, str):
        return None
    cleaned = ref.strip()
    if not cleaned or cleaned.startswith(("http://", "https://", "data:", "blob:")):
        return None
    # Restrict cleanup tracking to `/api/agents/uploads/...` or bare/relative upload paths
    if "/uploads/" in cleaned or "\\" in cleaned or "/" not in cleaned:
        name = Path(cleaned.split("?")[0]).name
        return name if name and name not in (".", "..") else None
    return None


def _register_upload_refs_conn(
    conn: sqlite3.Connection,
    owner_key: str,
    image_refs: list[str] | None,
) -> None:
    """Record upload filename references in `upload_refs` inside an open SQLite transaction."""
    if not owner_key or not image_refs:
        return
    for ref in image_refs:
        fname = _normalize_upload_filename(ref)
        if fname:
            conn.execute(
                "INSERT OR IGNORE INTO upload_refs (owner_key, upload_filename) VALUES (?, ?)",
                (owner_key, fname),
            )


# `event: dict` is a structured trace event emitted by `AgentTracer` or loaded from legacy JSON.
# `-> set[str]` extracts every valid hex `hash` / `blob_hash` referenced inside the event payload.
def extract_blob_hashes_from_event(event: dict) -> set[str]:
    """Collect all content-addressed blob hashes referenced inside a trace event's `data` payload."""
    hashes: set[str] = set()
    if not isinstance(event, dict):
        return hashes
    data = event.get("data")
    if not isinstance(data, dict):
        return hashes

    manifest = data.get("context_manifest")
    if isinstance(manifest, list):
        for entry in manifest:
            if isinstance(entry, dict):
                h = entry.get("hash") or entry.get("blob_hash")
                if isinstance(h, str) and _HEX_HASH_RE.match(h):
                    hashes.add(h)

    direct_hash = data.get("blob_hash")
    if isinstance(direct_hash, str) and _HEX_HASH_RE.match(direct_hash):
        hashes.add(direct_hash)
    return hashes


# `content: str` is raw text to scrub and deduplicate.
# `kind: str` categorizes the blob (e.g. `"system_prompt"`, `"tool_schemas"`, `"prehydrated_context"`).
# `run_id: str | None` optionally links the blob to a run in `run_blob_refs` in the same operation.
def store_trace_blob(
    content: str,
    kind: str = "text",
    run_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Scrub secrets, SHA-256 hash `content`, deduplicate into `trace_blobs`, and return compact manifest metadata."""
    cleaned = scrub_secrets(content if isinstance(content, str) else str(content or ""))
    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    char_count = len(cleaned)
    approx_tok = approx_token_count(char_count)
    now = datetime.now(timezone.utc).isoformat()

    def _write(active_conn: sqlite3.Connection) -> None:
        active_conn.execute(
            """
            INSERT OR IGNORE INTO trace_blobs (hash, kind, content, char_count, approx_tokens, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (digest, kind, cleaned, char_count, approx_tok, now),
        )
        if run_id:
            # Link only if the parent `runs` row already exists; `append_trace_event_record` also links via manifest
            has_run = active_conn.execute(
                "SELECT 1 FROM runs WHERE run_id = ? LIMIT 1",
                (run_id,),
            ).fetchone()
            if has_run:
                active_conn.execute(
                    "INSERT OR IGNORE INTO run_blob_refs (run_id, blob_hash) VALUES (?, ?)",
                    (run_id, digest),
                )

    if conn is not None:
        _write(conn)
    else:
        with _get_conn() as local_conn:
            _write(local_conn)
            local_conn.commit()

    return {
        "hash": digest,
        "kind": kind,
        "chars": char_count,
        "approx_tokens": approx_tok,
    }


def get_trace_blob(blob_hash: str) -> dict[str, Any] | None:
    """Fetch a single deduplicated blob from `trace_blobs` by SHA-256 hex digest."""
    if not isinstance(blob_hash, str) or not _HEX_HASH_RE.match(blob_hash.strip()):
        raise ValueError(f"Invalid trace blob hash: {blob_hash!r}")
    norm_hash = blob_hash.strip().lower()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT hash, kind, content, char_count, approx_tokens, created_at FROM trace_blobs WHERE hash = ?",
            (norm_hash,),
        ).fetchone()
        return dict(row) if row else None


def get_trace_blobs_batch(blob_hashes: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-fetch multiple `trace_blobs` rows in one indexed SQLite query keyed by hash."""
    if not blob_hashes:
        return {}
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in blob_hashes:
        if not isinstance(raw, str) or not _HEX_HASH_RE.match(raw.strip()):
            raise ValueError(f"Invalid trace blob hash in batch request: {raw!r}")
        h = raw.strip().lower()
        if h not in seen:
            seen.add(h)
            cleaned.append(h)

    if not cleaned:
        return {}

    result: dict[str, dict[str, Any]] = {}
    with _get_conn() as conn:
        # Chunk at 500 parameters to stay well below SQLite's bind parameter limit
        for i in range(0, len(cleaned), 500):
            chunk = cleaned[i : i + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"SELECT hash, kind, content, char_count, approx_tokens, created_at FROM trace_blobs WHERE hash IN ({placeholders})",
                tuple(chunk),
            ).fetchall()
            for r in rows:
                d = dict(r)
                result[d["hash"]] = d
    return result


# ── Unified Run & Live Trace Event Persistence ───────────────────────────────

def _ensure_run_exists_conn(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    thread_id: str | None = None,
    agent_name: str = "nexus",
    query: str = "",
    source: str = "chat",
    model_tier: str | None = None,
    model_name: str | None = None,
    timestamp: str | None = None,
) -> str | None:
    """Insert a `runs` row if missing and resolve `conversation_id` when `thread_id` exists in `conversations`."""
    conv_id: str | None = None
    if thread_id and thread_id != "unspecified":
        conv_row = conn.execute(
            "SELECT 1 FROM conversations WHERE id = ? LIMIT 1",
            (thread_id,),
        ).fetchone()
        if conv_row:
            conv_id = thread_id

    now = timestamp or datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO runs (
            run_id, timestamp, status, source, thread_id, conversation_id,
            agent_name, input_query, model_tier, model_name
        )
        VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            now,
            source,
            thread_id or "unspecified",
            conv_id,
            agent_name or "nexus",
            scrub_secrets(query or ""),
            model_tier,
            model_name,
        ),
    )
    return conv_id


def start_run_record(
    run_id: str,
    thread_id: str | None,
    agent_name: str = "nexus",
    query: str = "",
    source: str = "chat",
    model_tier: str | None = None,
    model_name: str | None = None,
    image_refs: list[str] | None = None,
    timestamp: str | None = None,
) -> str:
    """Create a `runs` row with `status='running'` at turn start so live steps survive crashes."""
    with _get_conn() as conn:
        _ensure_run_exists_conn(
            conn,
            run_id,
            thread_id=thread_id,
            agent_name=agent_name,
            query=query,
            source=source,
            model_tier=model_tier,
            model_name=model_name,
            timestamp=timestamp,
        )
        _register_upload_refs_conn(conn, f"run:{run_id}", image_refs)
        conn.commit()
    return run_id


def append_trace_event_record(run_id: str, event: dict[str, Any]) -> None:
    """Append a single emitted trace event live into `trace_events` and link any referenced `trace_blobs`."""
    if not run_id or not isinstance(event, dict):
        return
    scrubbed_event = scrub_structure(event)
    event_json = json.dumps(scrubbed_event, ensure_ascii=False, default=str)
    blob_hashes = extract_blob_hashes_from_event(scrubbed_event)

    with _get_conn() as conn:
        _ensure_run_exists_conn(
            conn,
            run_id,
            thread_id=scrubbed_event.get("thread_id") or "unspecified",
            agent_name="nexus",
            timestamp=scrubbed_event.get("timestamp"),
        )
        conn.execute(
            """
            INSERT INTO trace_events (run_id, seq, event_json)
            VALUES (?, COALESCE((SELECT MAX(seq) FROM trace_events WHERE run_id = ?), 0) + 1, ?)
            """,
            (run_id, run_id, event_json),
        )
        conn.execute(
            "UPDATE runs SET trace_events_count = trace_events_count + 1 WHERE run_id = ?",
            (run_id,),
        )
        for bh in blob_hashes:
            has_blob = conn.execute("SELECT 1 FROM trace_blobs WHERE hash = ? LIMIT 1", (bh,)).fetchone()
            if has_blob:
                conn.execute(
                    "INSERT OR IGNORE INTO run_blob_refs (run_id, blob_hash) VALUES (?, ?)",
                    (run_id, bh),
                )
        conn.commit()


def finalize_run_record(
    *,
    run_id: str,
    timestamp: str,
    ended_at: str | None,
    status: str,
    source: str,
    thread_id: str | None,
    agent_name: str,
    domain: str | None,
    confidence: float | None,
    reasoning: str | None,
    input_query: str,
    output_response: str,
    model_tier: str | None,
    model_name: str | None,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    reasoning_tokens: int,
    cost_usd: float | None,
    cache_savings_usd: float | None,
    latency_seconds: float | None,
    tool_calls: list[dict[str, Any]],
    subagents_count: int,
    trace_events: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    """Persist or finalize a `runs` row and ensure all `trace_events` + `run_blob_refs` are stored in SQLite."""
    scrubbed_query = scrub_secrets(input_query or "")
    scrubbed_response = scrub_secrets(output_response or "")
    scrubbed_tool_calls = scrub_structure(tool_calls or [])
    scrubbed_meta = scrub_structure(metadata or {})

    with _get_conn() as conn:
        conv_id = _ensure_run_exists_conn(
            conn,
            run_id,
            thread_id=thread_id,
            agent_name=agent_name,
            query=scrubbed_query,
            source=source,
            model_tier=model_tier,
            model_name=model_name,
            timestamp=timestamp,
        )

        # Backfill `trace_events` if live streaming didn't insert them (e.g. direct `log_run()` calls)
        existing_evt_count = conn.execute(
            "SELECT COUNT(*) FROM trace_events WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]

        effective_evt_count = existing_evt_count
        if existing_evt_count == 0 and trace_events:
            scrubbed_events = scrub_structure(trace_events)
            rows_to_insert: list[tuple[str, int, str]] = []
            all_blob_hashes: set[str] = set()
            for seq_idx, evt in enumerate(scrubbed_events, start=1):
                rows_to_insert.append(
                    (run_id, seq_idx, json.dumps(evt, ensure_ascii=False, default=str))
                )
                all_blob_hashes.update(extract_blob_hashes_from_event(evt))

            conn.executemany(
                "INSERT INTO trace_events (run_id, seq, event_json) VALUES (?, ?, ?)",
                rows_to_insert,
            )
            effective_evt_count = len(rows_to_insert)

            for bh in all_blob_hashes:
                has_blob = conn.execute("SELECT 1 FROM trace_blobs WHERE hash = ? LIMIT 1", (bh,)).fetchone()
                if has_blob:
                    conn.execute(
                        "INSERT OR IGNORE INTO run_blob_refs (run_id, blob_hash) VALUES (?, ?)",
                        (run_id, bh),
                    )

        conn.execute(
            """
            UPDATE runs
            SET timestamp = ?,
                ended_at = ?,
                status = ?,
                source = ?,
                thread_id = ?,
                conversation_id = COALESCE(conversation_id, ?),
                agent_name = ?,
                domain = ?,
                confidence = ?,
                reasoning = ?,
                input_query = ?,
                output_response = ?,
                model_tier = ?,
                model_name = ?,
                input_tokens = ?,
                output_tokens = ?,
                cached_tokens = ?,
                reasoning_tokens = ?,
                cost_usd = ?,
                cache_savings_usd = ?,
                latency_seconds = ?,
                tool_calls_json = ?,
                subagents_count = ?,
                trace_events_count = ?,
                metadata_json = ?
            WHERE run_id = ?
            """,
            (
                timestamp,
                ended_at,
                status,
                source,
                thread_id or "unspecified",
                conv_id,
                agent_name,
                domain,
                confidence,
                reasoning,
                scrubbed_query,
                scrubbed_response,
                model_tier,
                model_name,
                int(input_tokens or 0),
                int(output_tokens or 0),
                int(cached_tokens or 0),
                int(reasoning_tokens or 0),
                cost_usd,
                cache_savings_usd,
                round(latency_seconds, 3) if latency_seconds is not None else None,
                json.dumps(scrubbed_tool_calls, ensure_ascii=False, default=str),
                int(subagents_count or 0),
                int(effective_evt_count),
                json.dumps(scrubbed_meta, ensure_ascii=False, default=str),
                run_id,
            ),
        )
        conn.commit()


def list_run_records(limit: int = 50, agent: Optional[str] = None) -> list[dict[str, Any]]:
    """Query indexed `runs` summaries newest-first without scanning JSON files on disk."""
    with _get_conn() as conn:
        if agent:
            rows = conn.execute(
                """
                SELECT * FROM runs
                WHERE lower(agent_name) = lower(?)
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (agent, max(1, int(limit))),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM runs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()

        summaries: list[dict[str, Any]] = []
        for r in rows:
            meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
            tool_calls = json.loads(r["tool_calls_json"]) if r["tool_calls_json"] else []
            full_query = r["input_query"] or ""
            full_response = r["output_response"] or ""
            summaries.append({
                "run_id": r["run_id"],
                "filename": f"{r['run_id']}.sqlite",
                "timestamp": r["timestamp"],
                "status": r["status"],
                "source": r["source"],
                "thread_id": r["thread_id"] or "unspecified",
                "agent_name": r["agent_name"],
                "domain": r["domain"],
                "input_query": full_query,
                "output_response": full_response,
                "query_preview": full_query,
                "response_preview": full_response,
                "latency_seconds": r["latency_seconds"],
                "cost_usd": r["cost_usd"],
                "tool_calls_count": len(tool_calls),
                "subagents_count": r["subagents_count"] or 0,
                "trace_events_count": r["trace_events_count"] or 0,
                "metadata": meta,
            })
        return summaries


def get_run_record(run_id: str) -> dict[str, Any] | None:
    """Load one complete run record and its ordered `trace_events` from SQLite by `run_id`."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE run_id = ? LIMIT 1",
            (run_id,),
        ).fetchone()
        if not row:
            # Support partial ID prefix matching cleanly
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id LIKE ? ORDER BY timestamp DESC LIMIT 1",
                (f"%{run_id}%",),
            ).fetchone()
        if not row:
            return None

        exact_id = row["run_id"]
        evt_rows = conn.execute(
            "SELECT event_json FROM trace_events WHERE run_id = ? ORDER BY seq ASC",
            (exact_id,),
        ).fetchall()
        trace_events: list[dict[str, Any]] = []
        for er in evt_rows:
            try:
                trace_events.append(json.loads(er["event_json"]))
            except Exception:
                continue

        meta = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        tool_calls = json.loads(row["tool_calls_json"]) if row["tool_calls_json"] else []

        return {
            "run_id": exact_id,
            "timestamp": row["timestamp"],
            "ended_at": row["ended_at"],
            "status": row["status"],
            "source": row["source"],
            "thread_id": row["thread_id"] or "unspecified",
            "agent_name": row["agent_name"],
            "domain": row["domain"],
            "confidence": row["confidence"],
            "reasoning": row["reasoning"],
            "input_query": row["input_query"] or "",
            "output_response": row["output_response"] or "",
            "cost_usd": row["cost_usd"],
            "latency_seconds": row["latency_seconds"],
            "tool_calls": tool_calls,
            "subagents_count": row["subagents_count"] or 0,
            "trace_events_count": len(trace_events) or (row["trace_events_count"] or 0),
            "trace_events": trace_events,
            "metadata": meta,
        }


def get_latest_run_record() -> dict[str, Any] | None:
    """Return the newest run record stored in `runs`."""
    with _get_conn() as conn:
        row = conn.execute("SELECT run_id FROM runs ORDER BY timestamp DESC LIMIT 1").fetchone()
    if not row:
        return None
    return get_run_record(row["run_id"])


def delete_run_record(run_id: str) -> bool:
    """Delete a run (cascading `trace_events` + `run_blob_refs`) and reclaim orphaned blobs/uploads."""
    if not run_id:
        return False
    with _get_conn() as conn:
        candidate_hashes = {
            r["blob_hash"]
            for r in conn.execute("SELECT blob_hash FROM run_blob_refs WHERE run_id = ?", (run_id,)).fetchall()
        }
        owner_key = f"run:{run_id}"
        candidate_uploads = {
            r["upload_filename"]
            for r in conn.execute("SELECT upload_filename FROM upload_refs WHERE owner_key = ?", (owner_key,)).fetchall()
        }
        conn.execute("DELETE FROM upload_refs WHERE owner_key = ?", (owner_key,))
        conn.execute("UPDATE messages SET run_id = NULL WHERE run_id = ?", (run_id,))
        cur = conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
        gc_unreferenced_telemetry(
            conn=conn,
            candidate_hashes=candidate_hashes,
            candidate_uploads=candidate_uploads,
            delete_uploads=True,
        )
        conn.commit()
        return cur.rowcount > 0


# ── Canonical LangChain Thread Messages (Replaces LangGraph `memory.sqlite`) ─

def _save_base64_image_to_uploads(mime_subtype: str, b64_payload: str) -> str | None:
    """Decode an inline base64 image once onto `logs/uploads/` and return its `/api/agents/uploads/...` URL."""
    try:
        raw_bytes = base64.b64decode(b64_payload, validate=False)
    except Exception:
        return None
    ext_map = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png", "webp": ".webp", "gif": ".gif", "bmp": ".bmp"}
    ext = ext_map.get(mime_subtype.lower(), ".png")
    digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
    fname = f"migrated_{digest}{ext}"
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOADS_DIR / fname
    if not target.exists():
        target.write_bytes(raw_bytes)
    return f"/api/agents/uploads/{fname}"


def _dehydrate_lc_message_dict(
    msg_dict: dict[str, Any],
    image_refs: list[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Replace inline `data:image/...;base64,...` blocks with lightweight `nexus_image_ref` pointers."""
    copied = json.loads(json.dumps(msg_dict, ensure_ascii=False, default=str))
    data = copied.get("data")
    if not isinstance(data, dict):
        return copied, []

    content = data.get("content")
    tracked_uploads: list[str] = []
    if isinstance(content, list):
        ref_idx = 0
        new_blocks: list[Any] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image_url":
                img_obj = block.get("image_url") if isinstance(block.get("image_url"), dict) else {}
                url = str(img_obj.get("url") or "")
                if url.startswith("data:image/"):
                    mapped_ref: str | None = None
                    if image_refs and ref_idx < len(image_refs):
                        mapped_ref = image_refs[ref_idx]
                    else:
                        m = _DATA_IMAGE_URI_RE.match(url)
                        if m:
                            mapped_ref = _save_base64_image_to_uploads(m.group(1), m.group(2))
                    ref_idx += 1
                    if mapped_ref:
                        fname = _normalize_upload_filename(mapped_ref)
                        if fname:
                            tracked_uploads.append(fname)
                        new_blocks.append({"type": "nexus_image_ref", "url": mapped_ref})
                        continue
            new_blocks.append(block)
        data["content"] = new_blocks

    # Also track any explicitly supplied image refs even if block didn't start with `data:`
    if image_refs:
        for ref in image_refs:
            fname = _normalize_upload_filename(ref)
            if fname and fname not in tracked_uploads:
                tracked_uploads.append(fname)

    return copied, tracked_uploads


def _rehydrate_lc_message_dict(
    msg_dict: dict[str, Any],
    image_resolver: Optional[Callable[[str], str]] = None,
) -> dict[str, Any]:
    """Expand `nexus_image_ref` placeholders back into provider-ready `image_url` data URIs or safe text."""
    copied = json.loads(json.dumps(msg_dict))
    data = copied.get("data")
    if not isinstance(data, dict):
        return copied

    content = data.get("content")
    if isinstance(content, list):
        new_blocks: list[Any] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "nexus_image_ref":
                url = str(block.get("url") or "")
                if image_resolver and url:
                    try:
                        resolved_data_url = image_resolver(url)
                        new_blocks.append({"type": "image_url", "image_url": {"url": resolved_data_url}})
                        continue
                    except Exception:
                        pass
                new_blocks.append({"type": "text", "text": f"[Attached Image: {url or 'unavailable'}]"})
            else:
                new_blocks.append(block)
        data["content"] = new_blocks
    return copied


def append_thread_lc_messages(
    thread_id: str,
    new_messages: list[BaseMessage],
    *,
    turn_id: str | None = None,
    image_refs: list[str] | None = None,
) -> None:
    """Persist incremental LangChain `BaseMessage` objects for `thread_id` losslessly (preserving signatures & tool calls)."""
    if not thread_id or not new_messages:
        return
    serialized = messages_to_dict(list(new_messages))
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        for item in serialized:
            msg_type = str(item.get("type") or "unknown")
            refs_for_msg = image_refs if msg_type == "human" else None
            dehydrated, tracked_uploads = _dehydrate_lc_message_dict(item, image_refs=refs_for_msg)
            conn.execute(
                """
                INSERT INTO thread_messages (thread_id, turn_id, msg_type, msg_json, blob_hash, created_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (thread_id, turn_id, msg_type, json.dumps(dehydrated, ensure_ascii=False, default=str), now),
            )
            if turn_id and tracked_uploads:
                _register_upload_refs_conn(conn, f"run:{turn_id}", tracked_uploads)
        conn.commit()


def replace_thread_lc_messages(
    thread_id: str,
    messages: list[BaseMessage],
    *,
    turn_id: str | None = None,
) -> None:
    """Replace the canonical `thread_messages` sequence for `thread_id` atomically."""
    if not thread_id:
        return
    serialized = messages_to_dict(list(messages))
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute("DELETE FROM thread_messages WHERE thread_id = ?", (thread_id,))
        for item in serialized:
            msg_type = str(item.get("type") or "unknown")
            dehydrated, _ = _dehydrate_lc_message_dict(item)
            conn.execute(
                """
                INSERT INTO thread_messages (thread_id, turn_id, msg_type, msg_json, blob_hash, created_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (thread_id, turn_id, msg_type, json.dumps(dehydrated, ensure_ascii=False, default=str), now),
            )
        conn.commit()


def load_thread_lc_messages(
    thread_id: str,
    image_resolver: Optional[Callable[[str], str]] = None,
) -> list[BaseMessage]:
    """Load the ordered LangChain `BaseMessage` history for `thread_id` from `thread_messages` (with `messages` fallback)."""
    if not thread_id:
        return []

    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT msg_json FROM thread_messages WHERE thread_id = ? ORDER BY id ASC",
            (thread_id,),
        ).fetchall()

        if rows:
            raw_dicts: list[dict[str, Any]] = []
            for r in rows:
                try:
                    raw_dicts.append(_rehydrate_lc_message_dict(json.loads(r["msg_json"]), image_resolver=image_resolver))
                except Exception:
                    continue
            return list(messages_from_dict(raw_dicts)) if raw_dicts else []

        # Fallback: reconstruct completed turns from `messages` if `thread_messages` has not been seeded yet.
        # Guard against Turn-1 duplication: `agents.py` & `telegram_bridge.py` persist the active `user` message
        # into `messages` *before* calling `run_nexus_agent_with_trace`, so strip a trailing `user` row here!
        msg_rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (thread_id,),
        ).fetchall()
        if not msg_rows:
            return []
        if msg_rows[-1]["role"] == "user":
            msg_rows = msg_rows[:-1]
        if not msg_rows:
            return []

        lc_msgs: list[BaseMessage] = []
        for r in msg_rows:
            body = r["content"] or ""
            if r["role"] == "user":
                lc_msgs.append(HumanMessage(content=body))
            else:
                lc_msgs.append(AIMessage(content=body))
        if lc_msgs and isinstance(lc_msgs[0], AIMessage):
            lc_msgs.insert(0, HumanMessage(content="[Prior conversation context restored from history]"))
        return lc_msgs


# ── Garbage Collection (Reference-Counted Blobs & Uploads) ───────────────────

def gc_unreferenced_telemetry(
    conn: sqlite3.Connection | None = None,
    candidate_hashes: set[str] | None = None,
    candidate_uploads: set[str] | None = None,
    delete_uploads: bool = True,
    uploads_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Delete unreferenced `trace_blobs` rows and (optionally) unreferenced `logs/uploads/` files."""
    target_uploads_dir = (uploads_dir or UPLOADS_DIR).resolve()

    def _run_gc(active_conn: sqlite3.Connection) -> dict[str, int]:
        deleted_blobs = 0
        deleted_uploads = 0

        if candidate_hashes is not None:
            valid_candidates = [h for h in candidate_hashes if isinstance(h, str) and _HEX_HASH_RE.match(h)]
            for i in range(0, len(valid_candidates), 400):
                chunk = valid_candidates[i : i + 400]
                ph = ",".join("?" for _ in chunk)
                if dry_run:
                    cnt = active_conn.execute(
                        f"""
                        SELECT COUNT(*) FROM trace_blobs
                        WHERE hash IN ({ph})
                          AND NOT EXISTS (SELECT 1 FROM run_blob_refs WHERE blob_hash = trace_blobs.hash)
                          AND NOT EXISTS (SELECT 1 FROM thread_messages WHERE blob_hash = trace_blobs.hash)
                        """,
                        tuple(chunk),
                    ).fetchone()[0]
                    deleted_blobs += int(cnt)
                else:
                    cur = active_conn.execute(
                        f"""
                        DELETE FROM trace_blobs
                        WHERE hash IN ({ph})
                          AND NOT EXISTS (SELECT 1 FROM run_blob_refs WHERE blob_hash = trace_blobs.hash)
                          AND NOT EXISTS (SELECT 1 FROM thread_messages WHERE blob_hash = trace_blobs.hash)
                        """,
                        tuple(chunk),
                    )
                    deleted_blobs += cur.rowcount
        else:
            if dry_run:
                deleted_blobs = int(
                    active_conn.execute(
                        """
                        SELECT COUNT(*) FROM trace_blobs
                        WHERE NOT EXISTS (SELECT 1 FROM run_blob_refs WHERE blob_hash = trace_blobs.hash)
                          AND NOT EXISTS (SELECT 1 FROM thread_messages WHERE blob_hash = trace_blobs.hash)
                        """
                    ).fetchone()[0]
                )
            else:
                cur = active_conn.execute(
                    """
                    DELETE FROM trace_blobs
                    WHERE NOT EXISTS (SELECT 1 FROM run_blob_refs WHERE blob_hash = trace_blobs.hash)
                      AND NOT EXISTS (SELECT 1 FROM thread_messages WHERE blob_hash = trace_blobs.hash)
                    """
                )
                deleted_blobs = cur.rowcount

        if delete_uploads and target_uploads_dir.is_dir():
            files_to_check: list[str] = []
            if candidate_uploads is not None:
                files_to_check = [f for f in candidate_uploads if f]
            else:
                # Full sweep: check disk uploads older than 1 hour that have 0 refs in `upload_refs` or `messages.images`
                cutoff = time.time() - 3600.0
                known_msg_imgs: set[str] = set()
                for mr in active_conn.execute("SELECT images FROM messages WHERE images IS NOT NULL").fetchall():
                    try:
                        for img_ref in json.loads(mr["images"]) or []:
                            fn = _normalize_upload_filename(img_ref)
                            if fn:
                                known_msg_imgs.add(fn)
                    except Exception:
                        continue
                for p in target_uploads_dir.iterdir():
                    if p.is_file():
                        try:
                            if p.stat().st_mtime < cutoff and p.name not in known_msg_imgs:
                                files_to_check.append(p.name)
                        except OSError:
                            continue

            for fname in files_to_check:
                safe_name = Path(fname).name
                if not safe_name or safe_name != fname:
                    continue
                ref_exists = active_conn.execute(
                    "SELECT 1 FROM upload_refs WHERE upload_filename = ? LIMIT 1",
                    (safe_name,),
                ).fetchone()
                if ref_exists:
                    continue
                candidate_path = (target_uploads_dir / safe_name).resolve()
                if not candidate_path.is_relative_to(target_uploads_dir) or not candidate_path.is_file():
                    continue
                if dry_run:
                    deleted_uploads += 1
                else:
                    try:
                        candidate_path.unlink()
                        deleted_uploads += 1
                    except OSError:
                        pass

        return {"deleted_blobs": deleted_blobs, "deleted_uploads": deleted_uploads}

    if conn is not None:
        return _run_gc(conn)

    with _get_conn() as local_conn:
        stats = _run_gc(local_conn)
        if not dry_run:
            local_conn.commit()
        return stats


# ── Conversation & Message CRUD ──────────────────────────────────────────────

def create_conversation(
    title: str = "New Chat",
    title_source: str = "placeholder",
    last_model_tier: str | None = None,
    last_model_name: str | None = None,
) -> str:
    """
    Creates a new root conversation row in `chats.db`.

    Parameters:
      title: Initial display title (typically `"New Chat"` or a truncated first-prompt placeholder).
      title_source: Provenance tag (`"placeholder"`, `"auto"`, or `"manual"`). Defaults to `"placeholder"`
                    so background Turn-1 auto-titling upgrades it safely without overwriting manual edits.
      last_model_tier: Optional initial model capability tier (`"strong"`, `"medium"`, `"low"`) selected for the thread.
      last_model_name: Optional concrete model identifier (e.g. `"claude-opus-5-5"`) selected for the thread.
    """
    conv_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO conversations (
                id, title, created_at, last_updated, title_source, last_model_tier, last_model_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (conv_id, title, now, now, title_source, last_model_tier, last_model_name),
        )
        conn.commit()
    return conv_id


def create_branch_conversation(
    title: str,
    parent_conversation_id: str,
    parent_message_id: int | None = None,
    branch_mode: str = "tangent",
    title_source: str = "placeholder",
    last_model_tier: str | None = None,
    last_model_name: str | None = None,
) -> str:
    """
    Creates a new branched child conversation in `chats.db` linked to its parent thread and fork message.

    Parameters:
      title: Display title for the newly forked child branch.
      parent_conversation_id: UUID of the parent conversation from which this branch was spawned.
      parent_message_id: Optional SQLite `messages.id` in the parent conversation where the fork occurred.
      branch_mode: Either `'tangent'` (context-sliced fresh ALU) or `'fork'` (full history clone up to branch point).
      title_source: Provenance tag (`"placeholder"` for auto-derived branch snippets, `"manual"` for explicit titles).
      last_model_tier: Optional inherited model tier from the parent conversation or fork slice.
      last_model_name: Optional inherited concrete model identifier from the parent conversation or fork slice.

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
                parent_conversation_id, parent_message_id, branch_mode, merged_at, title_source,
                last_model_tier, last_model_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (
                conv_id,
                title,
                now,
                now,
                parent_conversation_id,
                parent_message_id,
                branch_mode,
                title_source,
                last_model_tier,
                last_model_name,
            ),
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
        # Gather candidate run IDs (by conversation_id/thread_id or message linkage), blob hashes, and uploads
        run_id_set = {
            r["run_id"]
            for r in conn.execute(
                "SELECT run_id FROM runs WHERE conversation_id = ? OR thread_id = ?",
                (conversation_id, conversation_id),
            ).fetchall()
            if r["run_id"]
        }
        for r in conn.execute(
            "SELECT DISTINCT run_id FROM messages WHERE conversation_id = ? AND run_id IS NOT NULL",
            (conversation_id,),
        ).fetchall():
            if r["run_id"]:
                run_id_set.add(r["run_id"])
        run_ids = list(run_id_set)
        msg_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
        ]

        candidate_hashes: set[str] = set()
        candidate_uploads: set[str] = set()
        if run_ids:
            ph = ",".join("?" for _ in run_ids)
            for row in conn.execute(
                f"SELECT blob_hash FROM run_blob_refs WHERE run_id IN ({ph})",
                tuple(run_ids),
            ).fetchall():
                candidate_hashes.add(row["blob_hash"])

        owner_keys = [f"run:{rid}" for rid in run_ids] + [f"msg:{mid}" for mid in msg_ids]
        if owner_keys:
            ph = ",".join("?" for _ in owner_keys)
            for row in conn.execute(
                f"SELECT upload_filename FROM upload_refs WHERE owner_key IN ({ph})",
                tuple(owner_keys),
            ).fetchall():
                candidate_uploads.add(row["upload_filename"])
            conn.execute(f"DELETE FROM upload_refs WHERE owner_key IN ({ph})", tuple(owner_keys))

        # Promote any child branches to root level so deleting a parent never orphans child threads
        conn.execute(
            "UPDATE conversations SET parent_conversation_id = NULL WHERE parent_conversation_id = ?",
            (conversation_id,),
        )
        # Purge canonical thread messages, runs (cascades trace_events + run_blob_refs), captures, and messages
        conn.execute("DELETE FROM thread_messages WHERE thread_id = ?", (conversation_id,))
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        if run_ids:
            ph = ",".join("?" for _ in run_ids)
            conn.execute(f"DELETE FROM runs WHERE run_id IN ({ph})", tuple(run_ids))
        conn.execute("DELETE FROM conversation_captures WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

        gc_unreferenced_telemetry(
            conn=conn,
            candidate_hashes=candidate_hashes,
            candidate_uploads=candidate_uploads,
            delete_uploads=True,
        )
        conn.commit()
    # Purge any cached instruction-hydration ledger entries for this thread and its `:subagent-*` children.
    from nexus.core.instruction_guard import clear_seen_instructions

    clear_seen_instructions(conversation_id)


# `*` enforces keyword-only optional guards so legacy positional callers `update_conversation_title(id, title)` remain compatible
def update_conversation_title(
    conversation_id: str,
    title: str,
    *,
    source: str = "manual",
    expected_title: str | None = None,
    only_if_placeholder: bool = False,
) -> bool:
    """
    Updates a conversation's title and `title_source` atomically in SQLite `chats.db`.

    Parameters:
      conversation_id: UUID of the target conversation row.
      title: New display title string.
      source: Provenance label (`"manual"`, `"auto"`, or `"placeholder"`).
      expected_title: Optional compare-and-swap (CAS) guard; when set, the UPDATE commits only if the
                      stored title still matches `expected_title` (preventing stale LLM jobs from clobbering edits).
      only_if_placeholder: When True, restricts the UPDATE to rows whose `title_source` is still `"placeholder"`.

    Returns:
      True if the row was updated; False if no matching row met the atomic CAS / provenance conditions.
    """
    clauses = ["id = ?"]
    params: list[str] = [title, source, conversation_id]

    if expected_title is not None:
        clauses.append("title = ?")
        params.append(expected_title)
    if only_if_placeholder:
        clauses.append("COALESCE(title_source, 'placeholder') = 'placeholder'")

    sql = f"UPDATE conversations SET title = ?, title_source = ? WHERE {' AND '.join(clauses)}"
    with _get_conn() as conn:
        cursor = conn.execute(sql, tuple(params))
        conn.commit()
        return cursor.rowcount > 0


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
    run_id: str | None = None,
) -> int | None:
    if not conversation_id:
        return None

    with _get_conn() as conn:
        now = datetime.now(timezone.utc).isoformat()
        # Ensure parent `conversations` row exists so PRAGMA foreign_keys = ON never rejects standalone callers
        conn.execute(
            """
            INSERT OR IGNORE INTO conversations (id, title, created_at, last_updated, title_source)
            VALUES (?, 'New Chat', ?, ?, 'placeholder')
            """,
            (conversation_id, now, now),
        )

        images_json = json.dumps(images) if images else None
        effective_run_id = run_id
        has_run_trace = False
        if effective_run_id:
            has_run_trace = bool(
                conn.execute("SELECT 1 FROM trace_events WHERE run_id = ? LIMIT 1", (effective_run_id,)).fetchone()
            )
        elif trace and len(trace) > 0:
            # Normalize callers/tests passing an inline `trace` list directly into `runs` + `trace_events`
            effective_run_id = f"msg-{uuid.uuid4().hex[:10]}"
            scrubbed_trace = scrub_structure(trace)
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, timestamp, ended_at, status, source, thread_id, conversation_id,
                    agent_name, domain, confidence, input_query, output_response,
                    model_tier, model_name, cost_usd, trace_events_count, metadata_json
                )
                VALUES (?, ?, ?, 'done', 'chat', ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, '{}')
                """,
                (
                    effective_run_id,
                    now,
                    now,
                    conversation_id,
                    conversation_id,
                    agent or "nexus",
                    domain,
                    confidence,
                    scrub_secrets(content or ""),
                    model_tier,
                    model_name,
                    cost_usd,
                    len(scrubbed_trace),
                ),
            )
            conn.executemany(
                "INSERT INTO trace_events (run_id, seq, event_json) VALUES (?, ?, ?)",
                [
                    (effective_run_id, idx, json.dumps(evt, ensure_ascii=False, default=str))
                    for idx, evt in enumerate(scrubbed_trace, start=1)
                ],
            )
            has_run_trace = True

        has_trace = 1 if (has_run_trace or (trace and len(trace) > 0)) else 0

        # Primary messages table row stays lean: trace column remains NULL and `run_id` points to live `trace_events`
        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, role, content, agent, domain, confidence,
                trace, timestamp, images, model_tier, model_name, cost_usd, has_trace, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                content,
                agent,
                domain,
                confidence,
                now,
                images_json,
                model_tier,
                model_name,
                cost_usd,
                has_trace,
                effective_run_id,
            ),
        )

        msg_id = int(cursor.lastrowid) if cursor.lastrowid is not None else None
        if msg_id is not None and images:
            _register_upload_refs_conn(conn, f"msg:{msg_id}", images)

        # Only overwrite remembered model metadata when this message actually carries model attribution;
        # synthetic entries (`branch_context`, `branch_merge`) and error logs pass None and must preserve prior state
        if model_tier or model_name:
            conn.execute(
                "UPDATE conversations SET last_updated = ?, last_model_tier = ?, last_model_name = ? WHERE id = ?",
                (now, model_tier, model_name, conversation_id),
            )
        else:
            conn.execute("UPDATE conversations SET last_updated = ? WHERE id = ?", (now, conversation_id))
        conn.commit()
        return msg_id


def _load_trace_events_for_run_conn(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT event_json FROM trace_events WHERE run_id = ? ORDER BY seq ASC",
        (run_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            out.append(json.loads(r["event_json"]))
        except Exception:
            continue
    return out


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
        query = """
            SELECT id, role, content, agent, domain, confidence,
                   timestamp, images, model_tier, model_name, cost_usd, has_trace, run_id
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
            raw_images = r["images"] if "images" in r.keys() else None
            parsed_images = json.loads(raw_images) if raw_images else []

            if include_trace:
                run_id = r["run_id"] if "run_id" in r.keys() else None
                trace_events = _load_trace_events_for_run_conn(conn, run_id) if run_id else []
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
                "run_id": r["run_id"] if "run_id" in r.keys() else None,
            })
        return history


def get_message_trace(message_id: int) -> list[dict]:
    """
    Retrieves the full, untruncated trace events array for a specific message ID on demand via `messages.run_id`.
    """
    with _get_conn() as conn:
        msg_row = conn.execute(
            "SELECT run_id FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if msg_row and msg_row["run_id"]:
            return _load_trace_events_for_run_conn(conn, msg_row["run_id"])
        return []


def revert_last_turn(conversation_id: str) -> dict | None:
    """
    Reverts the latest turn in a conversation by deleting its messages, run telemetry, and canonical
    `thread_messages` turn rows from SQLite `chats.db` (while keeping `restored_images` on disk for composer recovery).
    """
    if not conversation_id:
        return None

    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, images, run_id, timestamp
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

        if not rows:
            return None

        last_row = rows[-1]
        ids_to_delete: list[int] = []
        run_ids_to_delete: set[str] = set()
        restored_query = ""
        restored_images: list[str] = []
        user_turn_ts: str | None = None

        if last_row["role"] == "assistant":
            ids_to_delete.append(last_row["id"])
            if last_row["run_id"]:
                run_ids_to_delete.add(last_row["run_id"])
            for r in reversed(rows[:-1]):
                if r["role"] == "user":
                    ids_to_delete.append(r["id"])
                    restored_query = r["content"] or ""
                    raw_images = r["images"] if "images" in r.keys() else None
                    restored_images = json.loads(raw_images) if raw_images else []
                    user_turn_ts = r["timestamp"]
                    if r["run_id"]:
                        run_ids_to_delete.add(r["run_id"])
                    break
        elif last_row["role"] == "user":
            # Mid-turn abort: only the user prompt exists at the tail of the message log
            ids_to_delete.append(last_row["id"])
            restored_query = last_row["content"] or ""
            raw_images = last_row["images"] if "images" in last_row.keys() else None
            restored_images = json.loads(raw_images) if raw_images else []
            user_turn_ts = last_row["timestamp"]
            if last_row["run_id"]:
                run_ids_to_delete.add(last_row["run_id"])

        # Also capture any in-flight `running` run or run started at/after the reverted user prompt
        for rr in conn.execute(
            """
            SELECT run_id, status, timestamp FROM runs
            WHERE (conversation_id = ? OR thread_id = ?)
              AND (status = 'running' OR (? IS NOT NULL AND timestamp >= ?))
            """,
            (conversation_id, conversation_id, user_turn_ts, user_turn_ts),
        ).fetchall():
            run_ids_to_delete.add(rr["run_id"])

        if ids_to_delete:
            candidate_hashes: set[str] = set()
            if run_ids_to_delete:
                rph = ",".join("?" for _ in run_ids_to_delete)
                for row in conn.execute(
                    f"SELECT blob_hash FROM run_blob_refs WHERE run_id IN ({rph})",
                    tuple(run_ids_to_delete),
                ).fetchall():
                    candidate_hashes.add(row["blob_hash"])
                # Clear `thread_messages` for reverted turn IDs before deleting the runs
                conn.execute(
                    f"DELETE FROM thread_messages WHERE thread_id = ? AND turn_id IN ({rph})",
                    (conversation_id, *run_ids_to_delete),
                )
            else:
                # Fallback when reverting an untagged turn: drop from the last human turn boundary onward
                last_human = conn.execute(
                    "SELECT id FROM thread_messages WHERE thread_id = ? AND msg_type = 'human' ORDER BY id DESC LIMIT 1",
                    (conversation_id,),
                ).fetchone()
                if last_human:
                    conn.execute(
                        "DELETE FROM thread_messages WHERE thread_id = ? AND id >= ?",
                        (conversation_id, last_human["id"]),
                    )

            owner_keys = [f"msg:{mid}" for mid in ids_to_delete] + [f"run:{rid}" for rid in run_ids_to_delete]
            oph = ",".join("?" for _ in owner_keys)
            conn.execute(f"DELETE FROM upload_refs WHERE owner_key IN ({oph})", tuple(owner_keys))

            placeholders = ",".join("?" for _ in ids_to_delete)
            conn.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", ids_to_delete)

            if run_ids_to_delete:
                rph = ",".join("?" for _ in run_ids_to_delete)
                conn.execute(f"DELETE FROM runs WHERE run_id IN ({rph})", tuple(run_ids_to_delete))

            # Reclaim zero-ref trace blobs immediately while preserving `restored_images` on disk!
            if candidate_hashes:
                gc_unreferenced_telemetry(
                    conn=conn,
                    candidate_hashes=candidate_hashes,
                    delete_uploads=False,
                )

            latest_model_row = conn.execute(
                """
                SELECT model_tier, model_name
                FROM messages
                WHERE conversation_id = ?
                  AND (model_name IS NOT NULL OR model_tier IS NOT NULL)
                ORDER BY id DESC
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
            next_tier = latest_model_row["model_tier"] if latest_model_row else None
            next_name = latest_model_row["model_name"] if latest_model_row else None
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE conversations SET last_updated = ?, last_model_tier = ?, last_model_name = ? WHERE id = ?",
                (now, next_tier, next_name, conversation_id),
            )
            conn.commit()

            return {
                "restored_query": restored_query,
                "images": restored_images,
                "deleted_count": len(ids_to_delete),
            }

        return None
