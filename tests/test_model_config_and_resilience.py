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
from langchain_core.tools import tool

from nexus.agent.api import run_nexus_agent_with_trace
from nexus.agent.graph import (
    _cooperative_sleep,
    _extract_retry_delay,
    _invoke_llm_with_resilience,
    _invoke_tool_node_resilient,
    _is_rate_limit_error,
    call_model,
)
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
    assert any(m["id"] == "claude-opus-5-5" and m["tier"] == "strong" and m["provider"] == "anthropic" for m in catalog["models"])
    assert any(m["id"] == "claude-sonnet-4-5" and m["tier"] == "low" and m["provider"] == "anthropic" for m in catalog["models"])

    low_cfg = resolve_model_config("low")
    assert low_cfg["tier"] == "low"

    opus_cfg = resolve_model_config("claude-opus-5-5")
    assert opus_cfg["tier"] == "strong"
    assert opus_cfg["provider"] == "anthropic"
    assert opus_cfg["model_name"] == "claude-opus-5-5"

    sonnet_cfg = resolve_model_config("claude-sonnet-4-5")
    assert sonnet_cfg["tier"] == "low"
    assert sonnet_cfg["provider"] == "anthropic"
    assert sonnet_cfg["model_name"] == "claude-sonnet-4-5"

    # Verify ChatAnthropic instantiation when selecting an Anthropic model
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    anthropic_llm = get_chat_model(tier="claude-opus-5-5")
    assert getattr(anthropic_llm, "model", None) == "claude-opus-5-5"

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

    # Verify selecting an Anthropic model in call_model sets _active_turn_provider to "anthropic"
    call_model(state, config={"configurable": {"thread_id": "t1", "model_tier": "claude-opus-5-5"}})
    import nexus.agent.graph as graph_mod
    assert graph_mod._active_turn_provider == "anthropic"
    assert resolve_model_config(f"{graph_mod._active_turn_provider}:low")["model_name"] == "claude-sonnet-4-5"


def test_run_nexus_agent_with_trace_executor_shutdown_diagnostic_message(monkeypatch: pytest.MonkeyPatch):
    """Verify run_nexus_agent_with_trace translates Python ThreadPoolExecutor shutdown errors into clear reload guidance."""
    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = RuntimeError("cannot schedule new futures after shutdown")
    monkeypatch.setattr("nexus.agent.api.nexus_graph", mock_graph)

    res = run_nexus_agent_with_trace(query="peep that Tennr email", thread_id="test_shutdown_thread")
    assert "interrupted mid-turn because the backend server reloaded or shut down" in res["response"]
    assert "cannot schedule new futures after shutdown" not in res["response"]
    assert res["confidence"] == 0.0


def test_invoke_tool_node_resilient_fallback_on_executor_shutdown():
    """Verify _invoke_tool_node_resilient executes tools synchronously in-thread when ToolNode's thread pool is shut down."""
    @tool
    def dummy_read(path: str) -> str:
        """Read a dummy note."""
        return f"contents of {path}"

    mock_node = MagicMock()
    mock_node.invoke.side_effect = RuntimeError("cannot schedule new futures after shutdown")
    mock_node.tools_by_name = {"dummy_read": dummy_read}

    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": "dummy_read", "args": {"path": "Mission - Tennr.md"}, "id": "call_123"}],
    )
    out = _invoke_tool_node_resilient(mock_node, {"messages": [ai_msg]})
    assert len(out["messages"]) == 1
    assert out["messages"][0].content == "contents of Mission - Tennr.md"
    assert out["messages"][0].tool_call_id == "call_123"
    assert out["messages"][0].name == "dummy_read"

    # Unrelated RuntimeErrors must still propagate normally
    mock_node.invoke.side_effect = RuntimeError("unrelated runtime failure")
    with pytest.raises(RuntimeError, match="unrelated runtime failure"):
        _invoke_tool_node_resilient(mock_node, {"messages": [ai_msg]})


def test_is_rate_limit_error_classification():
    """Verify _is_rate_limit_error identifies 429 status codes, RESOURCE_EXHAUSTED, and quota keywords."""
    # Google AI Studio / gRPC 429 errors
    assert _is_rate_limit_error(Exception("429 RESOURCE_EXHAUSTED. Quota exceeded for metric..."))
    assert _is_rate_limit_error(Exception("Error calling model 'gemini-3.8-flash' (RESOURCE_EXHAUSTED)"))
    assert _is_rate_limit_error(Exception("Rate limit reached for requests per minute"))

    # Object with status_code attribute
    class DummyHttpError(Exception):
        status_code = 429

    assert _is_rate_limit_error(DummyHttpError("Too Many Requests"))

    # Non-rate-limit errors must return False
    assert not _is_rate_limit_error(Exception("504 DEADLINE_EXCEEDED"))
    assert not _is_rate_limit_error(ValueError("Invalid argument format"))
    assert not _is_rate_limit_error(RuntimeError("Connection reset by peer"))


