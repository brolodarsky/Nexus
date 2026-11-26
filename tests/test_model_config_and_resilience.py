"""
test_model_config_and_resilience.py — Unit tests for AI client timeout configurations and tier fallback resilience.

Tests:
  1. EngineSettings timeout & retry defaults and overrides.
  2. get_chat_model binds timeout and max_retries into ChatGoogleGenerativeAI and ChatOpenAI.
  3. call_model catches 504 DEADLINE_EXCEEDED on primary model and falls back to low-latency tier.
  4. run_nexus_agent_with_trace returns clear diagnostic guidance on 504 DEADLINE_EXCEEDED.
"""
from unittest.mock import MagicMock, patch
import base64
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from nexus.agent.api import prepend_current_time_to_prompt, run_nexus_agent_with_trace
from nexus.agent.graph import call_model
from nexus.agent.runtime import (
    _build_system_message,
    _cooperative_sleep,
    _extract_retry_delay,
    _invoke_llm_with_resilience,
    _invoke_tool_node_resilient,
    _is_invalid_signature_error,
    _is_rate_limit_error,
    register_cancel_event,
    unregister_cancel_event,
)
from nexus.agent.sanitization import (
    _infer_message_provider,
    _sanitize_messages_for_provider,
    extract_message_text,
    extract_message_thinking,
)
from nexus.core.config import EngineSettings
from nexus.core.constants import get_available_models, get_chat_model, resolve_model_config
from nexus.core.engine_constitution import inject_root_instructions


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
    assert [m["label"] for m in catalog["models"]] == [
        "Gemini 4 Argon",
        "Gemini 4 Hydrogen",
        "Gemini 3.8 Flash",
        "Claude Opus 5.5",
        "Claude Sonnet 5.5",
        "Claude Haiku 5.5",
    ]

    for entry in catalog["models"]:
        assert entry["description"]
        assert entry["description"].endswith(".")
        assert entry["model_name"] not in entry["description"]
        assert "pricing" in entry
        assert entry["pricing"]["summary"].startswith("$")
        assert entry["pricing"]["input_per_m"] > 0
        assert entry["pricing"]["output_per_m"] > 0
        assert entry["pricing"]["cached_per_m"] > 0

    strong_entry = next(m for m in catalog["models"] if m["id"] == "strong")
    assert strong_entry["model_name"] == "gemini-4-argon"
    assert strong_entry["pricing"]["summary"] == "$2 / $10"

    hydrogen_entry = next(m for m in catalog["models"] if m["id"] == "gemini-4-hydrogen")
    assert hydrogen_entry["model_name"] == "gemini-4-hydrogen"
    assert hydrogen_entry["provider"] == "gemini"
    assert hydrogen_entry["tier"] == "medium"
    assert hydrogen_entry["pricing"]["summary"] == "$1.50 / $7.50"

    low_entry = next(m for m in catalog["models"] if m["id"] == "low")
    assert low_entry["model_name"] == "gemini-3.8-flash"
    assert low_entry["pricing"]["summary"] == "$0.75 / $3.75"

    assert any(
        m["id"] == "claude-opus-5-5"
        and m["tier"] == "strong"
        and m["provider"] == "anthropic"
        and m["pricing"]["summary"] == "$4 / $20"
        for m in catalog["models"]
    )
    assert any(
        m["id"] == "claude-sonnet-5-5"
        and m["tier"] == "medium"
        and m["provider"] == "anthropic"
        and m["short_label"] == "Sonnet 5.5"
        and m["pricing"]["summary"] == "$2 / $10"
        for m in catalog["models"]
    )
    assert any(
        m["id"] == "claude-haiku-5-5"
        and m["tier"] == "low"
        and m["provider"] == "anthropic"
        and m["short_label"] == "Haiku 5.5"
        and m["pricing"]["summary"] == "$0.10 / $0.50"
        for m in catalog["models"]
    )

    low_cfg = resolve_model_config("low")
    assert low_cfg["tier"] == "low"
    assert low_cfg["model_name"] == "gemini-3.8-flash"

    med_cfg = resolve_model_config("medium")
    assert med_cfg["tier"] == "medium"
    assert med_cfg["model_name"] == "gemini-3.8-flash"

    hydrogen_cfg = resolve_model_config("gemini-4-hydrogen")
    assert hydrogen_cfg["tier"] == "low"
    assert hydrogen_cfg["provider"] == "gemini"
    assert hydrogen_cfg["model_name"] == "gemini-4-hydrogen"

    hydrogen_alias_cfg = resolve_model_config("hydrogen")
    assert hydrogen_alias_cfg["tier"] == "low"
    assert hydrogen_alias_cfg["provider"] == "gemini"

    opus_cfg = resolve_model_config("claude-opus-5-5")
    assert opus_cfg["tier"] == "strong"
    assert opus_cfg["provider"] == "anthropic"
    assert opus_cfg["model_name"] == "claude-opus-5-5"

    sonnet_cfg = resolve_model_config("claude-sonnet-5-5")
    assert sonnet_cfg["tier"] == "medium"
    assert sonnet_cfg["provider"] == "anthropic"
    assert sonnet_cfg["model_name"] == "claude-sonnet-5-5"

    sonnet_dot_cfg = resolve_model_config("claude-sonnet-5.5")
    assert sonnet_dot_cfg["tier"] == "medium"
    assert sonnet_dot_cfg["provider"] == "anthropic"
    assert sonnet_dot_cfg["model_name"] == "claude-sonnet-5-5"

    haiku_cfg = resolve_model_config("claude-haiku-5-5")
    assert haiku_cfg["tier"] == "low"
    assert haiku_cfg["provider"] == "anthropic"
    assert haiku_cfg["model_name"] == "claude-haiku-5-5"

    haiku_dot_cfg = resolve_model_config("claude-haiku-5.5")
    assert haiku_dot_cfg["tier"] == "low"
    assert haiku_dot_cfg["provider"] == "anthropic"
    assert haiku_dot_cfg["model_name"] == "claude-haiku-5-5"

    # Verify ChatAnthropic instantiation when selecting an Anthropic model
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    anthropic_llm = get_chat_model(tier="claude-opus-5-5")
    assert getattr(anthropic_llm, "model", None) == "claude-opus-5-5"
    assert getattr(anthropic_llm, "temperature", None) is None
    assert getattr(anthropic_llm, "model_kwargs", None) == {"cache_control": {"type": "ephemeral"}}

    sonnet55_llm = get_chat_model(tier="claude-sonnet-5-5")
    assert getattr(sonnet55_llm, "model", None) == "claude-sonnet-5-5"
    assert getattr(sonnet55_llm, "temperature", None) is None
    assert getattr(sonnet55_llm, "model_kwargs", None) == {"cache_control": {"type": "ephemeral"}}

    haiku55_llm = get_chat_model(tier="claude-haiku-5-5")
    assert getattr(haiku55_llm, "model", None) == "claude-haiku-5-5"
    assert getattr(haiku55_llm, "temperature", None) is None
    assert getattr(haiku55_llm, "model_kwargs", None) == {"cache_control": {"type": "ephemeral"}}

    legacy_sonnet_llm = get_chat_model(tier="claude-sonnet-4-5")
    assert getattr(legacy_sonnet_llm, "temperature", None) == 0.0
    assert getattr(legacy_sonnet_llm, "model_kwargs", None) == {"cache_control": {"type": "ephemeral"}}

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
    import nexus.agent.runtime as runtime_mod
    assert runtime_mod._active_turn_provider == "anthropic"
    assert resolve_model_config(f"{runtime_mod._active_turn_provider}:low")["model_name"] == "claude-haiku-5-5"
    assert resolve_model_config(f"{runtime_mod._active_turn_provider}:medium")["model_name"] == "claude-sonnet-5-5"


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
    assert _is_rate_limit_error(Exception("Error calling model 'gemini-4-hydrogen' (RESOURCE_EXHAUSTED)"))
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


