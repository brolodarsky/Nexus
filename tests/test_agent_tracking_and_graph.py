"""
test_agent_tracking_and_graph.py — Unit tests for lossless agent tracking, subagent lineage, and run logging.

Tests:
  1. AgentTracer emits untruncated messages, tool args, and results with hierarchical agent_id & parent_id.
  2. Subagent serial allocation assigns sequential serial numbers and reset_subagent_counter resets properly.
  3. log_run persists structured subagent run records, token usage, and trace events without truncation.
  4. list_runs returns uncut query and response previews along with accurate subagents_count.
"""
import json
import shutil
from pathlib import Path
import pytest

from nexus.core.trace import AgentTracer, trace_bus, reset_trace_thread_id, set_trace_thread_id
from nexus.agent.runtime import (
    _next_subagent_tracer,
    get_active_turn_provider,
    reset_subagent_counter,
    set_active_turn_provider,
)
from nexus.core.run_logger import log_run, list_runs, get_run


def test_agent_tracer_lossless_emission():
    """Verify AgentTracer emits 100% untruncated trace events with agent_id, parent_id, and step numbers."""
    emitted = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt))

    try:
        tracer = AgentTracer("Subagent #1 (low)", color="magenta", agent_id="subagent-1", parent_id="nexus")
        long_prompt = "A" * 5000
        tracer.agent_start(f"Starting — {long_prompt}", metadata={"task_prompt": long_prompt})

        assert len(emitted) == 1
        evt = emitted[0]
        assert evt["agent"] == "Subagent #1 (low)"
        assert evt["agent_id"] == "subagent-1"
        assert evt["parent_id"] == "nexus"
        assert evt["step"] == 1
        assert evt["data"]["task_prompt"] == long_prompt
        assert len(evt["message"]) >= 5000  # Not truncated!

        long_arg = "B" * 3000
        tracer.tool_call("modify_file", args={"target": "old", "replacement": long_arg}, call_id="call_123")
        assert len(emitted) == 2
        call_evt = emitted[1]
        assert call_evt["data"]["tool"] == "modify_file"
        assert call_evt["data"]["args"]["replacement"] == long_arg
        assert call_evt["data"]["call_id"] == "call_123"

        long_result = "C" * 8000
        tracer.tool_result("modify_file", result=long_result, call_id="call_123")
        assert len(emitted) == 3
        res_evt = emitted[2]
        assert res_evt["data"]["result"] == long_result
    finally:
        unsub()


def test_subagent_serial_allocation_and_reset():
    """Verify sequential allocation of subagent serial numbers and lineage."""
    reset_subagent_counter()
    s1, id1, t1 = _next_subagent_tracer("low")
    s2, id2, t2 = _next_subagent_tracer("medium")

    assert s1 == 1
    assert id1 == "subagent-1"
    assert t1.agent_name == "Subagent #1 (low)"
    assert t1.parent_id == "nexus"

    assert s2 == 2
    assert id2 == "subagent-2"
    assert t2.agent_name == "Subagent #2 (medium)"
    assert t2.parent_id == "nexus"

    # Reset clears back to #1
    reset_subagent_counter()
    s3, id3, _ = _next_subagent_tracer("low")
    assert s3 == 1
    assert id3 == "subagent-1"


def test_concurrent_thread_subagent_counter_and_provider_isolation():
    """Verify that parallel conversation threads maintain completely isolated subagent counters and providers."""
    thread_a = "conv_thread_alpha"
    thread_b = "conv_thread_beta"

    # Reset both threads independently
    reset_subagent_counter(thread_a)
    reset_subagent_counter(thread_b)

    # Set distinct providers per thread
    set_active_turn_provider("anthropic", thread_id=thread_a)
    set_active_turn_provider("gemini", thread_id=thread_b)

    assert get_active_turn_provider(thread_a) == "anthropic"
    assert get_active_turn_provider(thread_b) == "gemini"

    # Subagents allocated on Thread A
    s_a1, id_a1, t_a1 = _next_subagent_tracer("low", thread_id=thread_a)
    s_a2, id_a2, t_a2 = _next_subagent_tracer("medium", thread_id=thread_a)

    assert s_a1 == 1
    assert id_a1 == "subagent-1"
    assert s_a2 == 2
    assert id_a2 == "subagent-2"

    # Subagents allocated on Thread B start at #1 and do not clash with Thread A
    s_b1, id_b1, t_b1 = _next_subagent_tracer("low", thread_id=thread_b)
    assert s_b1 == 1
    assert id_b1 == "subagent-1"

    # Resetting Thread A resets only Thread A; Thread B continues sequentially
    reset_subagent_counter(thread_a)
    s_b2, id_b2, t_b2 = _next_subagent_tracer("strong", thread_id=thread_b)
    assert s_b2 == 2
    assert id_b2 == "subagent-2"

    # Thread A starts cleanly back at #1
    s_a3, id_a3, t_a3 = _next_subagent_tracer("low", thread_id=thread_a)
    assert s_a3 == 1
    assert id_a3 == "subagent-1"


