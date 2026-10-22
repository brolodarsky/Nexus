import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# DB_PATH: Resolves to `src/nexus/hitl.db`, the SQLite ledger for Two-Phase Commit (HITL) file mutations
DB_PATH = Path(__file__).resolve().parent.parent / "hitl.db"


def _normalize_target_file(target_file: str) -> str:
    """Normalizes Vault target paths (`\\` -> `/`, ensures `Vault/` prefix) so per-file queue lookups never miss."""
    clean = (target_file or "").strip().replace("\\", "/").lstrip("/")
    if clean and not clean.startswith("Vault/"):
        clean = f"Vault/{clean}"
    return clean


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def get_pending_for_file(target_file: str) -> Optional[Dict[str, Any]]:
    """Returns the active pending HITL transaction for `target_file`, if one exists.

    Also matches when `target_file` is supplied as a short filename (e.g. `"Plan.md"`) by checking
    exact normalized path first and falling back to unique basename suffix match (`%/<filename>`).
    Used by `read_file`, `modify_file`, and `create_file` so agents read and stack edits
    on top of already-staged `proposed_content` instead of reading stale disk state and
    creating conflicting duplicate transactions for the same note.
    """
    norm_target = _normalize_target_file(target_file)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT * FROM transactions
        WHERE status = 'pending' AND REPLACE(target_file, '\\', '/') = ?
        ORDER BY id DESC
        LIMIT 1
        ''',
        (norm_target,),
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
            WHERE status = 'pending' AND REPLACE(target_file, '\\', '/') LIKE ?
            ORDER BY id DESC
            LIMIT 1
            ''',
            (f"%/{basename}",),
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
) -> int:
    """Inserts a pending HITL transaction or coalesces in-place if `target_file` already has a pending edit.

    Cumulative Overlay Stacking:
      - If `target_file` already has one or more `status = 'pending'` rows, we preserve the earliest
        pending row's `original_content` (the true on-disk baseline before any pending edits),
        update the newest pending row in place with the cumulative `proposed_content` and merged `reasoning`,
        and mark any older duplicate pending rows for that file as `'superseded'`.
      - This guarantees at most ONE pending review card per file in the HITL Control Panel.
    """
    norm_target = _normalize_target_file(target_file)
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

        # Preserve earliest pending action_type ('create' stays 'create' if refined before disk write)
        baseline_action = oldest["action_type"] if oldest["action_type"] == "create" else action_type
        baseline_original = oldest["original_content"] if oldest["original_content"] is not None else original_content

        combined_reasoning = oldest.get("reasoning") or ""
        for row in existing_rows[1:]:
            combined_reasoning = _merge_reasoning(combined_reasoning, row.get("reasoning"))
        combined_reasoning = _merge_reasoning(combined_reasoning, reasoning)

        cursor.execute(
            '''
            UPDATE transactions
            SET agent_name = ?,
                action_type = ?,
                target_file = ?,
                original_content = ?,
                proposed_content = ?,
                reasoning = ?,
                created_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (
                agent_name,
                baseline_action,
                norm_target,
                baseline_original,
                proposed_content,
                combined_reasoning,
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
        (agent_name, action_type, target_file, original_content, proposed_content, reasoning, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending')
        ''',
        (agent_name, action_type, norm_target, original_content, proposed_content, reasoning),
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


# Initialize DB on import
init_db()