def test_invoke_llm_with_resilience_temperature_deprecated_self_heals():
    """Verify _invoke_llm_with_resilience clears temperature and retries when a model deprecates temperature."""
    mock_llm = MagicMock()
    mock_llm.temperature = 0.0
    expected_response = AIMessage(content="Self-healed response")

    calls = []

    def fake_invoke(messages):
        calls.append(mock_llm.temperature)
        if len(calls) == 1:
            raise Exception("400 Bad Request: `temperature` is deprecated for this model.")
        return expected_response

    mock_llm.invoke.side_effect = fake_invoke

    tracer = MagicMock()
    result = _invoke_llm_with_resilience(
        llm=mock_llm,
        messages=[HumanMessage(content="Hello")],
        tracer=tracer,
        thread_ids=["test_thread"],
        model_name="claude-opus-5-5",
        tier="strong",
    )

    assert result == expected_response
    assert mock_llm.temperature is None
    assert len(calls) == 2
    tracer.info.assert_called_once()


def test_cooperative_sleep_cancellation():
    """Verify _cooperative_sleep polls thread cancellation and raises InterruptedError immediately."""
    import threading
    from nexus.agent.runtime import register_cancel_event, unregister_cancel_event

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

    monkeypatch.setattr("nexus.agent.runtime._cooperative_sleep", fake_sleep)

    mock_tracer = MagicMock()
    res = _invoke_llm_with_resilience(
        llm=mock_llm,
        messages=[HumanMessage(content="Hello")],
        tracer=mock_tracer,
        thread_ids=["test_thread"],
        model_name="gemini-4-hydrogen",
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

    monkeypatch.setattr("nexus.agent.runtime._cooperative_sleep", lambda sec, tids: None)
    mock_tracer = MagicMock()

    with pytest.raises(Exception, match="429 RESOURCE_EXHAUSTED"):
        _invoke_llm_with_resilience(
            llm=mock_llm,
            messages=[HumanMessage(content="Hello")],
            tracer=mock_tracer,
            thread_ids=["test_thread"],
            model_name="gemini-4-hydrogen",
            tier="low",
            max_retries=2,
        )

    # 1 initial + 2 retries = 3 calls
    assert mock_llm.invoke.call_count == 3


def test_run_nexus_agent_with_trace_429_diagnostic_message(monkeypatch: pytest.MonkeyPatch):
    """Verify run_nexus_agent_with_trace translates 429 RESOURCE_EXHAUSTED into clear user guidance."""
    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = Exception(
        "Error calling model 'gemini-4-hydrogen' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. Quota exceeded for metric..."
    )
    monkeypatch.setattr("nexus.agent.api.nexus_graph", mock_graph)

    res = run_nexus_agent_with_trace(query="Process all Keep notes", thread_id="test_429_thread")
    assert "429 RESOURCE_EXHAUSTED" in res["response"]
    assert "token-per-minute (TPM)" in res["response"]
    assert "sliding windows typically roll over within 20–60 seconds" in res["response"]
    assert res["confidence"] == 0.0


def test_tool_node_handle_tool_errors_interception():
    """Verify that ToolNode with handle_tool_errors=True catches unexpected tool exceptions and returns ToolMessage."""
    from langgraph.graph import StateGraph, MessagesState, START, END
    from langgraph.prebuilt import ToolNode

    @tool
    def exploding_tool(query: str) -> str:
        """A tool that raises an unexpected exception."""
        raise RuntimeError(f"Database crash during query: {query}")

    workflow = StateGraph(MessagesState)
    workflow.add_node("tools", ToolNode([exploding_tool], handle_tool_errors=True))
    workflow.add_edge(START, "tools")
    workflow.add_edge("tools", END)
    app = workflow.compile()

    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": "exploding_tool", "args": {"query": "SELECT *"}, "id": "call_err_1"}],
    )
    res = app.invoke({"messages": [ai_msg]})
    assert len(res["messages"]) == 2
    tool_msg = res["messages"][-1]
    assert tool_msg.status == "error"
    assert "Database crash during query" in tool_msg.content