def test_log_run_persists_subagents_and_token_telemetry():
    """Verify log_run structures subagent breakdowns and token counts into SQLite runs."""
    long_subagent_prompt = "Inspect all 5 career files and draft a 5000 word proposal: " + ("X" * 2000)
    mock_events = [
        {
            "step": 1,
            "type": "agent_start",
            "agent": "NexusAgent",
            "agent_id": "nexus",
            "parent_id": None,
            "color": "cyan",
            "message": "Starting query",
            "timestamp": "2026-10-26T22:00:00Z",
            "data": {},
        },
        {
            "step": 2,
            "type": "agent_start",
            "agent": "Subagent #1 (low)",
            "agent_id": "subagent-1",
            "parent_id": "nexus",
            "color": "magenta",
            "message": f"Starting — {long_subagent_prompt}",
            "timestamp": "2026-10-26T22:00:01Z",
            "data": {"task_prompt": long_subagent_prompt, "model_tier": "low"},
        },
        {
            "step": 3,
            "type": "info",
            "agent": "Subagent #1 (low)",
            "agent_id": "subagent-1",
            "parent_id": "nexus",
            "color": "magenta",
            "message": "Tokens: 1,500 in (500 cached, 33%) | 200 out",
            "timestamp": "2026-10-26T22:00:02Z",
            "data": {"input_tokens": 1500, "output_tokens": 200, "cached_tokens": 500},
        },
        {
            "step": 4,
            "type": "llm_response",
            "agent": "Subagent #1 (low)",
            "agent_id": "subagent-1",
            "parent_id": "nexus",
            "color": "magenta",
            "message": "Subagent distilled report text",
            "timestamp": "2026-10-26T22:00:03Z",
            "data": {"response": "Subagent distilled report text"},
        },
        {
            "step": 5,
            "type": "agent_end",
            "agent": "Subagent #1 (low)",
            "agent_id": "subagent-1",
            "parent_id": "nexus",
            "color": "magenta",
            "message": "Done",
            "timestamp": "2026-10-26T22:00:04Z",
            "data": {},
        },
    ]

    run_id = log_run(
        agent_name="nexus",
        query="Research career files",
        response="Here is the finalized synthesis",
        thread_id="test-thread-abc",
        trace_events=mock_events,
        latency_seconds=4.5,
    )

    assert isinstance(run_id, str)
    data = get_run(run_id)
    assert data is not None

    assert data["subagents_count"] == 1
    assert len(data["subagents"]) == 1
    sub = data["subagents"][0]
    assert sub["agent_id"] == "subagent-1"
    assert sub["agent_name"] == "Subagent #1 (low)"
    assert sub["task_prompt"] == long_subagent_prompt
    assert sub["final_response"] == "Subagent distilled report text"
    assert data["metadata"]["token_usage"]["input_tokens"] == 1500
    assert data["metadata"]["token_usage"]["cached_tokens"] == 500

    # Test list_runs
    summaries = list_runs(limit=10)
    assert len(summaries) >= 1
    summary = next(s for s in summaries if s["run_id"] == run_id)
    assert summary["subagents_count"] == 1
    assert summary["input_query"] == "Research career files"


def test_trace_bus_thread_isolation():
    """Verify trace_bus strictly routes events to thread-scoped subscribers without cross-talk."""
    events_a = []
    events_b = []
    events_global = []

    unsub_a = trace_bus.subscribe(lambda evt: events_a.append(evt), thread_id="thread-alpha")
    unsub_b = trace_bus.subscribe(lambda evt: events_b.append(evt), thread_id="thread-beta")
    unsub_global = trace_bus.subscribe(lambda evt: events_global.append(evt))

    try:
        # 1. Emit an event scoped to thread-alpha
        tracer_a = AgentTracer("NexusAgent", color="cyan", agent_id="nexus", thread_id="thread-alpha")
        tracer_a.agent_start("Alpha query")

        # 2. Emit an event scoped to thread-beta
        tracer_b = AgentTracer("NexusAgent", color="cyan", agent_id="nexus", thread_id="thread-beta")
        tracer_b.agent_start("Beta query")

        # Verify thread A only saw Alpha
        assert len(events_a) == 1
        assert events_a[0]["thread_id"] == "thread-alpha"
        assert "Alpha" in events_a[0]["message"]

        # Verify thread B only saw Beta
        assert len(events_b) == 1
        assert events_b[0]["thread_id"] == "thread-beta"
        assert "Beta" in events_b[0]["message"]

        # Verify global listener saw both
        assert len(events_global) == 2
        assert {e["thread_id"] for e in events_global} == {"thread-alpha", "thread-beta"}
    finally:
        unsub_a()
        unsub_b()
        unsub_global()


