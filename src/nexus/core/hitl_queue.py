import sqlite3
import json
# difflib: Stdlib sequence differ; SequenceMatcher yields line-level edit opcodes used by the 3-way rebase merge
import difflib
# os.replace: Atomic rename on the same volume (POSIX + Windows), so readers never see a half-written note
import os
import shutil
# threading.RLock: Re-entrant process lock allowing the same thread to acquire the lock multiple times
# (e.g., modify_file holding the lock while calling add_transaction) without causing a self-deadlock.
# defaultdict: Automatically instantiates a new RLock on first access for any unseen target file path.
import threading
from collections import defaultdict
# contextvars.ContextVar: Thread- and async-safe context storage that automatically propagates across
# LangGraph's `ContextThreadPoolExecutor` (`ToolNode`) while keeping parallel subagent branches isolated.
from contextvars import ContextVar, Token
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# DB_PATH: Resolves to `src/nexus/hitl.db`, the SQLite ledger for Two-Phase Commit (HITL) file mutations
DB_PATH = Path(__file__).resolve().parent.parent / "hitl.db"

# _hitl_execution_context: Holds the active turn/subagent provenance (`conversation_id`, `thread_id`,
# `agent_id`, `agent_role`) so `modify_file` and `create_file` automatically record full lineage in `hitl.db`.
_hitl_execution_context: ContextVar[Optional[Dict[str, Optional[str]]]] = ContextVar(
    "hitl_execution_context",
    default=None,
)


def set_hitl_execution_context(
    conversation_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    agent_role: Optional[str] = None,
) -> Token:
    """Sets or updates the execution provenance (`conversation_id`, `thread_id`, `agent_id`, `agent_role`) in the current `ContextVar`.

    Returns:
        Token: A contextvars reset token that callers (e.g. `spawn_subagent`) can pass to `reset_hitl_execution_context(token)`
        in a `finally` block so synchronous single-thread fallbacks cleanly restore the parent agent's provenance.
    """
    current = dict(_hitl_execution_context.get() or {})
    if conversation_id is not None:
        current["conversation_id"] = conversation_id
    if thread_id is not None:
        current["thread_id"] = thread_id
    if agent_id is not None:
        current["agent_id"] = agent_id
    if agent_role is not None:
        current["agent_role"] = agent_role
    return _hitl_execution_context.set(current)


def reset_hitl_execution_context(token: Token) -> None:
    """Restores `_hitl_execution_context` to its prior snapshot using the `Token` returned by `set_hitl_execution_context`."""
    _hitl_execution_context.reset(token)


def get_hitl_execution_context() -> Dict[str, Optional[str]]:
    """Returns a copy of the active HITL execution provenance (`conversation_id`, `thread_id`, `agent_id`, `agent_role`)."""
    return dict(_hitl_execution_context.get() or {})

# _file_mutation_locks: Per-target-file mutexes ensuring concurrent tool calls serialize their
# inspection of pending staged state, surgical replacement, and transaction insertion/updates.
_file_mutation_locks: Dict[str, threading.RLock] = defaultdict(threading.RLock)
_file_mutation_locks_guard = threading.Lock()


def get_file_mutation_lock(target_file: str) -> threading.RLock:
    """Returns a process-wide re-entrant mutex (`threading.RLock`) for `target_file`.

    Ensures concurrent tool calls (e.g. LangChain `ToolNode` worker threads) modifying the same
    Vault note serialize their check of staged pending state, surgical replacements, and database
    transactions so edits stack cumulatively into a single review card rather than creating race conditions.

    Args:
        target_file: Vault-relative or normalized target file path (e.g. 'Vault/Tasks.md').

    Returns:
        threading.RLock: The dedicated re-entrant mutex for this normalized file path.
    """
    norm = _normalize_target_file(target_file)
    with _file_mutation_locks_guard:
        return _file_mutation_locks[norm]


# ── Commit-Integrity Errors ─────────────────────────────────────────────────
# Custom exceptions let the API layer map engine failures to precise HTTP codes (409 vs 400 vs 404)
# without the engine importing FastAPI (keeps `core/` framework-agnostic).


class HitlCommitError(Exception):
    """Base class for HITL commit/rollback failures (invalid state, unsafe path, nothing to roll back)."""


class TransactionNotFoundError(HitlCommitError):
    """Raised when a transaction ID does not exist in `hitl.db` (mapped to HTTP 404)."""


