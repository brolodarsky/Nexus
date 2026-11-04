"""
test_blackboard.py — Unit tests for the Shared Agent Blackboard (`blackboard.db`).

Validates:
  1. Posting bulletins without channel tags.
  2. Querying bulletins (pinned-first, newest-first ordering).
  3. Formatting Markdown digests without channel tags.
  4. Deleting and clearing unpinned bulletins.
  5. Schema migration: legacy `channel` column dropping.
  6. Shared @tool wrappers (`post_to_board` and `read_board`).
"""
import sqlite3
from pathlib import Path
import pytest

from nexus.core import blackboard
from nexus.shared_tools.shared import post_to_board, read_board


@pytest.fixture
def temp_board_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Overrides `BOARD_DB_PATH` with an isolated temporary SQLite database for each test run."""
    db_file = tmp_path / "test_blackboard.db"
    monkeypatch.setattr(blackboard, "BOARD_DB_PATH", db_file)
    blackboard.init_board_db()
    yield db_file


def test_post_and_get_bulletins(temp_board_db: Path):
    """Tests posting bulletins and retrieving them in reverse chronological order."""
    b1_id = blackboard.post_bulletin(
        author="Subagent #1 (low)",
        title="Gmail Sweep Results",
        content="Found 3 unread messages.",
    )
    b2_id = blackboard.post_bulletin(
        author="Subagent #2 (low)",
        title="Calendar Audit",
        content="Schedule clear until 3 PM.",
    )

    items = blackboard.get_bulletins(limit=10)
    assert len(items) == 2
    # Newest bulletin should appear first
    assert items[0]["id"] == b2_id
    assert items[0]["title"] == "Calendar Audit"
    assert items[0]["author"] == "Subagent #2 (low)"
    assert "channel" not in items[0]  # Verify no channel field in returned dict

    assert items[1]["id"] == b1_id
    assert items[1]["title"] == "Gmail Sweep Results"


def test_pinned_bulletin_ordering(temp_board_db: Path):
    """Tests that pinned bulletins are sorted to the top regardless of insertion order."""
    blackboard.post_bulletin(
        author="Subagent #1 (low)",
        title="Routine Check",
        content="Normal status.",
        pinned=False,
    )
    b2_id = blackboard.post_bulletin(
        author="Astra",
        title="Standing Directive",
        content="Maintain high signal.",
        pinned=True,
    )
    blackboard.post_bulletin(
        author="Subagent #2 (low)",
        title="Another Routine Check",
        content="Normal status.",
        pinned=False,
    )

    items = blackboard.get_bulletins(limit=10)
    assert len(items) == 3
    # Pinned bulletin must come first
    assert items[0]["id"] == b2_id
    assert items[0]["pinned"] == 1


def test_format_board_digest(temp_board_db: Path):
    """Tests formatting bulletins into a Markdown digest without channel tags."""
    # When empty
    empty_digest = blackboard.format_board_digest()
    assert "Shared Agent Blackboard is currently empty" in empty_digest

    # With bulletins
    blackboard.post_bulletin(
        author="Flash: Gmail",
        title="Important Email",
        content="Urgent response needed.",
    )
    digest = blackboard.format_board_digest()
    assert "### 📋 Shared Agent Blackboard (1 recent bulletin(s))" in digest
    assert "Important Email" in digest
    assert "*(by Flash: Gmail at " in digest
    # Channel tags (like `[GENERAL]` or `[EMAIL]`) should NOT be present
    assert "[GENERAL]" not in digest
    assert "[EMAIL]" not in digest


def test_clear_and_delete_bulletin(temp_board_db: Path):
    """Tests deleting an individual bulletin and clearing unpinned bulletins."""
    b1_id = blackboard.post_bulletin(author="A", title="Pinned", content="Keep", pinned=True)
    b2_id = blackboard.post_bulletin(author="B", title="Unpinned 1", content="Drop", pinned=False)
    b3_id = blackboard.post_bulletin(author="C", title="Unpinned 2", content="Drop", pinned=False)

    # Delete single bulletin
    deleted = blackboard.delete_bulletin(b2_id)
    assert deleted is True
    assert len(blackboard.get_bulletins()) == 2

    # Clear all remaining unpinned bulletins
    cleared_count = blackboard.clear_bulletins()
    assert cleared_count == 1  # Only b3 was cleared
    remaining = blackboard.get_bulletins()
    assert len(remaining) == 1
    assert remaining[0]["id"] == b1_id


def test_legacy_kwargs_tolerance(temp_board_db: Path):
    """Tests that passing legacy `channel` kwargs does not raise an exception."""
    b_id = blackboard.post_bulletin(
        author="Subagent #1",
        title="Legacy Call",
        content="Works seamlessly",
        channel="email",
    )
    assert b_id > 0
    items = blackboard.get_bulletins(channel="email", limit=5)
    assert len(items) == 1


def test_schema_migration_drops_channel_column(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Tests that `init_board_db` migrates an existing legacy table with a `channel` column."""
    db_file = tmp_path / "legacy_board.db"
    monkeypatch.setattr(blackboard, "BOARD_DB_PATH", db_file)

    # 1. Create a legacy table with `channel`
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE bulletins (
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
    conn.execute("INSERT INTO bulletins (author, channel, title, content) VALUES ('OldAgent', 'vault', 'T', 'C')")
    conn.commit()
    conn.close()

    # 2. Run init_board_db to perform migration
    blackboard.init_board_db()

    # 3. Verify channel column is gone and data is preserved
    conn = sqlite3.connect(db_file)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bulletins)").fetchall()]
    conn.close()

    assert "channel" not in cols
    assert "author" in cols
    assert "title" in cols
    assert "content" in cols

    items = blackboard.get_bulletins()
    assert len(items) == 1
    assert items[0]["title"] == "T"