def test_agent_tracer_inherits_context_and_explicit_thread_id():
    """Verify AgentTracer resolves thread_id from contextvar or explicit parameter."""
    emitted = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt))

    token = set_trace_thread_id("thread-context-123")
    try:
        # Context-inherited tracer
        tracer_context = AgentTracer("Head Agent", color="cyan", agent_id="nexus")
        tracer_context.info("Contextual message")

        # Explicitly overridden tracer
        tracer_explicit = AgentTracer("Subagent #1", color="magenta", agent_id="subagent-1", thread_id="thread-explicit-456")
        tracer_explicit.info("Explicit message")

        assert len(emitted) == 2
        assert emitted[0]["thread_id"] == "thread-context-123"
        assert emitted[1]["thread_id"] == "thread-explicit-456"
    finally:
        reset_trace_thread_id(token)
        unsub()


def test_invoke_tool_node_resilient_timeout_returns_error_tool_messages():
    """Verify _invoke_tool_node_resilient propagates LangGraph runtime context and detaches hung tools on timeout."""
    import time
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode
    from nexus.agent.runtime import _invoke_tool_node_resilient

    @tool
    def fast_tool() -> str:
        """Returns quickly."""
        return "fast_ok"

    @tool
    def hung_tool() -> str:
        """Simulates a blocked external socket."""
        time.sleep(1.5)
        return "too late"

    node = ToolNode([fast_tool, hung_tool], handle_tool_errors=True)
    wf = StateGraph(MessagesState)
    wf.add_node("tools", lambda s: _invoke_tool_node_resilient(node, s, timeout_seconds=0.15))
    wf.add_edge(START, "tools")
    wf.add_edge("tools", END)
    app_graph = wf.compile()

    # 1. Fast tool succeeds with runtime ContextVar propagated into timeout wrapper thread
    fast_ai = AIMessage(
        content="",
        tool_calls=[{"name": "fast_tool", "args": {}, "id": "call_fast_1", "type": "tool_call"}],
    )
    fast_out = app_graph.invoke({"messages": [fast_ai]})
    assert fast_out["messages"][-1].content == "fast_ok"

    # 2. Hung tool times out promptly and yields structured error ToolMessage
    hung_ai = AIMessage(
        content="",
        tool_calls=[{"name": "hung_tool", "args": {}, "id": "call_hang_1", "type": "tool_call"}],
    )
    t0 = time.time()
    out = app_graph.invoke({"messages": [hung_ai]})
    elapsed = time.time() - t0

    assert elapsed < 1.0, f"Timeout wrapper blocked waiting for hung thread ({elapsed:.2f}s)"
    last_msg = out["messages"][-1]
    assert last_msg.status == "error"
    assert last_msg.tool_call_id == "call_hang_1"
    assert "timed out" in last_msg.content.lower()


def test_spawn_subagent_emits_error_telemetry_and_returns_report_on_failure(monkeypatch: pytest.MonkeyPatch):
    """Verify spawn_subagent catches unhandled LLM/tool failures, emits tool_error + agent_end, and returns an error report."""
    from nexus.agent import subagent as subagent_mod

    emitted = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt), thread_id="conv-subagent-err")
    token = set_trace_thread_id("conv-subagent-err")
    ctx_token = subagent_mod.set_hitl_execution_context(conversation_id="conv-subagent-err", thread_id="conv-subagent-err")

    monkeypatch.setattr(
        subagent_mod,
        "_invoke_llm_with_resilience",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("Simulated API crash")),
    )

    try:
        res = subagent_mod.spawn_subagent.invoke({"task_prompt": "Test failure handling", "model_tier": "low"})
    finally:
        subagent_mod.reset_hitl_execution_context(ctx_token)
        reset_trace_thread_id(token)
        unsub()

    assert "failed" in res.lower()
    assert "Simulated API crash" in res
    event_types = [e["type"] for e in emitted]
    assert "agent_start" in event_types
    assert "tool_error" in event_types
    assert "agent_end" in event_types


