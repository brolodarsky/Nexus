"""
test_model_config_and_resilience.py — Unit tests for AI client timeout configurations and tier fallback resilience.

Tests:
  1. EngineSettings timeout & retry defaults and overrides.
  2. get_chat_model binds timeout and max_retries into ChatGoogleGenerativeAI and ChatOpenAI.
  3. call_model catches 504 DEADLINE_EXCEEDED on primary model and falls back to low-latency tier.
  4. run_nexus_agent_with_trace returns clear diagnostic guidance on 504 DEADLINE_EXCEEDED.
"""
from unittest.mock import MagicMock, patch
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from nexus.agent.api import run_nexus_agent_with_trace
from nexus.agent.graph import call_model
from nexus.core.config import EngineSettings
from nexus.core.constants import get_available_models, get_chat_model, resolve_model_config


def test_engine_settings_timeout_and_retries_defaults(monkeypatch: pytest.MonkeyPatch):
    """Verify EngineSettings default timeout is 300s (5m) and max_retries is 3, with .env override support."""
    # Test default values
    settings = EngineSettings()
    assert settings.ai_request_timeout == 300
    assert settings.ai_max_retries == 3

    # Test environment variable overrides
    monkeypatch.setenv("AI_REQUEST_TIMEOUT", "240")
    monkeypatch.setenv("AI_MAX_RETRIES", "5")
    custom_settings = EngineSettings()
    assert custom_settings.ai_request_timeout == 240
    assert custom_settings.ai_max_retries == 5


def test_get_chat_model_applies_timeout_and_retries(monkeypatch: pytest.MonkeyPatch):
    """Verify get_chat_model extracts timeout and retries from EngineSettings and applies to clients."""
    monkeypatch.setenv("AI_REQUEST_TIMEOUT", "200")
    monkeypatch.setenv("AI_MAX_RETRIES", "4")
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-xyz")

    gemini_model = get_chat_model(tier="low")
    assert getattr(gemini_model, "timeout", None) == 200
    assert getattr(gemini_model, "max_retries", None) == 4

    # Test OpenAI client path
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    openai_model = get_chat_model(tier="low")
    assert getattr(openai_model, "request_timeout", None) == 200 or getattr(openai_model, "timeout", None) == 200
    assert getattr(openai_model, "max_retries", None) == 4


def test_call_model_falls_back_on_504_deadline_exceeded(monkeypatch: pytest.MonkeyPatch):
    """Verify call_model gracefully falls back to low-latency tier on 504 DEADLINE_EXCEEDED."""
    monkeypatch.setattr("nexus.agent.graph.settings.nexus_primary_tier", "strong")

    # Mock the strong model to simulate a 504 DEADLINE_EXCEEDED exception
    mock_strong_llm = MagicMock()
    mock_strong_bound = MagicMock()
    mock_strong_llm.bind_tools.return_value = mock_strong_bound
    mock_strong_bound.invoke.side_effect = Exception("504 DEADLINE_EXCEEDED. {'error': {'code': 504, 'message': 'Deadline expired'}}")

    # Mock the fallback low-tier model to succeed
    mock_fallback_llm = MagicMock()
    mock_fallback_bound = MagicMock()
    mock_fallback_llm.bind_tools.return_value = mock_fallback_bound
    expected_response = AIMessage(content="Fallback response from Flash")
    mock_fallback_bound.invoke.return_value = expected_response

    def mock_get_chat_model(tier=None, temperature=0.0):
        if tier == "low":
            return mock_fallback_llm
        return mock_strong_llm

    monkeypatch.setattr("nexus.agent.graph.get_chat_model", mock_get_chat_model)

    state = {"messages": [HumanMessage(content="Heavy analysis task")]}
    result = call_model(state)

    assert result["messages"] == [expected_response]
    mock_strong_bound.invoke.assert_called_once()
    mock_fallback_bound.invoke.assert_called_once()


def test_run_nexus_agent_with_trace_504_diagnostic_message(monkeypatch: pytest.MonkeyPatch):
    """Verify run_nexus_agent_with_trace emits an actionable diagnostic message on 504 errors."""
    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = Exception("504 DEADLINE_EXCEEDED. Deadline expired before operation could complete.")
    monkeypatch.setattr("nexus.agent.api.nexus_graph", mock_graph)

    res = run_nexus_agent_with_trace(query="Test query", thread_id="test_thread")
    assert "504 DEADLINE_EXCEEDED" in res["response"]
    assert "provider deadline timeout" in res["response"]
    assert res["confidence"] == 0.0


def test_per_turn_model_tier_routing_and_catalog(monkeypatch: pytest.MonkeyPatch):
    """Verify per-turn model_tier in RunnableConfig routes call_model to the selected tier and get_available_models returns catalog."""
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-xyz")

    catalog = get_available_models()
    assert catalog["provider"] == "gemini"
    assert any(m["id"] == "strong" for m in catalog["models"])
    assert any(m["id"] == "low" for m in catalog["models"])

    low_cfg = resolve_model_config("low")
    assert low_cfg["tier"] == "low"

    recorded_tiers: list[str | None] = []
    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_llm.bind_tools.return_value = mock_bound
    mock_bound.invoke.return_value = AIMessage(content="Fast turn response")

    def fake_get_chat_model(tier=None, temperature=0.0):
        recorded_tiers.append(tier)
        return mock_llm

    monkeypatch.setattr("nexus.agent.graph.get_chat_model", fake_get_chat_model)

    state = {"messages": [HumanMessage(content="Quick question")]}
    call_model(state, config={"configurable": {"thread_id": "t1", "model_tier": "low"}})
    assert recorded_tiers == ["low"]