def test_shared_tool_wrappers(temp_board_db: Path):
    """Tests invoking the `@tool` wrappers `post_to_board` and `read_board`."""
    res_post = post_to_board.invoke({
        "title": "Tool Post",
        "content": "Posted via @tool",
        "author": "TestWorker",
    })
    assert "📋 Bulletin #" in res_post
    assert "posted to Shared Blackboard: 'Tool Post'" in res_post
    assert "[`" not in res_post  # No channel tag like [`general`]

    res_read = read_board.invoke({"limit": 5})
    assert "Tool Post" in res_read
    assert "Posted via @tool" in res_read


def test_thread_scoped_bulletins(temp_board_db: Path):
    """Validates that bulletins posted to specific thread IDs are strictly isolated from one another."""
    # Bulletin posted to Conversation A
    b_a = blackboard.post_bulletin(
        author="Flash: Gmail",
        title="Thread A Triage",
        content="3 urgent emails found in thread A.",
        thread_id="conv_session_alpha",
    )
    # Bulletin posted to Conversation B
    b_b = blackboard.post_bulletin(
        author="Flash: Calendar",
        title="Thread B Audit",
        content="Calendar clear for thread B.",
        thread_id="conv_session_beta",
    )

    # 1. Thread A should ONLY retrieve bulletin A
    items_a = blackboard.get_bulletins(thread_id="conv_session_alpha")
    assert len(items_a) == 1
    assert items_a[0]["id"] == b_a
    assert items_a[0]["title"] == "Thread A Triage"

    # 2. Thread B should ONLY retrieve bulletin B
    items_b = blackboard.get_bulletins(thread_id="conv_session_beta")
    assert len(items_b) == 1
    assert items_b[0]["id"] == b_b
    assert items_b[0]["title"] == "Thread B Audit"

    # 3. Empty thread ID query returns empty list (represents fresh/uninitiated conversation)
    assert blackboard.get_bulletins(thread_id="") == []