def test_spawn_subagent_prehydrates_context_files_and_hitl_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify `spawn_subagent(context_files=...)` resolves disk + staged HITL files and prepends `# Pre-Hydrated Disk Context`."""
    from langchain_core.messages import AIMessage, HumanMessage
    from nexus.agent import subagent as subagent_mod
    import nexus.core.hitl_queue as hitl_mod
    import nexus.shared_tools.shared as shared_mod
    import nexus.shared_tools.vault_reader as vault_reader_mod

    fake_vault = tmp_path / "Vault"
    career_dir = fake_vault / "3. Operations" / "3.1. Career Strategy & Revenue"
    career_dir.mkdir(parents=True)
    (career_dir / "Resume - Master.md").write_text("BS in Computer Science\nPython, LangGraph", encoding="utf-8")
    (career_dir / "Section Instructions.md").write_text("# Career Section Rules\nBe accurate.", encoding="utf-8")

    monkeypatch.setattr(vault_reader_mod, "VAULT_PATH", fake_vault)
    monkeypatch.setattr(shared_mod, "VAULT_PATH", fake_vault)
    monkeypatch.setattr(hitl_mod, "DB_PATH", tmp_path / "test_hitl.db")
    hitl_mod.init_db()

    # Stage a brand-new note in HITL queue (not yet on disk) to confirm pending creates resolve too
    hitl_mod.add_transaction(
        agent_name="nexus_agent",
        action_type="create",
        target_file="Vault/3. Operations/3.1. Career Strategy & Revenue/Staged Draft.md",
        proposed_content="# Staged Draft\nReady for review.",
        original_content=None,
        reasoning="Test staged context file hydration",
    )

    captured_calls = []

    def _fake_invoke_llm(**kwargs):
        captured_calls.append(kwargs["messages"])
        return AIMessage(content="Evaluated against verified BS in CS.")

    monkeypatch.setattr(subagent_mod, "_invoke_llm_with_resilience", _fake_invoke_llm)

    ctx_token = subagent_mod.set_hitl_execution_context(conversation_id="conv-prehydrate", thread_id="conv-prehydrate")
    trace_token = set_trace_thread_id("conv-prehydrate")
    try:
        res = subagent_mod.spawn_subagent.invoke(
            {
                "task_prompt": "Evaluate JD fit strictly using the attached resume.",
                "model_tier": "low",
                "context_files": [
                    "3. Operations/3.1. Career Strategy & Revenue/Resume - Master.md",
                    "Section Instructions.md",
                    "3. Operations/3.1. Career Strategy & Revenue/Staged Draft.md",
                    "Resume - Master.md",  # duplicate title should only be hydrated once
                ],
            }
        )
    finally:
        reset_trace_thread_id(trace_token)
        subagent_mod.reset_hitl_execution_context(ctx_token)

    assert "Evaluated against verified BS in CS." in res
    assert len(captured_calls) == 1
    sent_messages = captured_calls[0]
    assert isinstance(sent_messages[1], HumanMessage)
    prompt_body = sent_messages[1].content
    assert prompt_body.startswith("# Pre-Hydrated Disk Context")
    assert "BS in Computer Science" in prompt_body
    assert "# Career Section Rules" in prompt_body
    assert "Ready for review." in prompt_body
    assert "# Assigned Subagent Task" in prompt_body
    assert "Evaluate JD fit strictly using the attached resume." in prompt_body
    # Deduplicated: Resume - Master.md appears once as a hydrated section header
    assert prompt_body.count("## `3. Operations/3.1. Career Strategy & Revenue/Resume - Master.md`") == 1


def test_spawn_subagent_context_files_fail_fast_on_hallucinated_and_unsafe_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify `spawn_subagent` fails fast without calling the LLM on missing or escaping `context_files` paths."""
    from nexus.agent import subagent as subagent_mod
    import nexus.core.hitl_queue as hitl_mod
    import nexus.shared_tools.shared as shared_mod
    import nexus.shared_tools.vault_reader as vault_reader_mod

    fake_vault = tmp_path / "Vault"
    career_dir = fake_vault / "3. Operations" / "3.1. Career Strategy & Revenue"
    career_dir.mkdir(parents=True)
    (career_dir / "Resume - Master.md").write_text("# Master Resume", encoding="utf-8")
    (career_dir / "Job Hunt War Room.md").write_text("# War Room", encoding="utf-8")

    monkeypatch.setattr(vault_reader_mod, "VAULT_PATH", fake_vault)
    monkeypatch.setattr(shared_mod, "VAULT_PATH", fake_vault)
    monkeypatch.setattr(hitl_mod, "DB_PATH", tmp_path / "test_hitl.db")
    hitl_mod.init_db()

    llm_called = False

    def _should_not_run(**_kwargs):
        nonlocal llm_called
        llm_called = True
        raise AssertionError("LLM should never be invoked when context_files fail resolution")

    monkeypatch.setattr(subagent_mod, "_invoke_llm_with_resilience", _should_not_run)

    emitted = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt), thread_id="conv-failfast")
    trace_token = set_trace_thread_id("conv-failfast")
    ctx_token = subagent_mod.set_hitl_execution_context(conversation_id="conv-failfast", thread_id="conv-failfast")
    try:
        missing_res = subagent_mod.spawn_subagent.invoke(
            {
                "task_prompt": "Compare JDs against resume.",
                "model_tier": "low",
                "context_files": [
                    "3. Operations/3.1. Career Strategy & Revenue/Resume - Applied AI & Forward Deployed Engineer.md"
                ],
            }
        )
        traversal_res = subagent_mod.spawn_subagent.invoke(
            {
                "task_prompt": "Read secret.",
                "model_tier": "low",
                "context_files": ["../.env"],
            }
        )
    finally:
        subagent_mod.reset_hitl_execution_context(ctx_token)
        reset_trace_thread_id(trace_token)
        unsub()

    assert not llm_called
    assert "Fail-Fast Context Hydration Error" in missing_res
    assert "3. Operations/3.1. Career Strategy & Revenue" in missing_res
    assert "Resume - Master.md" in missing_res
    assert "Job Hunt War Room.md" in missing_res

    assert "Fail-Fast Context Hydration Error" in traversal_res
    assert "outside the Vault" in traversal_res

    event_types = [e["type"] for e in emitted]
    assert "agent_start" in event_types
    assert "tool_error" in event_types
    assert "agent_end" in event_types