def test_format_events_as_markdown_includes_event_ids():
    """Verify format_events_as_markdown embeds event IDs so agents can extract event_id for updates/deletions."""
    from nexus.shared_tools.calendar_engine import format_events_as_markdown

    sample_events = [
        {
            "id": "event_abc_123",
            "summary": "Deep Work Block",
            "start": "2026-11-12T13:30:00-05:00",
            "end": "2026-11-12T16:30:00-05:00",
            "description": "Focus on Nexus Engine",
        }
    ]
    md = format_events_as_markdown(sample_events, title="Today's Schedule")
    assert "event_abc_123" in md
    assert "(id: `event_abc_123`)" in md
    assert "Deep Work Block" in md


def test_update_calendar_event_handles_not_found_defensively(monkeypatch: pytest.MonkeyPatch):
    """Verify update_calendar_event intercepts 404 HttpError cleanly instead of bubbling uncaught."""
    from googleapiclient.errors import HttpError
    import httplib2
    from nexus.shared_tools.shared import update_calendar_event

    resp = httplib2.Response({"status": 404, "reason": "Not Found"})
    http_err = HttpError(resp, b"Not Found")

    # Mock service.events().patch().execute to simulate Google 404 Not Found
    mock_service = MagicMock()
    mock_service.events().patch().execute.side_effect = http_err
    monkeypatch.setattr("nexus.shared_tools.calendar_engine.get_calendar_service", lambda: mock_service)

    result = update_calendar_event.invoke({
        "event_id": "test",
        "summary": "Shifted Morning Block",
        "start_iso": "2026-11-12T12:45:00-05:00",
        "end_iso": "2026-11-12T13:30:00-05:00",
    })
    assert "❌ Failed to update calendar event 'test'" in result
    assert "404" in result
    assert "Verify event ID" in result


def test_delete_calendar_event_handles_errors_defensively(monkeypatch: pytest.MonkeyPatch):
    """Verify delete_calendar_event returns a clear status message on failure rather than crashing."""
    from googleapiclient.errors import HttpError
    import httplib2
    from nexus.shared_tools.shared import delete_calendar_event

    resp = httplib2.Response({"status": 404, "reason": "Not Found"})
    http_err = HttpError(resp, b"Not Found")

    mock_service = MagicMock()
    mock_service.events().delete().execute.side_effect = http_err
    monkeypatch.setattr("nexus.shared_tools.calendar_engine.get_calendar_service", lambda: mock_service)

    result = delete_calendar_event.invoke({"event_id": "nonexistent_event_id"})
    assert "❌ Failed to delete event 'nonexistent_event_id'" in result