def test_thread_scoped_clear(temp_board_db: Path):
    """Validates that clearing unpinned bulletins in one thread preserves unpinned bulletins in other threads."""
    # Thread A has 1 pinned directive and 1 unpinned sweep
    blackboard.post_bulletin(
        author="Astra",
        title="Thread A Directive",
        content="Stay on task.",
        pinned=True,
        thread_id="conv_alpha",
    )
    blackboard.post_bulletin(
        author="Subagent #1",
        title="Thread A Unpinned Sweep",
        content="Temporary audit.",
        pinned=False,
        thread_id="conv_alpha",
    )

    # Thread B has 1 unpinned sweep
    b_b_id = blackboard.post_bulletin(
        author="Subagent #2",
        title="Thread B Unpinned Sweep",
        content="Keep this alive.",
        pinned=False,
        thread_id="conv_beta",
    )

    # Clear unpinned bulletins strictly for Thread A
    deleted_count = blackboard.clear_bulletins(thread_id="conv_alpha")
    assert deleted_count == 1

    # Thread A should retain only the pinned bulletin
    items_a = blackboard.get_bulletins(thread_id="conv_alpha")
    assert len(items_a) == 1
    assert items_a[0]["pinned"] == 1
    assert items_a[0]["title"] == "Thread A Directive"

    # Thread B should remain completely untouched
    items_b = blackboard.get_bulletins(thread_id="conv_beta")
    assert len(items_b) == 1
    assert items_b[0]["id"] == b_b_id
    assert items_b[0]["title"] == "Thread B Unpinned Sweep"


def test_ambient_execution_context_thread_scoping(temp_board_db: Path):
    """Validates that `post_bulletin` and `read_board` automatically inherit and normalize the active HITL thread context."""
    from nexus.core.hitl_queue import reset_hitl_execution_context, set_hitl_execution_context

    # Simulate subagent execution context spawned by parent conversation `conv_999`
    ctx_token = set_hitl_execution_context(
        conversation_id="conv_999",
        thread_id="conv_999:subagent_worker_7",
        agent_id="sub_7",
        agent_role="Subagent #7 (low)",
    )

    try:
        # Posting without explicit thread_id should resolve and normalize to parent thread "conv_999"
        b_id = blackboard.post_bulletin(
            author="Subagent #7",
            title="Auto Context Sweep",
            content="Grounded observations.",
        )
        assert b_id > 0

        # Querying with thread_id="conv_999" retrieves it
        items = blackboard.get_bulletins(thread_id="conv_999")
        assert len(items) == 1
        assert items[0]["id"] == b_id
        assert items[0]["thread_id"] == "conv_999"

        # Reading board without arguments inside this context should automatically format for "conv_999"
        digest = blackboard.format_board_digest()
        assert "Auto Context Sweep" in digest
        assert "Grounded observations." in digest
    finally:
        reset_hitl_execution_context(ctx_token)


def test_schema_migration_adds_thread_id_column(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Validates that `init_board_db` gracefully adds the `thread_id` column and index to an existing legacy table."""
    db_file = tmp_path / "legacy_board_no_thread.db"
    monkeypatch.setattr(blackboard, "BOARD_DB_PATH", db_file)

    # 1. Create table without thread_id column
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE bulletins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            pinned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("INSERT INTO bulletins (author, title, content) VALUES ('OldWorker', 'Pre-Migration', 'Legacy Content')")
    conn.commit()
    conn.close()

    # 2. Run init_board_db migration
    blackboard.init_board_db()

    # 3. Verify `thread_id` column and index now exist, and existing record has NULL thread_id
    conn = sqlite3.connect(db_file)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(bulletins)").fetchall()]
    indices = [r[1] for r in conn.execute("PRAGMA index_list(bulletins)").fetchall()]
    rows = conn.execute("SELECT id, thread_id, title FROM bulletins").fetchall()
    conn.close()

    assert "thread_id" in cols
    assert "idx_bulletins_thread_id" in indices
    assert len(rows) == 1
    assert rows[0][1] is None  # Existing legacy record has NULL thread_id
    assert rows[0][2] == "Pre-Migration"