def test_subagent_turn_cap_uses_cache_preserving_synthesis_first(monkeypatch: pytest.MonkeyPatch):
    """Verify subagent_max_turns defaults to 25 and hard cap prefers cache-preserving bound synthesis before fallback."""
    from unittest.mock import MagicMock
    from langchain_core.messages import AIMessage, ToolMessage
    from nexus.agent import subagent as subagent_mod
    from nexus.core.config import EngineSettings

    default_settings = EngineSettings()
    assert default_settings.subagent_max_turns == 25
    assert default_settings.subagent_max_uncached_input_tokens == 450_000

    monkeypatch.setattr(subagent_mod.settings, "subagent_max_turns", 2)
    monkeypatch.setattr(subagent_mod.settings, "subagent_max_uncached_input_tokens", 450_000)

    mock_base_llm = MagicMock()
    mock_bound_llm = MagicMock()
    mock_base_llm.bind_tools.return_value = mock_bound_llm
    monkeypatch.setattr(subagent_mod, "get_chat_model", lambda **_kwargs: mock_base_llm)

    tool_exec_calls = []

    def _fake_tool_node(_node, state_or_input, timeout_seconds=None):
        tool_exec_calls.append(state_or_input)
        last_tc = state_or_input["messages"][-1].tool_calls[0]
        return {
            "messages": [
                ToolMessage(
                    content="Read line 1-50 of target note.",
                    name=last_tc["name"],
                    tool_call_id=last_tc["id"],
                )
            ]
        }

    monkeypatch.setattr(subagent_mod, "_invoke_tool_node_resilient", _fake_tool_node)

    llm_invocations = []

    def _fake_invoke_llm(*, llm, messages, **_kwargs):
        llm_invocations.append((llm, list(messages)))
        call_num = len(llm_invocations)
        if call_num <= 2:
            return AIMessage(
                content=f"Inspecting step {call_num}",
                tool_calls=[{"name": "read_file", "args": {"file_path": "Note.md"}, "id": f"tc_{call_num}"}],
                usage_metadata={"input_tokens": 150, "output_tokens": 25, "total_tokens": 175},
            )
        # Turn 3 receives synthetic refusal ToolMessage(status="error") on bound `mock_bound_llm` to preserve KV cache
        return AIMessage(
            content="Budget-capped synthesis: Note.md lines 1-50 inspected.",
            usage_metadata={
                "input_tokens": 220,
                "output_tokens": 30,
                "total_tokens": 250,
                "input_token_details": {"cache_read": 180},
            },
        )

    monkeypatch.setattr(subagent_mod, "_invoke_llm_with_resilience", _fake_invoke_llm)

    emitted: list[dict] = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt), thread_id="conv-turn-cap")
    ctx_token = subagent_mod.set_hitl_execution_context(conversation_id="conv-turn-cap", thread_id="conv-turn-cap")
    trace_token = set_trace_thread_id("conv-turn-cap")
    try:
        res = subagent_mod.spawn_subagent.invoke({"task_prompt": "Keep digging forever.", "model_tier": "low"})
    finally:
        reset_trace_thread_id(trace_token)
        subagent_mod.reset_hitl_execution_context(ctx_token)
        unsub()

    assert res == "Budget-capped synthesis: Note.md lines 1-50 inspected."
    # Turn 1 ran tool execution; Turn 2 hit max_turns=2 -> injected refusal ToolMessage -> Turn 3 ran on bound LLM
    assert len(tool_exec_calls) == 1
    assert [inv[0] for inv in llm_invocations] == [mock_bound_llm, mock_bound_llm, mock_bound_llm]

    synth_messages = llm_invocations[-1][1]
    assert isinstance(synth_messages[-1], ToolMessage)
    assert synth_messages[-1].status == "error"
    assert synth_messages[-1].tool_call_id == "tc_2"
    assert "turn limit (2/2) reached" in synth_messages[-1].content

    cap_evt = next(
        e for e in emitted
        if e["type"] == "info" and (e.get("data") or {}).get("event_kind") == "subagent_budget_cap"
    )
    assert cap_evt["data"]["reason"] == "turn_limit"
    assert cap_evt["data"]["cache_preserved_synthesis"] is True


