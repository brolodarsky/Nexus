"""
conftest.py — Global pytest fixtures isolating SQLite state from live workspace databases.
"""

from pathlib import Path
import pytest

import nexus.core.chats_db as chats_db


@pytest.fixture(autouse=True)
def _isolate_default_chats_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect `chats_db.DB_PATH` and `UPLOADS_DIR` to `tmp_path` so unit tests never touch live `logs/chats.db`."""
    monkeypatch.setattr(chats_db, "DB_PATH", tmp_path / "pytest_chats.db")
    monkeypatch.setattr(chats_db, "UPLOADS_DIR", tmp_path / "uploads")
    chats_db.init_db()
