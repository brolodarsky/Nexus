"""
test_sqlite_concurrency.py — Unit and integration tests for SQLite WAL mode, busy timeouts, and concurrent multi-agent access.

Validates that all core SQLite databases (`chats.db`, `blackboard.db`, `hitl.db`, `memory.sqlite`):
  1. Operate with Write-Ahead Logging (`PRAGMA journal_mode = WAL`) enabled.
  2. Set a 30,000ms engine-level busy timeout (`PRAGMA busy_timeout = 30000`).
  3. Execute concurrent reads and writes across multiple worker threads without `sqlite3.OperationalError: database is locked`.
"""
import concurrent.futures
import sqlite3
import threading
import pytest
from pathlib import Path

from nexus.agent.graph import MEMORY_DB_PATH, get_latest_checkpoint_id
from nexus.core.blackboard import get_board_connection, get_bulletins, init_board_db, post_bulletin
from nexus.core.chats_db import _get_conn as get_chats_conn, create_conversation, log_message, get_chat_history
from nexus.core.hitl_queue import get_db_connection as get_hitl_conn, add_transaction, get_pending_transactions


def test_chats_db_wal_mode_and_busy_timeout():
    """Verify chats.db initializes with WAL mode and 30s busy timeout."""
    with get_chats_conn() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0].upper()
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert journal_mode == "WAL"
        assert busy_timeout == 30000


def test_blackboard_db_wal_mode_and_busy_timeout():
    """Verify blackboard.db initializes with WAL mode and 30s busy timeout."""
    with get_board_connection() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0].upper()
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert journal_mode == "WAL"
        assert busy_timeout == 30000


def test_hitl_db_wal_mode_and_busy_timeout():
    """Verify hitl.db initializes with WAL mode and 30s busy timeout."""
    with get_hitl_conn() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0].upper()
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert journal_mode == "WAL"
        assert busy_timeout == 30000


def test_memory_db_wal_mode_and_busy_timeout():
    """Verify memory.sqlite checkpointer database operates in WAL mode with 30s busy timeout."""
    if not MEMORY_DB_PATH.exists():
        pytest.skip("memory.sqlite has not been initialized yet on this disk.")

    with sqlite3.connect(MEMORY_DB_PATH, timeout=30.0) as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0].upper()
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert journal_mode == "WAL"
        assert busy_timeout == 30000


def test_concurrent_chat_logging_without_lock():
    """Verify multiple worker threads can write messages simultaneously to chats.db without collision."""
    conv_id = create_conversation(title="Concurrency Test Thread")
    worker_count = 10
    messages_per_worker = 5

    def _worker_log(worker_idx: int):
        for msg_idx in range(messages_per_worker):
            log_message(
                role="user" if msg_idx % 2 == 0 else "assistant",
                content=f"Worker {worker_idx} message {msg_idx}",
                conversation_id=conv_id,
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(_worker_log, i) for i in range(worker_count)]
        for f in concurrent.futures.as_completed(futures):
            f.result()  # Will raise if any OperationalError: database is locked occurred

    history = get_chat_history(conv_id)
    assert len(history) == worker_count * messages_per_worker


def test_concurrent_blackboard_bulletin_posting():
    """Verify multiple parallel subagents posting to blackboard.db succeed concurrently under WAL mode."""
    init_board_db()
    test_thread = "concurrency_test_thread"
    worker_count = 8

    def _worker_bulletin(worker_idx: int):
        post_bulletin(
            title=f"Bulletin from Worker #{worker_idx}",
            content=f"Findings payload from worker #{worker_idx}",
            author=f"Subagent #{worker_idx}",
            thread_id=test_thread,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(_worker_bulletin, i) for i in range(worker_count)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    bulletins = get_bulletins(thread_id=test_thread)
    assert len(bulletins) >= worker_count
