"""
test_chat_titles.py — Unit and integration tests for Nexus chat conversation title updating and auto-titling.

Tests:
  1. Manual conversation title rename via PATCH /api/agents/ask/conversations/{conversation_id}
  2. Input validation guarding against empty or whitespace-only titles (HTTP 400)
  3. Safe handling of non-existent conversation UUIDs (HTTP 404)
  4. AI-driven auto-title generation via POST /api/agents/ask/conversations/{conversation_id}/auto-title
  5. Graceful fallback title extraction when the underlying LLM call encounters exceptions
  6. Idempotent handling for empty conversations without messages
"""

from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from nexus.api.main import app
import nexus.core.chats_db as chats_db
from nexus.core.chats_db import (
    create_conversation,
    get_conversation,
    get_conversations,
    delete_conversation,
    log_message,
)


@pytest.fixture(autouse=True)
def isolated_chats_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect `chats_db.DB_PATH` to an isolated temporary SQLite database per test."""
    monkeypatch.setattr(chats_db, "DB_PATH", tmp_path / "test_chats.db")
    chats_db.init_db()


@pytest.fixture
def client():
    """FastAPI TestClient fixture for invoking HTTP routes without binding a physical port."""
    return TestClient(app)


@pytest.fixture
def temp_conv():
    """Pytest fixture yielding a freshly initialized conversation thread and deleting it upon teardown."""
    conv_id = create_conversation(title="Temporary Title")
    try:
        yield conv_id
    finally:
        delete_conversation(conv_id)


def test_update_conversation_title_success(client, temp_conv):
    """Verify that PATCH /api/agents/ask/conversations/{id} renames an existing conversation in SQLite chats.db."""
    new_title = "Architectural Review — Graph Subagents"
    response = client.patch(
        f"/api/agents/ask/conversations/{temp_conv}",
        json={"title": new_title},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert data["title"] == new_title
    assert data["conversation_id"] == temp_conv

    # Direct database verification
    db_record = get_conversation(temp_conv)
    assert db_record is not None
    assert db_record["title"] == new_title


def test_update_conversation_title_empty_rejected(client, temp_conv):
    """Verify that updating a conversation with a blank or whitespace-only title raises HTTP 400 Bad Request."""
    response = client.patch(
        f"/api/agents/ask/conversations/{temp_conv}",
        json={"title": "    "},
    )
    assert response.status_code == 400
    assert "Title cannot be empty" in response.json()["detail"]


def test_update_conversation_title_not_found(client):
    """Verify that updating an unrecorded UUID returns HTTP 404 Not Found."""
    fake_id = "non-existent-uuid-99999"
    response = client.patch(
        f"/api/agents/ask/conversations/{fake_id}",
        json={"title": "New Title"},
    )
    assert response.status_code == 404
    assert f"Conversation '{fake_id}' not found" in response.json()["detail"]


@pytest.mark.anyio
def test_auto_generate_title_with_mock_llm(client, temp_conv):
    """Verify that POST /api/agents/ask/conversations/{id}/auto-title summarizes opening turn into a clean title."""
    # Seed messages into the conversation thread
    log_message(
        role="user",
        content="Can you analyze the Q3 cloud infrastructure budget and highlight largest cost drivers?",
        conversation_id=temp_conv,
    )
    log_message(
        role="assistant",
        content="Here is a breakdown of your AWS and GCP compute and database expenditures...",
        conversation_id=temp_conv,
    )

    mock_model = AsyncMock()
    mock_model.ainvoke.return_value = AIMessage(content='"Q3 Cloud Budget Breakdown"')

    with patch("nexus.core.constants.get_chat_model", return_value=mock_model):
        response = client.post(f"/api/agents/ask/conversations/{temp_conv}/auto-title")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        # Verify quotation marks were stripped
        assert data["title"] == "Q3 Cloud Budget Breakdown"

        # Verify persisted in SQLite chats.db
        persisted = get_conversation(temp_conv)
        assert persisted["title"] == "Q3 Cloud Budget Breakdown"


@pytest.mark.anyio
def test_auto_generate_title_gemini_block_format(client, temp_conv):
    """Verify that Gemini 3+ structured content blocks [{'type': 'text', 'text': '...'}] are cleanly unpacked."""
    log_message(
        role="user",
        content="Catch up and email sweep across my accounts",
        conversation_id=temp_conv,
    )

    mock_model = AsyncMock()
    # Simulate Gemini 3+ content block returned by ChatGoogleGenerativeAI
    mock_model.ainvoke.return_value = AIMessage(
        content=[
            {
                "type": "text",
                "text": "Catch Up and Email Sweep",
                "extras": {"signature": "thought_sig_xyz"},
            }
        ]
    )

    with patch("nexus.core.constants.get_chat_model", return_value=mock_model):
        response = client.post(f"/api/agents/ask/conversations/{temp_conv}/auto-title")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        # Verify the raw string block was unpacked to clean text
        assert data["title"] == "Catch Up and Email Sweep"
        assert not data["title"].startswith("[{")


@pytest.mark.anyio
def test_auto_generate_title_graceful_fallback_on_error(client, temp_conv):
    """Verify that when the LLM call fails, auto-title falls back gracefully to a prompt excerpt without crashing."""
    prompt_text = "What is the recommended design pattern for distributed task queues?"
    log_message(
        role="user",
        content=prompt_text,
        conversation_id=temp_conv,
    )

    mock_model = AsyncMock()
    mock_model.ainvoke.side_effect = RuntimeError("API key quota exceeded")

    with patch("nexus.core.constants.get_chat_model", return_value=mock_model):
        response = client.post(f"/api/agents/ask/conversations/{temp_conv}/auto-title")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert data.get("fallback") is True
        # Verify fallback title was generated from prompt
        assert "What is the recommended" in data["title"]


def test_auto_generate_title_empty_conversation(client, temp_conv):
    """Verify that auto-titling a conversation without any user messages leaves the title unchanged."""
    response = client.post(f"/api/agents/ask/conversations/{temp_conv}/auto-title")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unchanged"
    assert data["title"] == "Temporary Title"


def test_ask_brain_stream_mocked(client, temp_conv):
    """Verify that POST /api/agents/ask/stream yields SSE packets and completes with a terminal 'done' packet."""
    mock_result = {
        "response": "Here is the simulated test response.",
        "domain": "general",
        "confidence": 0.95,
        "reasoning": "Mock test routing",
        "model_tier": "low",
        "model_name": "gemini-4-hydrogen",
    }
    with patch("nexus.agent.api.run_nexus_agent_with_trace", return_value=mock_result), patch(
        "nexus.api.routers.agents.schedule_auto_title"
    ) as mock_schedule:
        with client.stream(
            "POST",
            "/api/agents/ask/stream",
            json={
                "query": "Hello test stream",
                "conversation_id": temp_conv,
                "model_tier": "low",
            },
        ) as response:
            assert response.status_code == 200
            lines = [line for line in response.iter_lines() if line]
            assert any("done" in line for line in lines)
        mock_schedule.assert_called_once_with(temp_conv)


def test_stream_triggers_real_background_auto_title(client, temp_conv):
    """Verify /ask/stream schedules and completes backend Turn-1 auto-titling in SQLite."""
    import time
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    mock_result = {
        "response": "Here is the simulated test response.",
        "domain": "general",
        "confidence": 0.95,
        "reasoning": "Mock test routing",
        "model_tier": "low",
        "model_name": "gemini-4-hydrogen",
    }
    mock_model = MagicMock()
    mock_model.invoke.return_value = SimpleNamespace(content="Streamed Thread Summary")

    with patch("nexus.agent.api.run_nexus_agent_with_trace", return_value=mock_result), patch(
        "nexus.core.constants.get_chat_model", return_value=mock_model
    ):
        with client.stream(
            "POST",
            "/api/agents/ask/stream",
            json={
                "query": "How does WAL mode improve SQLite concurrency?",
                "conversation_id": temp_conv,
                "model_tier": "low",
            },
        ) as response:
            assert response.status_code == 200
            lines = [line for line in response.iter_lines() if line]
            assert any("done" in line for line in lines)

        # Wait briefly for the bounded background executor to persist the generated title
        deadline = time.monotonic() + 5.0
        conv = chats_db.get_conversation(temp_conv)
        while time.monotonic() < deadline and (conv or {}).get("title_source") != "auto":
            time.sleep(0.05)
            conv = chats_db.get_conversation(temp_conv)

    assert conv is not None
    assert conv["title"] == "Streamed Thread Summary"
    assert conv["title_source"] == "auto"
    assert mock_model.invoke.call_count == 1


def test_concurrent_auto_title_coalesces_single_llm_call(temp_conv):
    """Verify per-conversation _inflight_titles lock coalesces parallel non-forced requests into one LLM call."""
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import time
    from types import SimpleNamespace

    chats_db.log_message("user", "Design a thread-safe SQLite connection wrapper", conversation_id=temp_conv)
    chats_db.log_message("assistant", "Use contextlib.contextmanager to close handles cleanly.", conversation_id=temp_conv)

    call_count = 0
    call_lock = threading.Lock()
    entered_invoke = threading.Event()

    class SlowFakeModel:
        def invoke(self, _prompt):
            nonlocal call_count
            with call_lock:
                call_count += 1
            entered_invoke.set()
            time.sleep(0.15)
            return SimpleNamespace(content="Thread-Safe SQLite Wrapper")

    from nexus.core.chat_titles import auto_generate_title_sync

    with patch("nexus.core.constants.get_chat_model", return_value=SlowFakeModel()):
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(auto_generate_title_sync, temp_conv, force=False)
                for _ in range(4)
            ]
            assert entered_invoke.wait(timeout=3.0)
            results = [f.result(timeout=5.0) for f in futures]

    assert call_count == 1
    assert all(r["title"] == "Thread-Safe SQLite Wrapper" for r in results)
    conv = chats_db.get_conversation(temp_conv)
    assert conv["title"] == "Thread-Safe SQLite Wrapper"
    assert conv["title_source"] == "auto"


def test_auto_title_cas_does_not_overwrite_manual_rename_mid_flight(temp_conv):
    """Verify atomic SQLite CAS refuses to overwrite a manual rename made while LLM titling is in flight."""
    from types import SimpleNamespace

    chats_db.log_message("user", "Initial placeholder prompt", conversation_id=temp_conv)
    chats_db.log_message("assistant", "Initial assistant response", conversation_id=temp_conv)

    class RacingFakeModel:
        def invoke(self, _prompt):
            # Simulate user manually renaming the thread right before the AI title commits
            chats_db.update_conversation_title(temp_conv, "User Custom Title", source="manual")
            return SimpleNamespace(content="Stale AI Title")

    from nexus.core.chat_titles import auto_generate_title_sync

    with patch("nexus.core.constants.get_chat_model", return_value=RacingFakeModel()):
        res = auto_generate_title_sync(temp_conv, force=False)

    assert res["status"] == "unchanged"
    assert res.get("skipped_race") is True
    assert res["title"] == "User Custom Title"
    conv = chats_db.get_conversation(temp_conv)
    assert conv["title"] == "User Custom Title"
    assert conv["title_source"] == "manual"


def test_branch_placeholder_auto_title_preserves_prefix_and_skips_brief(temp_conv):
    """Verify branch placeholder titling skips synthetic branch_context briefs and keeps the branch badge."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from nexus.core.chat_branching import fork_conversation

    root_u = chats_db.log_message("user", "Root question about Kubernetes pods", conversation_id=temp_conv)
    chats_db.log_message("assistant", "Root answer about pods.", conversation_id=temp_conv)

    branch_res = fork_conversation(
        parent_conversation_id=temp_conv,
        parent_message_id=root_u,
        branch_mode="tangent",
    )
    branch_id = branch_res["conversation_id"]
    branch_conv = chats_db.get_conversation(branch_id)
    assert branch_conv["title_source"] == "placeholder"
    assert branch_conv["title"].startswith("🌿 ")

    # Inject a synthetic branch_context brief plus a real branch turn
    chats_db.log_message(
        "assistant",
        "SYNTHETIC_BRANCH_BRIEF_SHOULD_BE_IGNORED",
        agent="branch_context",
        conversation_id=branch_id,
    )
    chats_db.log_message("user", "Explain atomic compare-and-swap in SQLite", conversation_id=branch_id)
    chats_db.log_message("assistant", "Use conditional WHERE clauses.", conversation_id=branch_id)

    mock_model = MagicMock()
    mock_model.invoke.return_value = SimpleNamespace(content="Atomic SQLite CAS")

    from nexus.core.chat_titles import auto_generate_title_sync

    with patch("nexus.core.constants.get_chat_model", return_value=mock_model):
        res = auto_generate_title_sync(branch_id, force=False)

    sent_prompt = mock_model.invoke.call_args[0][0]
    assert "SYNTHETIC_BRANCH_BRIEF_SHOULD_BE_IGNORED" not in sent_prompt
    assert "Explain atomic compare-and-swap" in sent_prompt
    assert res["title"] == "🌿 Atomic SQLite CAS"
    updated_branch = chats_db.get_conversation(branch_id)
    assert updated_branch["title"] == "🌿 Atomic SQLite CAS"
    assert updated_branch["title_source"] == "auto"