class StaleBaseError(HitlCommitError):
    """Raised when the note on disk no longer matches the baseline the agent's edit was staged against.

    Attributes:
        current_content: Text currently on disk (`None` if the file was deleted) so the GUI can render
            a 3-way comparison (current disk vs agent baseline vs agent proposal).
    """

    def __init__(self, message: str, current_content: Optional[str]):
        super().__init__(message)
        self.current_content = current_content


class MergeConflictError(HitlCommitError):
    """Raised when a rebase cannot cleanly merge human edits and agent edits (overlapping line regions)."""


def _normalize_target_file(target_file: str) -> str:
    """Normalizes Vault target paths (`\\` -> `/`, ensures `Vault/` prefix) so per-file queue lookups never miss."""
    clean = (target_file or "").strip().replace("\\", "/").lstrip("/")
    if clean and not clean.startswith("Vault/"):
        clean = f"Vault/{clean}"
    return clean


def get_db_connection():
    """Opens a SQLite connection to `hitl.db` with dictionary row access and WAL concurrency mode.

    Write-Ahead Logging (WAL) ensures concurrent agent tool calls staging proposals do not block
    human review queries in the Control Panel or background approval checks.
    """
    # timeout=30.0: Waits up to 30 seconds for pending transactions or snapshot rollbacks to settle
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_file TEXT NOT NULL,
            original_content TEXT,
            proposed_content TEXT NOT NULL,
            reasoning TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            conversation_id TEXT,
            thread_id TEXT,
            agent_id TEXT,
            agent_role TEXT,
            destination_file TEXT
        )
    ''')
    # Idempotent schema migration: add provenance and destination_file columns to existing hitl.db files
    cursor.execute("PRAGMA table_info(transactions)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    for col_name in ("conversation_id", "thread_id", "agent_id", "agent_role", "destination_file"):
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} TEXT")

    # revisions: Pre-commit snapshot ledger enabling one-click rollback of approved transactions.
    #   prior_content NULL      -> file did not exist before approval (rollback deletes it)
    #   applied_content         -> exact text written on approval (rollback refuses if disk drifted, unless forced)
    #   overwritten_content     -> text clobbered by a *forced* rollback, kept so even that action is recoverable
    #   destination_file        -> target destination path for atomic file move transactions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_id INTEGER NOT NULL,
            target_file TEXT NOT NULL,
            prior_content TEXT,
            applied_content TEXT NOT NULL,
            rolled_back INTEGER DEFAULT 0,
            overwritten_content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            rolled_back_at TIMESTAMP,
            destination_file TEXT
        )
    ''')
    cursor.execute("PRAGMA table_info(revisions)")
    existing_rev_cols = {row["name"] for row in cursor.fetchall()}
    for col_name in ("destination_file",):
        if col_name not in existing_rev_cols:
            cursor.execute(f"ALTER TABLE revisions ADD COLUMN {col_name} TEXT")
    conn.commit()
    conn.close()