def test_extract_retry_delay_from_payloads():
    """Verify _extract_retry_delay extracts structured and natural-language delays with safety buffer."""
    # 1. Google AI Studio structured RetryInfo dict format
    google_err = Exception(
        "{'error': {'code': 429, 'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '23s'}]}}"
    )
    # 23 + 1.5s buffer = 24.5s
    assert _extract_retry_delay(google_err) == 24.5

    # 2. Google AI Studio decimal delay in message
    google_decimal_err = Exception(
        "Generate content input tokens per minute limit exceeded on Tier 1. Please retry in 23.991883049s."
    )
    assert abs(_extract_retry_delay(google_decimal_err) - (23.991883049 + 1.5)) < 1e-4

    # 3. Natural language 'try again in Xs'
    natural_err = Exception("Rate limit reached. Please try again in 18s.")
    assert _extract_retry_delay(natural_err) == 19.5

    # 4. HTTP retry-after header pattern
    header_err = Exception("HTTP 429: retry-after: 12")
    assert _extract_retry_delay(header_err) == 13.5

    # 5. Fallback exponential backoff when no delay is present
    generic_429 = Exception("429 Too Many Requests")
    assert _extract_retry_delay(generic_429, attempt=0) == 15.0
    assert _extract_retry_delay(generic_429, attempt=1) == 30.0
    assert _extract_retry_delay(generic_429, attempt=2) == 60.0


def test_cooperative_sleep_cancellation():
    """Verify _cooperative_sleep polls thread cancellation and raises InterruptedError immediately."""
    import threading
    from nexus.agent.graph import register_cancel_event, unregister_cancel_event

    thread_id = "test_coop_sleep_thread"
    event = threading.Event()
    register_cancel_event(thread_id, event)

    # Signal stop before or during sleep
    event.set()
    try:
        with pytest.raises(InterruptedError, match="stopped by user during rate-limit backoff"):
            _cooperative_sleep(10.0, [thread_id])
    finally:
        unregister_cancel_event(thread_id)


def test_invoke_llm_with_resilience_retries_and_succeeds(monkeypatch: pytest.MonkeyPatch):
    """Verify _invoke_llm_with_resilience catches 429, logs telemetry, sleeps, and returns subsequent success."""
    mock_llm = MagicMock()
    # Fail twice with 429, succeed on attempt 3
    expected_response = AIMessage(content="Success after backoff")
    mock_llm.invoke.side_effect = [
        Exception("429 RESOURCE_EXHAUSTED. Please retry in 5s."),
        Exception("429 RESOURCE_EXHAUSTED. {'retryDelay': '2s'}"),
        expected_response,
    ]

    slept_intervals: list[float] = []

    def fake_sleep(seconds: float, thread_ids: list):
        slept_intervals.append(seconds)

    monkeypatch.setattr("nexus.agent.graph._cooperative_sleep", fake_sleep)

    mock_tracer = MagicMock()
    res = _invoke_llm_with_resilience(
        llm=mock_llm,
        messages=[HumanMessage(content="Hello")],
        tracer=mock_tracer,
        thread_ids=["test_thread"],
        model_name="gemini-3.8-flash",
        tier="low",
        max_retries=3,
    )

    assert res == expected_response
    assert mock_llm.invoke.call_count == 3
    # Verify 2 sleep intervals were executed with provider delay + 1.5s buffer
    assert len(slept_intervals) == 2
    assert slept_intervals[0] == 6.5  # 5 + 1.5
    assert slept_intervals[1] == 3.5  # 2 + 1.5
    assert mock_tracer.info.call_count == 2


def test_invoke_llm_with_resilience_exhaustion(monkeypatch: pytest.MonkeyPatch):
    """Verify _invoke_llm_with_resilience raises when max_retries are exhausted."""
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = Exception("429 RESOURCE_EXHAUSTED. Quota exceeded.")

    monkeypatch.setattr("nexus.agent.graph._cooperative_sleep", lambda sec, tids: None)
    mock_tracer = MagicMock()

    with pytest.raises(Exception, match="429 RESOURCE_EXHAUSTED"):
        _invoke_llm_with_resilience(
            llm=mock_llm,
            messages=[HumanMessage(content="Hello")],
            tracer=mock_tracer,
            thread_ids=["test_thread"],
            model_name="gemini-3.8-flash",
            tier="low",
            max_retries=2,
        )

    # 1 initial + 2 retries = 3 calls
    assert mock_llm.invoke.call_count == 3


def test_run_nexus_agent_with_trace_429_diagnostic_message(monkeypatch: pytest.MonkeyPatch):
    """Verify run_nexus_agent_with_trace translates 429 RESOURCE_EXHAUSTED into clear user guidance."""
    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = Exception(
        "Error calling model 'gemini-3.8-flash' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. Quota exceeded for metric..."
    )
    monkeypatch.setattr("nexus.agent.api.nexus_graph", mock_graph)

    res = run_nexus_agent_with_trace(query="Process all Keep notes", thread_id="test_429_thread")
    assert "429 RESOURCE_EXHAUSTED" in res["response"]
    assert "token-per-minute (TPM)" in res["response"]
    assert "sliding windows typically roll over within 20–60 seconds" in res["response"]
    assert res["confidence"] == 0.0