def test_force_false_skips_auto_and_legacy_titles_and_conn_closes(client, tmp_path, monkeypatch):
    """Verify legacy DB migration sets title_source='legacy', ?force=false respects it, and _get_conn closes handles."""
    import sqlite3

    db_path = tmp_path / "legacy_chats.db"
    # Pre-seed a legacy conversations table without the new title_source column
    raw_conn = sqlite3.connect(str(db_path))
    raw_conn.execute(
        """
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT 'New Chat',
            created_at TEXT,
            last_updated TEXT
        )
        """
    )
    raw_conn.execute("INSERT INTO conversations (id, title) VALUES ('legacy-conv', 'Existing Legacy Title')")
    raw_conn.commit()
    raw_conn.close()

    monkeypatch.setattr(chats_db, "DB_PATH", db_path)
    chats_db.init_db()

    legacy = chats_db.get_conversation("legacy-conv")
    assert legacy is not None
    assert legacy["title_source"] == "legacy"

    chats_db.log_message("user", "Legacy user prompt", conversation_id="legacy-conv")
    # Non-forced auto-title (used by automatic GUI sync) must NOT overwrite legacy titles
    res_skip = client.post("/api/agents/ask/conversations/legacy-conv/auto-title?force=false")
    assert res_skip.status_code == 200
    assert res_skip.json()["status"] == "unchanged"
    assert res_skip.json()["title"] == "Existing Legacy Title"

    # Forced auto-title (`✨` sparkle button) MUST override and mark as 'auto'
    from unittest.mock import AsyncMock, MagicMock
    mock_model = AsyncMock()
    mock_model.ainvoke.return_value = MagicMock(content="Regenerated Title")
    with patch("nexus.core.constants.get_chat_model", return_value=mock_model):
        res_force = client.post("/api/agents/ask/conversations/legacy-conv/auto-title?force=true")
    assert res_force.status_code == 200
    assert res_force.json()["title"] == "Regenerated Title"
    assert chats_db.get_conversation("legacy-conv")["title_source"] == "auto"

    # Subsequent non-forced call skips 'auto' titles too
    res_skip_auto = client.post("/api/agents/ask/conversations/legacy-conv/auto-title?force=false")
    assert res_skip_auto.status_code == 200
    assert res_skip_auto.json()["status"] == "unchanged"
    assert res_skip_auto.json()["title"] == "Regenerated Title"

    # Verify _get_conn closes file descriptors cleanly (no leaked open handle locking Windows unlink)
    db_path.unlink()
    assert not db_path.exists()