def test_anthropic_prompt_caching_system_message(monkeypatch: pytest.MonkeyPatch):
    """Verify Anthropic turns receive ephemeral cache_control on SystemMessage while Gemini receives plain text."""
    anth_sys = _build_system_message("System constitution", "anthropic")
    assert isinstance(anth_sys.content, list)
    assert anth_sys.content[0]["type"] == "text"
    assert anth_sys.content[0]["text"] == "System constitution"
    assert anth_sys.content[0]["cache_control"] == {"type": "ephemeral"}

    gem_sys = _build_system_message("System constitution", "gemini")
    assert gem_sys.content == "System constitution"

    captured_messages = []
    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_llm.bind_tools.return_value = mock_bound

    def fake_invoke(msgs):
        captured_messages.extend(msgs)
        return AIMessage(content="Cached Claude reply")

    mock_bound.invoke.side_effect = fake_invoke
    monkeypatch.setattr("nexus.agent.graph.get_chat_model", lambda tier=None, temperature=0.0: mock_llm)

    call_model(
        {"messages": [HumanMessage(content="[Current Time: 2026-11-12 23:00]\n\nHello")]},
        config={"configurable": {"thread_id": "cache_test", "model_tier": "claude-opus-5-5"}},
    )
    assert len(captured_messages) >= 2
    sys_msg = captured_messages[0]
    assert isinstance(sys_msg.content, list)
    assert sys_msg.content[0]["cache_control"] == {"type": "ephemeral"}


def test_system_prompt_static_and_user_message_timestamp_injection(monkeypatch: pytest.MonkeyPatch):
    """Verify inject_root_instructions() omits dynamic timestamps and new user messages receive [Current Time: ...]."""
    inst1 = inject_root_instructions()
    inst2 = inject_root_instructions(cache_stable=False)
    assert inst1 == inst2
    assert "- Current Time:" not in inst1
    assert "{current_time}" not in inst1

    stamped = prepend_current_time_to_prompt("Review my Gameplan")
    assert stamped.startswith("[Current Time: ")
    assert stamped.endswith("]\n\nReview my Gameplan")
    # Idempotency check
    assert prepend_current_time_to_prompt(stamped) == stamped

    captured_state = {}
    mock_graph = MagicMock()

    def fake_invoke(state, config=None):
        captured_state.update(state)
        return {"messages": list(state["messages"]) + [AIMessage(content="Done")]}

    mock_graph.invoke.side_effect = fake_invoke
    monkeypatch.setattr("nexus.agent.api.nexus_graph", mock_graph)

    run_nexus_agent_with_trace(query="Check my calendar", thread_id="ts_test_thread")
    sent_human = captured_state["messages"][0]
    assert isinstance(sent_human, HumanMessage)
    assert sent_human.content.startswith("[Current Time: ")
    assert sent_human.content.endswith("]\n\nCheck my calendar")


def test_master_instructions_protocol_pointer_and_deduplication() -> None:
    """Verify Master Instructions points to [[Protocol - Email Triage]] and omits non-CLI modules & duplicate aliases."""
    from nexus.shared_tools.vault_reader import resolve_vault_note_path

    inst = inject_root_instructions()
    assert "[[Protocol - Email Triage]]" in inst
    assert "`nexus.shared_tools.shared`" not in inst
    assert "get_vault_structure" not in inst

    resolved_path, err = resolve_vault_note_path("Protocol - Email Triage.md")
    assert err is None
    assert resolved_path is not None
    assert resolved_path.as_posix().endswith(
        "Vault/1. Core/1.2. Personal Knowledge Management (PKM)/Protocol - Email Triage.md"
    )


def test_infer_message_provider_metadata_and_structural_markers() -> None:
    """Verify _infer_message_provider resolves Gemini, Anthropic, OpenAI, and plain synthetic AIMessages."""
    # Explicit model_provider metadata
    assert _infer_message_provider(AIMessage(content="hi", response_metadata={"model_provider": "google_genai"})) == "gemini"
    assert _infer_message_provider(AIMessage(content="hi", response_metadata={"model_provider": "anthropic"})) == "anthropic"
    assert _infer_message_provider(AIMessage(content="hi", response_metadata={"model_provider": "openai"})) == "openai"

    # Model-name fallback without model_provider
    assert _infer_message_provider(AIMessage(content="hi", response_metadata={"model_name": "gemini-4-hydrogen"})) == "gemini"
    assert _infer_message_provider(AIMessage(content="hi", response_metadata={"model": "claude-opus-5-5"})) == "anthropic"
    assert _infer_message_provider(AIMessage(content="hi", response_metadata={"model_name": "gpt-5.6-sol"})) == "openai"

    # Structural marker fallback without response_metadata
    gem_tc_msg = AIMessage(
        content="",
        tool_calls=[{"name": "read_file", "args": {}, "id": "tc_gem"}],
        additional_kwargs={"__gemini_function_call_thought_signatures__": {"tc_gem": "abc="}},
    )
    assert _infer_message_provider(gem_tc_msg) == "gemini"

    gem_text_sig_msg = AIMessage(
        content=[{"type": "text", "text": "done", "extras": {"signature": "abc="}}],
    )
    assert _infer_message_provider(gem_text_sig_msg) == "gemini"

    anth_redacted = AIMessage(content=[{"type": "redacted_thinking", "data": "xyz"}, {"type": "text", "text": "ok"}])
    assert _infer_message_provider(anth_redacted) == "anthropic"

    anth_tool_use = AIMessage(content=[{"type": "tool_use", "id": "tu_1", "name": "read_file", "input": {}}])
    assert _infer_message_provider(anth_tool_use) == "anthropic"

    # Plain synthetic AIMessage or HumanMessage
    assert _infer_message_provider(AIMessage(content="Plain reply")) is None
    assert _infer_message_provider(HumanMessage(content="User prompt")) is None