def get_pending_for_file(target_file: str) -> Optional[Dict[str, Any]]:
    """Returns the active pending HITL transaction for `target_file`, if one exists.

    Also matches when `target_file` is supplied as a short filename (e.g. `"Plan.md"`) by checking
    exact normalized path first and falling back to unique basename suffix match (`%/<filename>`).
    Also matches across `destination_file` for pending file move operations.
    Used by `read_file`, `modify_file`, `move_file`, and `create_file` so agents read and stack edits
    on top of already-staged `proposed_content` instead of reading stale disk state and
    creating conflicting duplicate transactions for the same note.
    """
    norm_target = _normalize_target_file(target_file)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT * FROM transactions
        WHERE status = 'pending' AND (
            REPLACE(target_file, '\\', '/') = ?
            OR (destination_file IS NOT NULL AND REPLACE(destination_file, '\\', '/') = ?)
        )
        ORDER BY id DESC
        LIMIT 1
        ''',
        (norm_target, norm_target),
    )
    row = cursor.fetchone()
    if row is None and "/" not in (target_file or "").strip().replace("\\", "/").lstrip("/"):
        # Fallback: match unique filename suffix (e.g., `read_file("Plan.md")` or newly staged Event note)
        basename = (target_file or "").strip()
        if not basename.endswith(".md") and "." not in basename:
            basename += ".md"
        cursor.execute(
            '''
            SELECT * FROM transactions
            WHERE status = 'pending' AND (
                REPLACE(target_file, '\\', '/') LIKE ?
                OR (destination_file IS NOT NULL AND REPLACE(destination_file, '\\', '/') LIKE ?)
            )
            ORDER BY id DESC
            LIMIT 1
            ''',
            (f"%/{basename}", f"%/{basename}"),
        )
        row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _merge_reasoning(existing_reasoning: Optional[str], new_reasoning: Optional[str]) -> str:
    """Combines reasoning strings into a clean bulleted audit log when multiple edits stack onto one file."""
    old_r = (existing_reasoning or "").strip()
    new_r = (new_reasoning or "").strip()
    if not old_r:
        return new_r
    if not new_r or new_r in old_r:
        return old_r
    if not old_r.startswith("• "):
        old_r = f"• {old_r}"
    if not new_r.startswith("• "):
        new_r = f"• {new_r}"
    return f"{old_r}\n{new_r}"


def add_transaction(
    agent_name: str,
    action_type: str,
    target_file: str,
    proposed_content: str,
    original_content: str = None,
    reasoning: str = None,
    conversation_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    agent_role: Optional[str] = None,
    destination_file: Optional[str] = None,
) -> int:
    """Inserts a pending HITL transaction or coalesces in-place if `target_file` already has a pending edit.

    Automatically enriches the row with `conversation_id`, `thread_id`, `agent_id`, and `agent_role` from
    `get_hitl_execution_context()` when not explicitly supplied by the caller.
    Supports atomic file moves (`action_type="move"` / `"move_file"`) by storing `destination_file`,
    and file deletions (`action_type="delete"` / `"delete_file"`).

    Cumulative Overlay Stacking:
      - If `target_file` already has one or more `status = 'pending'` rows, we preserve the earliest
        pending row's `original_content` (the true on-disk baseline before any pending edits),
        update the newest pending row in place with the cumulative `proposed_content` and merged `reasoning`,
        and mark any older duplicate pending rows for that file as `'superseded'`.
      - This guarantees at most ONE pending review card per file in the HITL Control Panel.
    """
    ctx = get_hitl_execution_context()
    eff_convo_id = conversation_id if conversation_id is not None else ctx.get("conversation_id")
    eff_thread_id = thread_id if thread_id is not None else ctx.get("thread_id")
    eff_agent_id = agent_id if agent_id is not None else (ctx.get("agent_id") or ("nexus" if agent_name in ("nexus_agent", "nexus", "NexusAgent") else agent_name))
    eff_agent_role = agent_role if agent_role is not None else (ctx.get("agent_role") or ("Commander" if agent_name in ("nexus_agent", "nexus", "NexusAgent") else agent_name))
    eff_agent_name = ctx.get("agent_role") or agent_role or agent_name

    norm_target = _normalize_target_file(target_file)
    norm_dest = _normalize_target_file(destination_file) if destination_file else None
    with get_file_mutation_lock(norm_target):
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT * FROM transactions
            WHERE status = 'pending' AND REPLACE(target_file, '\\', '/') = ?
            ORDER BY id ASC
            ''',
            (norm_target,),
        )
        existing_rows = [dict(r) for r in cursor.fetchall()]

        if existing_rows:
            oldest = existing_rows[0]
            newest = existing_rows[-1]
            tx_id = int(newest["id"])

            # Explicit move or delete takes precedence; otherwise preserve earliest pending 'create'
            if action_type in ("delete", "delete_file", "move", "move_file"):
                baseline_action = action_type
            elif oldest["action_type"] == "create":
                baseline_action = "create"
            else:
                baseline_action = action_type
            baseline_original = oldest["original_content"] if oldest["original_content"] is not None else original_content

            combined_reasoning = oldest.get("reasoning") or ""
            for row in existing_rows[1:]:
                combined_reasoning = _merge_reasoning(combined_reasoning, row.get("reasoning"))
            combined_reasoning = _merge_reasoning(combined_reasoning, reasoning)

            merged_convo_id = eff_convo_id or newest.get("conversation_id") or oldest.get("conversation_id")
            merged_thread_id = eff_thread_id or newest.get("thread_id") or oldest.get("thread_id")
            merged_agent_id = eff_agent_id or newest.get("agent_id") or oldest.get("agent_id")
            merged_agent_role = eff_agent_role or newest.get("agent_role") or oldest.get("agent_role")
            merged_dest = norm_dest or newest.get("destination_file")

            cursor.execute(
                '''
                UPDATE transactions
                SET agent_name = ?,
                    action_type = ?,
                    target_file = ?,
                    original_content = ?,
                    proposed_content = ?,
                    reasoning = ?,
                    conversation_id = ?,
                    thread_id = ?,
                    agent_id = ?,
                    agent_role = ?,
                    destination_file = ?,
                    created_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (
                    eff_agent_name,
                    baseline_action,
                    norm_target,
                    baseline_original,
                    proposed_content,
                    combined_reasoning,
                    merged_convo_id,
                    merged_thread_id,
                    merged_agent_id,
                    merged_agent_role,
                    merged_dest,
                    tx_id,
                ),
            )

            if len(existing_rows) > 1:
                older_ids = [int(r["id"]) for r in existing_rows[:-1]]
                placeholders = ",".join("?" for _ in older_ids)
                cursor.execute(
                    f"UPDATE transactions SET status = 'superseded' WHERE id IN ({placeholders})",
                    older_ids,
                )

            conn.commit()
            conn.close()
            return tx_id

        cursor.execute(
            '''
            INSERT INTO transactions
            (agent_name, action_type, target_file, original_content, proposed_content, reasoning, status,
             conversation_id, thread_id, agent_id, agent_role, destination_file)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
            ''',
            (
                eff_agent_name,
                action_type,
                norm_target,
                original_content,
                proposed_content,
                reasoning,
                eff_convo_id,
                eff_thread_id,
                eff_agent_id,
                eff_agent_role,
                norm_dest,
            ),
        )
        tx_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return tx_id


def get_pending_transactions() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM transactions WHERE status = "pending" ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_transaction(tx_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM transactions WHERE id = ?', (tx_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_transaction_status(tx_id: int, status: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE transactions SET status = ? WHERE id = ?', (status, tx_id))
    conn.commit()
    conn.close()


def cancel_pending_transactions_for_conversation(conversation_id: str) -> List[int]:
    """Cancels all staged pending transactions for a conversation thread.
    
    Used by Stop & Revert to guarantee that no unapproved file mutations (edits, creations,
    moves, or deletions) proposed during the aborted or reverted turn remain in the HITL review queue.
    
    Parameters:
      conversation_id: Unique UUID of the active conversation thread.
      
    Returns:
      List of transaction IDs whose status was transitioned from 'pending' to 'cancelled'.
    """
    if not conversation_id:
        return []

    conn = get_db_connection()
    cursor = conn.cursor()
    # Match on either conversation_id or thread_id columns
    cursor.execute(
        """
        SELECT id FROM transactions
        WHERE (conversation_id = ? OR thread_id = ?) AND status = 'pending'
        ORDER BY id ASC
        """,
        (conversation_id, conversation_id),
    )
    tx_ids = [row["id"] for row in cursor.fetchall()]
    if tx_ids:
        placeholders = ",".join("?" for _ in tx_ids)
        cursor.execute(
            f"UPDATE transactions SET status = 'cancelled' WHERE id IN ({placeholders})",
            tx_ids,
        )
        conn.commit()
    conn.close()
    return tx_ids


# ── Commit Integrity: Stale-Base Detection, Snapshots, Rollback & Rebase ─────
# Why this layer exists: edits can sit in the queue for hours while the human keeps editing the same
# note in Obsidian. Blindly writing `proposed_content` on approval would silently erase those edits.
# Every disk mutation below is (1) gated on the disk still matching the agent's baseline and
# (2) preceded by a snapshot in `revisions` so it can be undone.


def _normalize_eol(text: Optional[str]) -> Optional[str]:
    """Collapses Windows CRLF to LF so line-ending churn from editors never registers as a content conflict."""
    return text.replace("\r\n", "\n") if text is not None else None


def _content_matches(a: Optional[str], b: Optional[str]) -> bool:
    """True when both sides are absent (`None`) or have identical text after EOL normalization."""
    if a is None or b is None:
        return a is None and b is None
    return _normalize_eol(a) == _normalize_eol(b)


def _resolve_commit_path(target_file: str, root: Path) -> Path:
    """Resolves a `Vault/...` target against `root` and refuses anything escaping `root/Vault` (path traversal guard)."""
    norm = _normalize_target_file(target_file)
    # .resolve(): Collapses `..` segments and symlinks to an absolute path before the containment check
    path = (root / norm).resolve()
    vault_root = (root / "Vault").resolve()
    # Path.is_relative_to (3.9+): True only if `path` sits under `vault_root`; blocks `Vault/../.env` style targets
    if not path.is_relative_to(vault_root):
        raise HitlCommitError(f"Refusing to write outside the Vault: '{target_file}'")
    return path


def _read_disk(path: Path) -> Optional[str]:
    """Reads current note text exactly as stored (`newline=""` preserves CRLF), or metadata placeholder if binary, or `None` if the file is absent."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return f.read()
    except UnicodeDecodeError:
        return f"[Binary file ({path.stat().st_size} bytes)]"


def _atomic_write(path: Path, text: str) -> None:
    """Writes `text` via temp file + `os.replace` so a crash mid-write never leaves a truncated note.

    `newline=""` disables Python's Windows `\\n` -> `\\r\\n` translation, so notes keep the exact line
    endings in `text` (LF for agent-authored content, matching Obsidian's default).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.hitl-tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp_path, path)


def _require_pending(tx_id: int) -> Dict[str, Any]:
    """Fetches a transaction and asserts it is still `pending` (only pending cards may be committed or rebased)."""
    tx = get_transaction(tx_id)
    if not tx:
        raise TransactionNotFoundError(f"Transaction #{tx_id} not found")
    if tx["status"] != "pending":
        raise HitlCommitError(f"Transaction #{tx_id} is not pending (status: {tx['status']})")
    return tx


def commit_transaction(tx_id: int, root: Path, force: bool = False) -> Dict[str, Any]:
    """Applies a pending transaction to disk with stale-base detection and a pre-commit snapshot.

    Supports surgical modifications (`modify`), new file creations (`create`), atomic file
    relocations (`move` / `move_file`), and note deletions (`delete` / `delete_file`).

    Args:
        tx_id: Pending transaction to approve.
        root: Project root that `Vault/...` target paths are resolved against (normally `PROJECT_ROOT`).
        force: Skip the stale-base check and overwrite whatever is on disk (snapshot is still taken).

    Returns:
        Dict with `revision_id`, `target_file`, optional `destination_file`, and `forced`.

    Raises:
        StaleBaseError: Disk no longer matches `original_content` (human edited, deleted, or created the note).
    """
    tx = _require_pending(tx_id)
    action_type = tx.get("action_type", "")

    if action_type in ("delete", "delete_file"):
        path = _resolve_commit_path(tx["target_file"], root)
        current = _read_disk(path)
        is_stale = not _content_matches(current, tx["original_content"])

        if is_stale and not force:
            if current is None:
                reason = "the note was already deleted or moved after this deletion was staged"
            else:
                reason = "the note was edited on disk after deletion was staged"
            raise StaleBaseError(f"Stale base for Transaction #{tx_id}: {reason}.", current)

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO revisions (tx_id, target_file, prior_content, applied_content)
                VALUES (?, ?, ?, ?)
                ''',
                (tx_id, tx["target_file"], current, ""),
            )
            revision_id = cursor.lastrowid
            if path.exists():
                path.unlink()
            cursor.execute("UPDATE transactions SET status = 'approved' WHERE id = ?", (tx_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {"revision_id": revision_id, "target_file": tx["target_file"], "forced": bool(force and is_stale)}

    elif action_type in ("move", "move_file"):
        src_path = _resolve_commit_path(tx["target_file"], root)
        dest_target = tx.get("destination_file")
        if not dest_target:
            raise HitlCommitError(f"Move transaction #{tx_id} is missing destination_file")
        dst_path = _resolve_commit_path(dest_target, root)

        src_current = _read_disk(src_path)
        is_src_stale = not _content_matches(src_current, tx["original_content"])
        if is_src_stale and not force:
            if src_current is None:
                reason = "the source note was deleted or moved after this move was staged"
            else:
                reason = "the source note was edited on disk after this move was staged"
            raise StaleBaseError(f"Stale base for Transaction #{tx_id}: {reason}.", src_current)

        dst_current = _read_disk(dst_path)
        if dst_current is not None and not force:
            raise StaleBaseError(
                f"Stale base for Transaction #{tx_id}: a note now exists at destination '{dest_target}'.",
                dst_current,
            )

        # Check if source is a binary file (e.g. PDF, images, audio)
        is_binary = False
        if src_path.exists():
            try:
                with open(src_path, "r", encoding="utf-8", newline="") as f:
                    f.read(1024)
            except UnicodeDecodeError:
                is_binary = True

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO revisions (tx_id, target_file, destination_file, prior_content, applied_content)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (tx_id, tx["target_file"], dest_target, src_current, tx["proposed_content"]),
            )
            revision_id = cursor.lastrowid

            dst_path.parent.mkdir(parents=True, exist_ok=True)
            if is_binary:
                # Atomically copy and replace binary file bytes without UTF-8 string encoding corruption
                tmp_dst = dst_path.with_name(f".{dst_path.name}.hitl-tmp")
                shutil.copy2(src_path, tmp_dst)
                os.replace(tmp_dst, dst_path)
                if src_path.exists() and src_path.resolve() != dst_path.resolve():
                    src_path.unlink()
            else:
                _atomic_write(dst_path, tx["proposed_content"])
                if src_path.exists() and src_path.resolve() != dst_path.resolve():
                    src_path.unlink()

            cursor.execute("UPDATE transactions SET status = 'approved' WHERE id = ?", (tx_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {
            "revision_id": revision_id,
            "target_file": tx["target_file"],
            "destination_file": dest_target,
            "forced": bool(force and (is_src_stale or dst_current is not None)),
        }

    else:
        path = _resolve_commit_path(tx["target_file"], root)
        current = _read_disk(path)
        is_stale = not _content_matches(current, tx["original_content"])

        if is_stale and not force:
            # Phase 1: Explain *how* the disk drifted so the reviewer knows what approving would clobber
            if current is None:
                reason = "the note was deleted or moved after this edit was staged"
            elif tx["original_content"] is None:
                reason = "a note was created at this path after this edit was staged"
            else:
                reason = "the note was edited on disk after this edit was staged"
            raise StaleBaseError(f"Stale base for Transaction #{tx_id}: {reason}.", current)

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # Phase 2: Stage the snapshot row (uncommitted) BEFORE touching disk, so a write failure rolls both back
            cursor.execute(
                '''
                INSERT INTO revisions (tx_id, target_file, prior_content, applied_content)
                VALUES (?, ?, ?, ?)
                ''',
                (tx_id, tx["target_file"], current, tx["proposed_content"]),
            )
            revision_id = cursor.lastrowid
            # Phase 3: Mutate disk atomically, then flip status and commit the ledger in one SQLite transaction
            _atomic_write(path, tx["proposed_content"])
            cursor.execute("UPDATE transactions SET status = 'approved' WHERE id = ?", (tx_id,))
            conn.commit()
        except Exception:
            # conn.rollback(): Discards the uncommitted snapshot row if the disk write (or status update) failed
            conn.rollback()
            raise
        finally:
            conn.close()

        return {"revision_id": revision_id, "target_file": tx["target_file"], "forced": bool(force and is_stale)}


def rollback_transaction(tx_id: int, root: Path, force: bool = False) -> Dict[str, Any]:
    """Restores a note to its pre-approval snapshot (or deletes it if the approval created it).

    Refuses (StaleBaseError) if the note changed since approval, because restoring would erase those
    newer edits. With `force=True` the newer text is overwritten but preserved in `overwritten_content`.
    Correctly reverses file moves and deletions atomically.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT * FROM revisions
            WHERE tx_id = ? AND rolled_back = 0
            ORDER BY id DESC
            LIMIT 1
            ''',
            (tx_id,),
        )
        row = cursor.fetchone()
        if row is None:
            if get_transaction(tx_id) is None:
                raise TransactionNotFoundError(f"Transaction #{tx_id} not found")
            raise HitlCommitError(f"Transaction #{tx_id} has no applied revision to roll back")
        rev = dict(row)

        tx = get_transaction(tx_id)
        action_type = tx.get("action_type") if tx else None

        # Case 1: Rollback atomic file move
        if action_type in ("move", "move_file") or rev.get("destination_file") is not None:
            dst_dest = rev.get("destination_file")
            dst_path = _resolve_commit_path(dst_dest, root)
            src_path = _resolve_commit_path(rev["target_file"], root)

            current_dst = _read_disk(dst_path)
            drifted_dst = not _content_matches(current_dst, rev["applied_content"])
            if drifted_dst and not force:
                raise StaleBaseError(
                    f"Cannot roll back Transaction #{tx_id}: destination note changed after approval.",
                    current_dst,
                )

            current_src = _read_disk(src_path)
            if current_src is not None and not force:
                raise StaleBaseError(
                    f"Cannot roll back Transaction #{tx_id}: a note now exists at original source path '{rev['target_file']}'.",
                    current_src,
                )

            # Detect if destination is a binary file
            is_binary = False
            if dst_path.exists():
                try:
                    with open(dst_path, "r", encoding="utf-8", newline="") as f:
                        f.read(1024)
                except UnicodeDecodeError:
                    is_binary = True

            if is_binary and dst_path.exists():
                src_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst_path), str(src_path))
            else:
                if dst_path.exists():
                    dst_path.unlink()
                _atomic_write(src_path, rev["prior_content"] or "")

            cursor.execute(
                '''
                UPDATE revisions
                SET rolled_back = 1, rolled_back_at = CURRENT_TIMESTAMP, overwritten_content = ?
                WHERE id = ?
                ''',
                (current_dst if drifted_dst else None, rev["id"]),
            )
            cursor.execute("UPDATE transactions SET status = 'rolled_back' WHERE id = ?", (tx_id,))
            conn.commit()
            return {
                "revision_id": rev["id"],
                "target_file": rev["target_file"],
                "destination_file": dst_dest,
                "forced": bool(force and (drifted_dst or current_src is not None)),
            }

        # Case 2: Rollback file deletion (restores deleted note from prior_content)
        elif action_type in ("delete", "delete_file") or (rev["applied_content"] == "" and rev["prior_content"] is not None):
            path = _resolve_commit_path(rev["target_file"], root)
            current = _read_disk(path)
            # For deletion, current is expected to be None (absent from disk)
            drifted = current is not None
            if drifted and not force:
                raise StaleBaseError(
                    f"Cannot roll back Transaction #{tx_id}: a note was created at this path after deletion.",
                    current,
                )

            _atomic_write(path, rev["prior_content"] or "")

            cursor.execute(
                '''
                UPDATE revisions
                SET rolled_back = 1, rolled_back_at = CURRENT_TIMESTAMP, overwritten_content = ?
                WHERE id = ?
                ''',
                (current if drifted else None, rev["id"]),
            )
            cursor.execute("UPDATE transactions SET status = 'rolled_back' WHERE id = ?", (tx_id,))
            conn.commit()
            return {"revision_id": rev["id"], "target_file": rev["target_file"], "forced": bool(force and drifted)}

        # Case 3: Standard modify / create rollback
        else:
            path = _resolve_commit_path(rev["target_file"], root)
            current = _read_disk(path)
            drifted = not _content_matches(current, rev["applied_content"])
            if drifted and not force:
                raise StaleBaseError(
                    f"Cannot roll back Transaction #{tx_id}: the note changed after approval "
                    f"(rolling back would erase those newer edits).",
                    current,
                )

            # Restore: NULL prior_content means the approval created the file, so undo = delete it
            if rev["prior_content"] is None:
                if path.exists():
                    path.unlink()
            else:
                _atomic_write(path, rev["prior_content"])

            cursor.execute(
                '''
                UPDATE revisions
                SET rolled_back = 1, rolled_back_at = CURRENT_TIMESTAMP, overwritten_content = ?
                WHERE id = ?
                ''',
                (current if drifted else None, rev["id"]),
            )
            cursor.execute("UPDATE transactions SET status = 'rolled_back' WHERE id = ?", (tx_id,))
            conn.commit()
            return {"revision_id": rev["id"], "target_file": rev["target_file"], "forced": bool(force and drifted)}
    finally:
        conn.close()


def three_way_merge(base: str, ours: str, theirs: str) -> Optional[str]:
    """Line-level diff3-style merge. Returns merged text, or `None` if the two sides' edits touch.

    Args:
        base: Common ancestor (the disk text the agent staged against).
        ours: Current disk text (human edits since staging).
        theirs: Agent's proposed text.

    Conservative by design: changes that overlap OR sit directly adjacent count as conflicts (same as git),
    because silently interleaving human and agent edits in a personal note is worse than asking.
    """
    # splitlines(keepends=True): Keeps the trailing "\n" on each line so re-joining reproduces exact text
    base_lines = base.splitlines(keepends=True)
    ours_lines = ours.splitlines(keepends=True)
    theirs_lines = theirs.splitlines(keepends=True)

    def _change_regions(side_lines: List[str]) -> List[tuple]:
        # get_opcodes(): Tuples (tag, i1, i2, j1, j2) meaning base[i1:i2] -> side[j1:j2]; we keep non-'equal' ones
        # autojunk=False: Disables the "popular line" heuristic that misfires on notes with many blank lines
        matcher = difflib.SequenceMatcher(None, base_lines, side_lines, autojunk=False)
        return [(i1, i2, side_lines[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]

    ours_regions = _change_regions(ours_lines)
    theirs_regions = _change_regions(theirs_lines)

    kept_theirs = []
    for t_region in theirs_regions:
        t1, t2, t_lines = t_region
        duplicate = False
        for o1, o2, o_lines in ours_regions:
            # Closed-interval touch test: catches overlaps, adjacency, and same-point insertions
            if t1 <= o2 and o1 <= t2:
                if (t1, t2, t_lines) == (o1, o2, o_lines):
                    duplicate = True  # Both sides made the identical change -> apply once, not a conflict
                    break
                return None
        if not duplicate:
            kept_theirs.append(t_region)

    # Regions are now non-overlapping, so a single left-to-right walk over base splices them in order
    merged: List[str] = []
    cursor_pos = 0
    for i1, i2, replacement in sorted(ours_regions + kept_theirs, key=lambda r: (r[0], r[1])):
        merged.extend(base_lines[cursor_pos:i1])
        merged.extend(replacement)
        cursor_pos = i2
    merged.extend(base_lines[cursor_pos:])
    return "".join(merged)


def rebase_transaction(tx_id: int, root: Path) -> Dict[str, Any]:
    """Re-stages a stale pending edit on top of the current disk text via `three_way_merge`.

    On success the card's `original_content` becomes current disk text and `proposed_content` becomes
    the merged result, so the diff shown in the GUI is again exactly what approval will write.
    For deletions, updates the baseline to current disk content so reviewer sees latest human edits.

    Raises:
        MergeConflictError: Note deleted/created underneath the edit, or human and agent edits touch.
    """
    tx = _require_pending(tx_id)
    action_type = tx.get("action_type", "")

    if action_type in ("delete", "delete_file"):
        path = _resolve_commit_path(tx["target_file"], root)
        current = _read_disk(path)
        if _content_matches(current, tx["original_content"]):
            return {"rebased": False, "message": "Already based on current disk content"}
        if current is None:
            raise MergeConflictError("The note no longer exists on disk; reject this edit or force-approve.")
        conn = get_db_connection()
        try:
            conn.execute(
                '''
                UPDATE transactions
                SET original_content = ?, reasoning = ?
                WHERE id = ?
                ''',
                (
                    _normalize_eol(current),
                    _merge_reasoning(tx.get("reasoning"), "Rebased deletion baseline onto human edits made after staging."),
                    tx_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {"rebased": True, "message": "Rebased deletion baseline onto current disk content"}

    path = _resolve_commit_path(tx["target_file"], root)
    current = _read_disk(path)

    if _content_matches(current, tx["original_content"]):
        return {"rebased": False, "message": "Already based on current disk content"}
    if current is None:
        raise MergeConflictError("The note no longer exists on disk; reject this edit or force-approve to recreate it.")
    if tx["original_content"] is None:
        raise MergeConflictError("A note now exists at this path; the staged 'create' cannot be merged into it.")

    # Normalize EOLs first so CRLF-vs-LF differences never surface as phantom line conflicts
    merged = three_way_merge(
        _normalize_eol(tx["original_content"]),
        _normalize_eol(current),
        _normalize_eol(tx["proposed_content"]),
    )
    if merged is None:
        raise MergeConflictError(
            "Your edits and the agent's edits touch the same lines; reject and re-run the agent, or force-approve."
        )

    conn = get_db_connection()
    try:
        conn.execute(
            '''
            UPDATE transactions
            SET original_content = ?, proposed_content = ?, reasoning = ?
            WHERE id = ?
            ''',
            (
                _normalize_eol(current),
                merged,
                _merge_reasoning(tx.get("reasoning"), "Rebased onto human edits made after staging."),
                tx_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"rebased": True, "message": "Rebased onto current disk content"}


def get_recent_revisions(limit: int = 20) -> List[Dict[str, Any]]:
    """Lists recently applied revisions (newest first) with lightweight metadata for the GUI's Undo list."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT r.id, r.tx_id, r.target_file, r.destination_file, r.rolled_back, r.created_at, r.rolled_back_at,
               t.agent_name, t.action_type, t.reasoning,
               t.conversation_id, t.thread_id, t.agent_id, t.agent_role
        FROM revisions r
        JOIN transactions t ON t.id = r.tx_id
        ORDER BY r.id DESC
        LIMIT ?
        ''',
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# Initialize DB on import
init_db()