def test_subagent_stubborn_tool_calls_trigger_unbound_fallback(monkeypatch: pytest.MonkeyPatch):
    """Verify spawn_subagent falls back to unbound sub_base_llm only if bound synthesis still emits tool_calls."""
    from unittest.mock import MagicMock
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from nexus.agent import subagent as subagent_mod

    monkeypatch.setattr(subagent_mod.settings, "subagent_max_turns", 1)
    monkeypatch.setattr(subagent_mod.settings, "subagent_max_uncached_input_tokens", 450_000)

    mock_base_llm = MagicMock()
    mock_bound_llm = MagicMock()
    mock_base_llm.bind_tools.return_value = mock_bound_llm
    monkeypatch.setattr(subagent_mod, "get_chat_model", lambda **_kwargs: mock_base_llm)

    invocations = []

    def _fake_invoke_llm(*, llm, messages, **_kwargs):
        invocations.append((llm, list(messages)))
        if llm is mock_bound_llm:
            return AIMessage(
                content="Still trying to call tools",
                tool_calls=[{"name": "read_file", "args": {"file_path": "Note.md"}, "id": f"tc_{len(invocations)}"}],
                usage_metadata={"input_tokens": 200, "output_tokens": 20, "total_tokens": 220},
            )
        assert llm is mock_base_llm
        return AIMessage(
            content="Fallback unbound synthesis completed.",
            usage_metadata={"input_tokens": 250, "output_tokens": 25, "total_tokens": 275},
        )

    monkeypatch.setattr(subagent_mod, "_invoke_llm_with_resilience", _fake_invoke_llm)

    emitted: list[dict] = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt), thread_id="conv-stubborn-cap")
    ctx_token = subagent_mod.set_hitl_execution_context(conversation_id="conv-stubborn-cap", thread_id="conv-stubborn-cap")
    trace_token = set_trace_thread_id("conv-stubborn-cap")
    try:
        res = subagent_mod.spawn_subagent.invoke({"task_prompt": "Stubborn loop.", "model_tier": "low"})
    finally:
        reset_trace_thread_id(trace_token)
        subagent_mod.reset_hitl_execution_context(ctx_token)
        unsub()

    assert res == "Fallback unbound synthesis completed."
    assert [inv[0] for inv in invocations] == [mock_bound_llm, mock_bound_llm, mock_base_llm]
    fallback_msgs = invocations[-1][1]
    assert all(not getattr(m, "tool_calls", None) for m in fallback_msgs)
    assert all(not isinstance(m, ToolMessage) for m in fallback_msgs)
    assert isinstance(fallback_msgs[-1], HumanMessage)
    assert "Subagent turn/token budget reached" in fallback_msgs[-1].content
    assert any(
        e["type"] == "info" and (e.get("data") or {}).get("event_kind") == "subagent_budget_cap_fallback"
        for e in emitted
    )