def test_sanitize_messages_for_gemini_strips_anthropic_preserves_gemini_and_parses() -> None:
    """Verify Anthropic -> Gemini sanitization drops foreign thinking/tool_use blocks while keeping Gemini signatures intact."""
    import langchain_google_genai.chat_models as google_cm

    anth_sig = base64.b64encode(b"anthropic-thinking-sig-bytes").decode("ascii")
    gem_tc_sig = base64.b64encode(b"gemini-fc-sig-bytes").decode("ascii")
    gem_text_sig = base64.b64encode(b"gemini-text-sig-bytes").decode("ascii")

    anth_tc_msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Claude reasoning", "signature": anth_sig},
            {"type": "redacted_thinking", "data": "opaque"},
            {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"file_path": "Note.md"}},
        ],
        tool_calls=[{"name": "read_file", "args": {"file_path": "Note.md"}, "id": "toolu_1"}],
        response_metadata={"model_provider": "anthropic", "model_name": "claude-opus-5-5", "output_version": "v1"},
    )
    anth_final_msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "More reasoning", "signature": anth_sig},
            {"type": "text", "text": "Claude final synthesis.", "cache_control": {"type": "ephemeral"}},
        ],
        response_metadata={"model_provider": "anthropic", "model_name": "claude-opus-5-5"},
    )
    gem_tc_msg = AIMessage(
        content="",
        tool_calls=[{"name": "read_file", "args": {"file_path": "Log.md"}, "id": "call_gem_1"}],
        additional_kwargs={
            "function_call": {"name": "read_file", "arguments": '{"file_path": "Log.md"}'},
            "__gemini_function_call_thought_signatures__": {"call_gem_1": gem_tc_sig},
        },
        response_metadata={"model_provider": "google_genai", "model_name": "gemini-4-hydrogen"},
    )
    gem_final_msg = AIMessage(
        content=[{"type": "text", "text": "Gemini synthesis.", "extras": {"signature": gem_text_sig}}],
        response_metadata={"model_provider": "google_genai", "model_name": "gemini-4-hydrogen"},
    )

    history = [
        HumanMessage(content="Turn 1"),
        anth_tc_msg,
        ToolMessage(content="Note body", name="read_file", tool_call_id="toolu_1"),
        anth_final_msg,
        HumanMessage(content="Turn 2"),
        gem_tc_msg,
        ToolMessage(content="Log body", name="read_file", tool_call_id="call_gem_1"),
        gem_final_msg,
        HumanMessage(content="Turn 3 on gemini-3.8-flash"),
    ]

    sanitized = _sanitize_messages_for_provider(history, "gemini")

    # Original persisted messages must never be mutated in place
    assert isinstance(anth_tc_msg.content, list) and anth_tc_msg.content[0]["type"] == "thinking"
    assert anth_final_msg.content[1]["cache_control"] == {"type": "ephemeral"}

    # Anthropic messages were replaced with stripped ephemeral copies
    assert sanitized[1] is not anth_tc_msg
    assert sanitized[1].content == ""
    assert sanitized[1].tool_calls == anth_tc_msg.tool_calls
    assert "output_version" not in sanitized[1].response_metadata

    assert sanitized[3] is not anth_final_msg
    assert sanitized[3].content == "Claude final synthesis."

    # Same-provider Gemini messages keep exact object identity and thought signatures (zero KV-cache churn)
    assert sanitized[5] is gem_tc_msg
    assert sanitized[5].additional_kwargs["__gemini_function_call_thought_signatures__"]["call_gem_1"] == gem_tc_sig
    assert sanitized[7] is gem_final_msg
    assert sanitized[7].content[0]["extras"]["signature"] == gem_text_sig

    # Serializing via langchain-google-genai for gemini-3.8-flash succeeds with zero ValueError and zero Anthropic thought parts
    _sys_instr, contents = google_cm._parse_chat_history(sanitized, model="gemini-3.8-flash")
    # Content[1] is stripped Anthropic tool-call turn: only function_call, no Anthropic thought signature
    assert all(not p.thought for p in (contents[1].parts or []))
    assert [p.function_call.name for p in (contents[1].parts or []) if p.function_call] == ["read_file"]
    # Content[3] is stripped Anthropic text turn: clean text, no thought signature
    assert [p.text for p in (contents[3].parts or [])] == ["Claude final synthesis."]
    assert all(p.thought_signature is None for p in (contents[3].parts or []))
    # Content[5] is untouched Gemini tool-call turn: original thought_signature bytes preserved
    assert contents[5].parts[0].thought_signature == b"gemini-fc-sig-bytes"
    # Content[7] is untouched Gemini text turn: original thought_signature bytes preserved
    assert contents[7].parts[0].thought_signature == b"gemini-text-sig-bytes"


