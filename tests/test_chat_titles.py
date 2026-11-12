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

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from nexus.api.main import app
from nexus.core.chats_db import (
    create_conversation,
    get_conversation,
    get_conversations,
    delete_conversation,
    log_message,
)


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
    with patch("nexus.agent.api.run_nexus_agent_with_trace", return_value=mock_result):
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