def test_subagent_uncached_token_budget_ignores_cached_tokens(monkeypatch: pytest.MonkeyPatch):
    """Verify cumulative uncached tokens (input - cached) govern the budget cap without penalizing KV-cache hits."""
    from unittest.mock import MagicMock
    from langchain_core.messages import AIMessage, ToolMessage
    from nexus.agent import subagent as subagent_mod

    monkeypatch.setattr(subagent_mod.settings, "subagent_max_turns", 25)
    monkeypatch.setattr(subagent_mod.settings, "subagent_max_uncached_input_tokens", 1_000)

    mock_base_llm = MagicMock()
    mock_bound_llm = MagicMock()
    mock_base_llm.bind_tools.return_value = mock_bound_llm
    monkeypatch.setattr(subagent_mod, "get_chat_model", lambda **_kwargs: mock_base_llm)

    tool_exec_count = 0

    def _fake_tool_node(_node, state_or_input, timeout_seconds=None):
        nonlocal tool_exec_count
        tool_exec_count += 1
        last_tc = state_or_input["messages"][-1].tool_calls[0]
        return {
            "messages": [
                ToolMessage(content="Big payload", name=last_tc["name"], tool_call_id=last_tc["id"])
            ]
        }

    monkeypatch.setattr(subagent_mod, "_invoke_tool_node_resilient", _fake_tool_node)

    # Turn 1: 600 uncached (cum=600 < 1000) -> continues
    # Turn 2: 900 total, 800 cached -> 100 uncached (cum_unc=700 < 1000 even though cum_total=1500!) -> continues
    # Turn 3: 1200 total, 800 cached -> 400 uncached (cum_unc=1100 >= 1000) -> triggers cache-preserving synthesis on Turn 4
    turn_usages = [
        {"input_tokens": 600, "output_tokens": 20, "total_tokens": 620, "input_token_details": {"cache_read": 0}},
        {"input_tokens": 900, "output_tokens": 20, "total_tokens": 920, "input_token_details": {"cache_read": 800}},
        {"input_tokens": 1200, "output_tokens": 20, "total_tokens": 1220, "input_token_details": {"cache_read": 800}},
        {"input_tokens": 1250, "output_tokens": 25, "total_tokens": 1275, "input_token_details": {"cache_read": 1150}},
    ]
    invoked_llms = []

    def _fake_invoke_llm(*, llm, messages, **_kwargs):
        idx = len(invoked_llms)
        invoked_llms.append(llm)
        usage = turn_usages[idx]
        if idx < 3:
            return AIMessage(
                content=f"Step {idx + 1}",
                tool_calls=[{"name": "read_file", "args": {"file_path": "Big.md"}, "id": f"tc_{idx + 1}"}],
                usage_metadata=usage,
            )
        return AIMessage(content="Uncached-token-capped synthesis completed.", usage_metadata=usage)

    monkeypatch.setattr(subagent_mod, "_invoke_llm_with_resilience", _fake_invoke_llm)

    emitted: list[dict] = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt), thread_id="conv-tok-cap")
    ctx_token = subagent_mod.set_hitl_execution_context(conversation_id="conv-tok-cap", thread_id="conv-tok-cap")
    trace_token = set_trace_thread_id("conv-tok-cap")
    try:
        res = subagent_mod.spawn_subagent.invoke({"task_prompt": "Scan large corpus.", "model_tier": "low"})
    finally:
        reset_trace_thread_id(trace_token)
        subagent_mod.reset_hitl_execution_context(ctx_token)
        unsub()

    assert res == "Uncached-token-capped synthesis completed."
    assert tool_exec_count == 2
    assert invoked_llms == [mock_bound_llm, mock_bound_llm, mock_bound_llm, mock_bound_llm]
    cap_evt = next(
        e for e in emitted
        if e["type"] == "info" and (e.get("data") or {}).get("event_kind") == "subagent_budget_cap"
    )
    assert cap_evt["data"]["reason"] == "uncached_token_budget"
    assert cap_evt["data"]["cumulative_uncached_input_tokens"] == 1100
    assert cap_evt["data"]["cumulative_input_tokens"] == 2700
    assert cap_evt["data"]["peak_context_tokens"] == 1200