def test_sanitize_messages_cross_provider_anthropic_openai_and_empty_blocks() -> None:
    """Verify Gemini -> Anthropic, cross-provider -> OpenAI, and empty thinking-only collapse guards."""
    anth_sig = base64.b64encode(b"anth-sig").decode("ascii")
    gem_sig = base64.b64encode(b"gem-sig").decode("ascii")

    gem_msg = AIMessage(
        content=[{"type": "text", "text": "Gemini text.", "extras": {"signature": gem_sig}}],
        additional_kwargs={"__gemini_function_call_thought_signatures__": {"tc_1": gem_sig}},
        tool_calls=[{"name": "search_vault", "args": {"query": "x"}, "id": "tc_1"}],
        response_metadata={"model_provider": "google_genai", "model_name": "gemini-4-argon"},
    )
    anth_msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Internal thought", "signature": anth_sig},
            {"type": "text", "text": "Anthropic text.", "cache_control": {"type": "ephemeral"}},
        ],
        response_metadata={"model_provider": "anthropic", "model_name": "claude-opus-5-5"},
    )
    thinking_only_tc = AIMessage(
        content=[{"type": "thinking", "thinking": "Only thinking", "signature": anth_sig}],
        tool_calls=[{"name": "read_file", "args": {"file_path": "a.md"}, "id": "tc_only"}],
        response_metadata={"model_provider": "anthropic"},
    )
    thinking_only_no_tc = AIMessage(
        content=[{"type": "thinking", "thinking": "Only thinking", "signature": anth_sig}],
        response_metadata={"model_provider": "anthropic"},
    )

    # Gemini -> Anthropic: strips Gemini signatures while keeping Anthropic messages identical
    for_anthropic = _sanitize_messages_for_provider([gem_msg, anth_msg], "anthropic")
    assert for_anthropic[0] is not gem_msg
    assert for_anthropic[0].content == "Gemini text."
    assert "__gemini_function_call_thought_signatures__" not in for_anthropic[0].additional_kwargs
    assert for_anthropic[1] is anth_msg  # same provider untouched

    # Cross-provider -> OpenAI: strips both Gemini and Anthropic artifacts
    for_openai = _sanitize_messages_for_provider([gem_msg, anth_msg], "openai")
    assert for_openai[0].content == "Gemini text."
    assert "__gemini_function_call_thought_signatures__" not in for_openai[0].additional_kwargs
    assert for_openai[1].content == "Anthropic text."

    # Empty content guards after stripping thinking blocks
    collapsed = _sanitize_messages_for_provider([thinking_only_tc, thinking_only_no_tc], "gemini")
    assert collapsed[0].content == ""
    assert collapsed[0].tool_calls == thinking_only_tc.tool_calls
    assert collapsed[1].content == "(no text)"


def test_call_model_sanitizes_cross_provider_history_without_mutating_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify call_model sanitizes foreign-provider thinking signatures before invoking LLM while leaving state untouched."""
    anth_sig = base64.b64encode(b"anth-sig").decode("ascii")
    anth_msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Plan", "signature": anth_sig},
            {"type": "text", "text": "Checked file."},
        ],
        response_metadata={"model_provider": "anthropic", "model_name": "claude-opus-5-5"},
    )
    state_msgs = [
        HumanMessage(content="Check file"),
        anth_msg,
        HumanMessage(content="Now reply using Flash"),
    ]

    captured_payload: list = []
    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_llm.bind_tools.return_value = mock_bound

    def fake_invoke(msgs):
        captured_payload.extend(msgs)
        return AIMessage(content="Flash response")

    mock_bound.invoke.side_effect = fake_invoke
    monkeypatch.setattr("nexus.agent.graph.get_chat_model", lambda tier=None, temperature=0.0: mock_llm)

    call_model({"messages": state_msgs}, config={"configurable": {"thread_id": "t_cross", "model_tier": "low"}})

    # First message is ephemeral SystemMessage; index 2 is the sanitized Anthropic AIMessage
    sent_anth = captured_payload[2]
    assert sent_anth is not anth_msg
    assert sent_anth.content == "Checked file."
    # Original state AIMessage retains its thinking block and signature intact
    assert isinstance(anth_msg.content, list) and anth_msg.content[0]["signature"] == anth_sig


def test_invoke_llm_with_resilience_self_heals_invalid_thought_signature() -> None:
    """Verify _invoke_llm_with_resilience strips signatures once on INVALID_THOUGHT_SIGNATURE and never infinite-loops."""
    assert _is_invalid_signature_error(Exception("400 INVALID_ARGUMENT. INVALID_THOUGHT_SIGNATURE"))
    assert _is_invalid_signature_error(Exception("Invalid thought signature."))
    assert not _is_invalid_signature_error(Exception("504 DEADLINE_EXCEEDED"))

    gem_sig = base64.b64encode(b"stale-gemini-sig").decode("ascii")
    hist_msg = AIMessage(
        content=[{"type": "text", "text": "Earlier answer", "extras": {"signature": gem_sig}}],
        response_metadata={"model_provider": "google_genai", "model_name": "gemini-4-hydrogen"},
    )
    input_msgs = [HumanMessage(content="Hi"), hist_msg, HumanMessage(content="Follow up")]

    # 1. Self-heals once even when max_retries=0
    recorded_batches = []
    mock_llm = MagicMock()

    def fake_invoke_succeeds_on_retry(msgs):
        recorded_batches.append(list(msgs))
        if len(recorded_batches) == 1:
            raise Exception(
                "Error calling model 'gemini-3.8-flash' (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. "
                "{'error': {'code': 400, 'message': 'Invalid thought signature.', "
                "'details': [{'reason': 'INVALID_THOUGHT_SIGNATURE'}]}}"
            )
        return AIMessage(content="Recovered answer")

    mock_llm.invoke.side_effect = fake_invoke_succeeds_on_retry
    tracer = MagicMock()
    res = _invoke_llm_with_resilience(
        llm=mock_llm,
        messages=input_msgs,
        tracer=tracer,
        thread_ids=["t_sig_heal"],
        model_name="gemini-3.8-flash",
        tier="low",
        max_retries=0,
    )
    assert res.content == "Recovered answer"
    assert len(recorded_batches) == 2
    assert recorded_batches[0][1] is hist_msg
    assert recorded_batches[1][1] is not hist_msg
    assert recorded_batches[1][1].content == "Earlier answer"
    tracer.info.assert_called_once()

    # 2. If the stripped retry still fails with INVALID_THOUGHT_SIGNATURE, propagate instead of looping
    always_fail_llm = MagicMock()
    always_fail_llm.invoke.side_effect = Exception("400 INVALID_ARGUMENT: Invalid thought signature.")
    with pytest.raises(Exception, match="Invalid thought signature"):
        _invoke_llm_with_resilience(
            llm=always_fail_llm,
            messages=input_msgs,
            tracer=MagicMock(),
            thread_ids=["t_sig_fail"],
            model_name="gemini-3.8-flash",
            tier="low",
            max_retries=3,
        )
    assert always_fail_llm.invoke.call_count == 2


def test_run_nexus_agent_with_trace_invalid_signature_diagnostic_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify run_nexus_agent_with_trace returns an actionable diagnostic when INVALID_THOUGHT_SIGNATURE bubbles out."""
    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = Exception(
        "Error calling model 'gemini-3.8-flash' (INVALID_ARGUMENT): 400 INVALID_ARGUMENT. "
        "{'error': {'message': 'Invalid thought signature.', 'details': [{'reason': 'INVALID_THOUGHT_SIGNATURE'}]}}"
    )
    monkeypatch.setattr("nexus.agent.api.nexus_graph", mock_graph)

    res = run_nexus_agent_with_trace(query="Test query", thread_id="test_sig_thread", model_tier="low")
    assert "INVALID_THOUGHT_SIGNATURE" in res["response"]
    assert "gemini-3.8-flash" in res["response"]
    assert "reasoning signature mismatch" in res["response"]
    assert res["confidence"] == 0.0


def test_get_chat_model_enables_thinking_for_gemini_and_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_chat_model configures Gemini include_thoughts and Anthropic adaptive thinking with overrides."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("AI_PROVIDER", "gemini")

    # Gemini defaults to include_thoughts=True, overridable per call or via AI_INCLUDE_THOUGHTS
    gem_default = get_chat_model(tier="strong")
    assert getattr(gem_default, "include_thoughts", None) is True

    gem_disabled = get_chat_model(tier="low", include_thoughts=False)
    assert getattr(gem_disabled, "include_thoughts", None) is False

    # Anthropic 5.5 models enable summarized adaptive thinking and 16384 max_tokens floor without temperature
    for claude_model in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
        ant_llm = get_chat_model(tier=claude_model)
        assert getattr(ant_llm, "thinking", None) == {"type": "adaptive", "display": "summarized"}
        assert getattr(ant_llm, "max_tokens", None) == 16384
        assert getattr(ant_llm, "temperature", None) is None

    # Legacy Anthropic 4.5 models keep standard non-thinking behavior
    legacy_ant = get_chat_model(tier="claude-sonnet-4-5")
    assert getattr(legacy_ant, "thinking", None) is None
    assert getattr(legacy_ant, "temperature", None) == 0.0

    # Global .env toggle AI_INCLUDE_THOUGHTS=false disables thinking on both Gemini and Anthropic 5.5
    monkeypatch.setenv("AI_INCLUDE_THOUGHTS", "false")
    assert getattr(get_chat_model(tier="strong"), "include_thoughts", None) is False
    opus_off = get_chat_model(tier="claude-opus-5-5")
    assert getattr(opus_off, "thinking", None) is None
    assert getattr(opus_off, "temperature", None) is None