def test_subagent_soft_landing_warning_preserves_prefix_and_logs_cleanly(
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify soft warning appends once to tail ToolMessage only (KV-safe) and run_logger preserves telemetry."""
    from unittest.mock import MagicMock
    from langchain_core.messages import AIMessage, ToolMessage
    from nexus.agent import subagent as subagent_mod

    monkeypatch.setattr(subagent_mod.settings, "subagent_max_turns", 5)
    monkeypatch.setattr(subagent_mod.settings, "subagent_max_uncached_input_tokens", 450_000)

    mock_base_llm = MagicMock()
    mock_bound_llm = MagicMock()
    mock_base_llm.bind_tools.return_value = mock_bound_llm
    monkeypatch.setattr(subagent_mod, "get_chat_model", lambda **_kwargs: mock_base_llm)

    def _fake_tool_node(_node, state_or_input, timeout_seconds=None):
        last_tc = state_or_input["messages"][-1].tool_calls[0]
        return {
            "messages": [
                ToolMessage(content="Tool payload", name=last_tc["name"], tool_call_id=last_tc["id"])
            ]
        }

    monkeypatch.setattr(subagent_mod, "_invoke_tool_node_resilient", _fake_tool_node)

    recorded_histories = []

    def _fake_invoke_llm(*, llm, messages, **_kwargs):
        turn = len(recorded_histories) + 1
        recorded_histories.append(list(messages))
        if turn <= 3:
            return AIMessage(
                content=f"Turn {turn}",
                tool_calls=[{"name": "read_file", "args": {"file_path": f"F{turn}.md"}, "id": f"tc_{turn}"}],
                usage_metadata={
                    "input_tokens": 500 + turn * 100,
                    "output_tokens": 20,
                    "total_tokens": 520 + turn * 100,
                    "input_token_details": {"cache_read": 400},
                },
            )
        return AIMessage(
            content="Clean soft-landed synthesis.",
            usage_metadata={
                "input_tokens": 900,
                "output_tokens": 30,
                "total_tokens": 930,
                "input_token_details": {"cache_read": 800},
            },
        )

    monkeypatch.setattr(subagent_mod, "_invoke_llm_with_resilience", _fake_invoke_llm)

    emitted: list[dict] = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt), thread_id="conv-soft-warn")
    ctx_token = subagent_mod.set_hitl_execution_context(conversation_id="conv-soft-warn", thread_id="conv-soft-warn")
    trace_token = set_trace_thread_id("conv-soft-warn")
    try:
        res = subagent_mod.spawn_subagent.invoke({"task_prompt": "Draft edits cleanly.", "model_tier": "low"})
    finally:
        reset_trace_thread_id(trace_token)
        subagent_mod.reset_hitl_execution_context(ctx_token)
        unsub()

    assert res == "Clean soft-landed synthesis."
    # Turn 3 triggers max_turns - 2 = 3 soft warning; Turn 4 sees it ONLY on the newly appended tail ToolMessage
    turn4_msgs = recorded_histories[3]
    assert "Approaching subagent budget (turn 3/5" in turn4_msgs[-1].content
    # Earlier ToolMessages (Turns 1 and 2) were never mutated
    assert "Approaching subagent budget" not in turn4_msgs[3].content
    assert "Approaching subagent budget" not in turn4_msgs[5].content

    soft_evts = [
        e for e in emitted
        if e["type"] == "info" and (e.get("data") or {}).get("event_kind") == "subagent_soft_warning"
    ]
    assert len(soft_evts) == 1
    assert soft_evts[0]["data"]["turn"] == 3

    # Regression check: run_logger.log_run() aggregates subagents[], cost_usd, and token_usage cleanly
    run_id = log_run(
        agent_name="nexus",
        query="Soft landing audit test",
        response=res,
        thread_id="conv-soft-warn",
        trace_events=emitted,
        metadata={"model_tier": "strong", "model_name": "gemini-4-argon"},
    )
    saved = get_run(run_id)
    assert saved is not None
    assert saved["subagents_count"] == 1
    assert saved["subagents"][0]["input_tokens"] == (600 + 700 + 800 + 900)
    assert saved["subagents"][0]["cached_tokens"] == (400 + 400 + 400 + 800)
    assert saved["metadata"]["token_usage"]["input_tokens"] == (600 + 700 + 800 + 900)
    assert saved["cost_usd"] > 0.0


def test_agent_tracer_and_log_run_preserve_llm_thinking() -> None:
    """Verify AgentTracer.llm_thinking emits lossless thinking events and log_run preserves them + reasoning_tokens."""
    emitted: list[dict] = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt), thread_id="conv-think-audit")
    tok = set_trace_thread_id("conv-think-audit")
    try:
        root_tracer = AgentTracer("Head Agent", color="cyan", agent_id="nexus", parent_id=None)
        sub_tracer = AgentTracer("Subagent #1 (low)", color="magenta", agent_id="subagent-1", parent_id="nexus")

        # Blank thinking strings are ignored
        root_tracer.llm_thinking("   ")
        assert len(emitted) == 0

        long_thought = "Analyze files carefully. " * 30
        root_tracer.llm_thinking(long_thought, metadata={"model_name": "gemini-4-argon", "model_tier": "strong"})
        sub_tracer.agent_start("Starting subtask", metadata={"task_prompt": "Inspect log", "model_tier": "low"})
        sub_tracer.llm_thinking("Subagent thought step 1", metadata={"turn": 1, "model_name": "gemini-3.8-flash"})
        sub_tracer.info(
            "Tokens: 500 in (0 cached, 0%) | 150 out (90 reasoning) · ~$0.0009",
            data={
                "input_tokens": 500,
                "output_tokens": 150,
                "cached_tokens": 0,
                "reasoning_tokens": 90,
                "cost_usd": 0.000938,
                "model_name": "gemini-3.8-flash",
                "model_tier": "low",
            },
        )
        sub_tracer.llm_response("Subagent findings")
        sub_tracer.agent_end("Done")
    finally:
        reset_trace_thread_id(tok)
        unsub()

    root_think_evt = next(e for e in emitted if e["type"] == "llm_thinking" and e["agent_id"] == "nexus")
    assert root_think_evt["data"]["thinking"] == long_thought
    assert root_think_evt["message"] == long_thought

    run_id = log_run(
        agent_name="nexus",
        query="Audit reasoning logs",
        response="All set.",
        thread_id="conv-think-audit",
        trace_events=emitted,
        metadata={"model_tier": "strong", "model_name": "gemini-4-argon"},
    )
    saved = get_run(run_id)
    assert saved is not None
    assert any(e["type"] == "llm_thinking" and e["data"]["thinking"] == long_thought for e in saved["trace_events"])
    assert len(saved["subagents"]) == 1
    assert any(
        s["type"] == "llm_thinking" and s["data"]["thinking"] == "Subagent thought step 1"
        for s in saved["subagents"][0]["steps"]
    )
    assert saved["metadata"]["token_usage"]["output_tokens"] == 150
    assert saved["metadata"]["token_usage"]["reasoning_tokens"] == 90