def test_extract_message_thinking_and_call_model_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify extract_message_thinking extracts thoughts read-only and call_model emits llm_thinking without double-counting cost."""
    from nexus.agent.sanitization import extract_message_text, extract_message_thinking
    from nexus.core.cost import calculate_token_cost
    from nexus.core.trace import trace_bus, set_trace_thread_id, reset_trace_thread_id

    anth_msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Step 1: inspect Vault.\n\nStep 2: synthesize.", "signature": "sig_a"},
            {"type": "redacted_thinking", "data": "encrypted_blob"},
            {"type": "text", "text": "Final user answer."},
        ],
        usage_metadata={
            "input_tokens": 1000,
            "output_tokens": 350,
            "total_tokens": 1350,
            "input_token_details": {"cache_read": 500},
            "output_token_details": {"reasoning": 200},
        },
        response_metadata={"model_provider": "anthropic", "model_name": "claude-opus-5-5"},
    )
    assert extract_message_thinking(anth_msg) == "Step 1: inspect Vault.\n\nStep 2: synthesize."
    assert extract_message_text(anth_msg) == "Final user answer."
    # Original message content and signatures remain untouched
    assert anth_msg.content[0]["signature"] == "sig_a"
    assert extract_message_thinking(None) == ""
    assert extract_message_thinking(AIMessage(content="Plain text")) == ""

    # Multi-block Gemini/OpenAI reasoning extraction
    gem_msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "First thought", "signature": "g1"},
            {"type": "thinking", "thinking": "Second thought", "signature": "g2"},
            {"type": "text", "text": "Reply", "extras": {"signature": "g3"}},
        ]
    )
    assert extract_message_thinking(gem_msg) == "First thought\n\nSecond thought"
    assert extract_message_text(gem_msg) == "Reply"

    # Verify call_model emits llm_thinking before llm_response and logs reasoning_tokens without inflating cost
    emitted: list[dict] = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt), thread_id="t_think")
    tok = set_trace_thread_id("t_think")

    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_llm.bind_tools.return_value = mock_bound
    mock_bound.invoke.return_value = anth_msg
    monkeypatch.setattr("nexus.agent.graph.get_chat_model", lambda tier=None, temperature=0.0: mock_llm)

    try:
        call_model(
            {"messages": [HumanMessage(content="Explain architecture")]},
            config={"configurable": {"thread_id": "t_think", "conversation_id": "t_think", "model_tier": "claude-opus-5-5"}},
        )
    finally:
        reset_trace_thread_id(tok)
        unsub()

    types = [e["type"] for e in emitted]
    assert "llm_thinking" in types
    assert types.index("llm_thinking") < types.index("llm_response")

    think_evt = next(e for e in emitted if e["type"] == "llm_thinking")
    assert think_evt["data"]["thinking"] == "Step 1: inspect Vault.\n\nStep 2: synthesize."

    info_evt = next(e for e in emitted if e["type"] == "info" and "reasoning_tokens" in (e.get("data") or {}))
    assert info_evt["data"]["output_tokens"] == 350
    assert info_evt["data"]["reasoning_tokens"] == 200
    expected_cost = calculate_token_cost(
        input_tokens=1000,
        output_tokens=350,
        cached_tokens=500,
        model_name="claude-opus-5-5",
        tier="strong",
    )
    assert info_evt["data"]["cost_usd"] == expected_cost
    assert "200 reasoning" in info_evt["message"]


def test_invoke_llm_with_resilience_thinking_unsupported_self_heals() -> None:
    """Verify _invoke_llm_with_resilience clears thinking and retries once when an API rejects thinking."""
    mock_llm = MagicMock()
    mock_llm.thinking = {"type": "adaptive", "display": "summarized"}
    expected_response = AIMessage(content="Recovered without thinking")

    seen_thinking = []

    def fake_invoke(_msgs):
        seen_thinking.append(mock_llm.thinking)
        if len(seen_thinking) == 1:
            raise Exception("400 invalid_request_error: `thinking` is not supported for this model.")
        return expected_response

    mock_llm.invoke.side_effect = fake_invoke
    tracer = MagicMock()
    res = _invoke_llm_with_resilience(
        llm=mock_llm,
        messages=[HumanMessage(content="Hello")],
        tracer=tracer,
        thread_ids=["t_think_heal"],
        model_name="claude-haiku-5-5",
        tier="low",
    )
    assert res == expected_response
    assert mock_llm.thinking is None
    assert len(seen_thinking) == 2
    tracer.info.assert_called_once()





