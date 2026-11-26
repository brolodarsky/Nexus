"""
test_unified_telemetry_and_context.py — Tests for content-addressed `trace_blobs`,
`agent_start` & `llm_call` context injection manifests, pre-hash secret scrubbing,
lossless `thread_messages` persistence, HTTP blob endpoints, and reference-counted GC.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pytest

import nexus.core.chats_db as chats_db
from nexus.api.main import app
from nexus.core.chats_db import (
    _get_conn,
    append_thread_lc_messages,
    create_conversation,
    delete_conversation,
    gc_unreferenced_telemetry,
    get_message_trace,
    get_trace_blob,
    get_trace_blobs_batch,
    load_thread_lc_messages,
    log_message,
    start_run_record,
    store_trace_blob,
)
from nexus.core.context_telemetry import build_head_agent_start_manifest, build_subagent_start_manifest
from nexus.core.secret_scrubber import approx_token_count, scrub_secrets
from nexus.core.trace import reset_trace_thread_id, set_trace_thread_id, trace_bus


def test_secret_scrubber_and_approx_token_count() -> None:
    """Verify API keys and Bearer headers are scrubbed before SHA-256 hashing and token estimates round up."""
    assert approx_token_count(0) == 0
    assert approx_token_count(1) == 1
    assert approx_token_count(4) == 1
    assert approx_token_count(5) == 2

    raw_secret = (
        "GOOGLE=AIzaSyDummyKey1234567890123456789012345 "
        "CLAUDE=sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456 "
        "Authorization: Bearer super_secret_token_987654321"
    )
    cleaned = scrub_secrets(raw_secret)
    assert "AIzaSyDummyKey" not in cleaned
    assert "sk-ant-api03" not in cleaned
    assert "super_secret_token" not in cleaned

    blob_meta = store_trace_blob(raw_secret, kind="tool_result")
    stored = get_trace_blob(blob_meta["hash"])
    assert stored is not None
    assert "AIzaSyDummyKey" not in stored["content"]
    assert "sk-ant-api03" not in stored["content"]
    assert stored["approx_tokens"] == approx_token_count(stored["char_count"])


def test_content_addressed_dedup_between_head_agent_and_subagent() -> None:
    """Verify Head Agent and Subagent share the exact same SHA-256 blob for Master Instructions."""
    root_prompt = "# Master Instructions\nAlways stay grounded in Vault reality."
    fake_tools = []

    head_manifest, head_summary = build_head_agent_start_manifest(
        system_prompt=root_prompt,
        tools=fake_tools,
        prior_messages=[],
        user_prompt="[Current Time: 2026-11-26 16:30]\n\nCheck plan",
    )
    sub_manifest, sub_summary = build_subagent_start_manifest(
        root_instructions=root_prompt,
        subagent_protocol="### SUBAGENT EXECUTION PROTOCOL\n1. Batch tool calls.",
        tools=fake_tools,
        prehydrated_block="# Pre-Hydrated Disk Context\n## Section Instructions\nFollow ADR rules.",
        task_prompt="Inspect Gameplan.md",
        context_files=["Gameplan.md"],
    )

    assert head_manifest[0]["hash"] == sub_manifest[0]["hash"]
    assert head_summary["total_chars"] > 0
    assert sub_summary["approx_tokens"] == approx_token_count(sub_summary["total_chars"])
    assert any(m["role"] == "prehydrated" for m in sub_manifest)

    with _get_conn() as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM trace_blobs WHERE hash = ?",
            (head_manifest[0]["hash"],),
        ).fetchone()[0]
        assert cnt == 1


def test_subagent_agent_start_captures_prehydrated_context_and_llm_call_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify spawn_subagent emits agent_start AFTER pre-hydration with system, prehydrated, and llm_call manifests."""
    from nexus.agent import graph as graph_mod

    vault_dir = tmp_path / "Vault"
    sec_dir = vault_dir / "6. Engineering"
    sec_dir.mkdir(parents=True)
    (sec_dir / "Section Instructions.md").write_text("Follow Engineering ADR rules.", encoding="utf-8")
    (sec_dir / "Spec.md").write_text("# Spec\nContent here.", encoding="utf-8")

    monkeypatch.setattr(graph_mod, "inject_root_instructions", lambda: "ROOT_MASTER_INSTRUCTIONS")
    monkeypatch.setattr(
        graph_mod,
        "hydrate_subagent_context_files",
        lambda *_a, **_kw: (
            "# Pre-Hydrated Disk Context\n\n## `6. Engineering/Section Instructions.md`\nFollow Engineering ADR rules.\n\n## `6. Engineering/Spec.md`\n# Spec\nContent here.",
            None,
        ),
    )

    mock_base_llm = MagicMock()
    mock_base_llm.bind_tools.return_value = MagicMock()
    monkeypatch.setattr(graph_mod, "get_chat_model", lambda **_kw: mock_base_llm)
    monkeypatch.setattr(
        graph_mod,
        "_invoke_llm_with_resilience",
        lambda **_kw: AIMessage(
            content="Subagent finished cleanly.",
            usage_metadata={
                "input_tokens": 120,
                "output_tokens": 20,
                "total_tokens": 140,
                "input_token_details": {"cache_read": 0},
            },
        ),
    )

    emitted: list[dict] = []
    unsub = trace_bus.subscribe(lambda evt: emitted.append(evt), thread_id="conv-sub-ctx")
    tok = set_trace_thread_id("conv-sub-ctx")
    ctx_tok = graph_mod.set_hitl_execution_context(conversation_id="conv-sub-ctx", thread_id="conv-sub-ctx")
    try:
        out = graph_mod.spawn_subagent.invoke(
            {"task_prompt": "Summarize Spec.md", "model_tier": "low", "context_files": ["6. Engineering/Spec.md"]}
        )
    finally:
        graph_mod.reset_hitl_execution_context(ctx_tok)
        reset_trace_thread_id(tok)
        unsub()

    assert out == "Subagent finished cleanly."
    start_evt = next(e for e in emitted if e["type"] == "agent_start")
    manifest = start_evt["data"]["context_manifest"]
    roles = [m["role"] for m in manifest]
    assert "system" in roles
    assert "protocol" in roles
    assert "tools" in roles
    assert "prehydrated" in roles
    assert "prompt" in roles

    pre_entry = next(m for m in manifest if m["role"] == "prehydrated")
    pre_blob = get_trace_blob(pre_entry["hash"])
    assert pre_blob is not None
    assert "Follow Engineering ADR rules." in pre_blob["content"]

    llm_evt = next(e for e in emitted if e["type"] == "llm_call")
    assert len(llm_evt["data"]["context_manifest"]) >= 3
    assert llm_evt["data"]["context_summary"]["approx_tokens"] > 0


def test_head_agent_run_persists_live_trace_thread_messages_and_deduplicates_message_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify run_nexus_agent_with_trace streams live steps to SQLite, preserves thinking signatures, and avoids message_traces dupes."""
    from nexus.agent import api as api_mod
    from nexus.agent import graph as graph_mod

    conv_id = create_conversation(title="Unified Telemetry Turn")
    # Simulate agents.py persisting the incoming user message BEFORE calling run_nexus_agent_with_trace
    log_message(role="user", content="Hello Nexus", conversation_id=conv_id)

    # Confirm Turn-1 load_thread_lc_messages strips trailing active user row so Turn 1 never duplicates!
    assert load_thread_lc_messages(conv_id) == []

    monkeypatch.setattr(api_mod, "inject_root_instructions", lambda: "ROOT_INSTRUCTIONS_V1")

    def _fake_invoke(state, config=None):
        # Emit an llm_call event inside the active run scope
        graph_mod.nexus_tracer.llm_call(metadata={"model_tier": "strong", "model_name": "gemini-4-argon"})
        ai_reply = AIMessage(
            content=[
                {"type": "thinking", "thinking": "Step-by-step check", "signature": "sig_abc"},
                {"type": "text", "text": "Here is your answer.", "extras": {"signature": "gsig_xyz"}},
            ]
        )
        return {"messages": list(state["messages"]) + [ai_reply]}

    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = _fake_invoke
    monkeypatch.setattr(api_mod, "nexus_graph", mock_graph)

    res = api_mod.run_nexus_agent_with_trace(
        query="Hello Nexus",
        thread_id=conv_id,
        model_tier="strong",
        source="chat",
    )
    run_id = res["run_id"]
    msg_id = log_message(
        role="assistant",
        content=res["response"],
        agent="nexus",
        conversation_id=conv_id,
        run_id=run_id,
    )
    assert msg_id is not None

    # `get_message_trace` resolves via `trace_events` (and `message_traces` was skipped!)
    trace = get_message_trace(msg_id)
    assert any(e["type"] == "agent_start" for e in trace)
    assert any(e["type"] == "llm_call" for e in trace)
    start_evt = next(e for e in trace if e["type"] == "agent_start")
    assert any(m["role"] == "system" for m in start_evt["data"]["context_manifest"])

    with _get_conn() as conn:
        mt_count = conn.execute("SELECT COUNT(*) FROM message_traces WHERE message_id = ?", (msg_id,)).fetchone()[0]
        assert mt_count == 0

    # Turn 2: canonical `thread_messages` loads both HumanMessage & signature-bearing AIMessage losslessly
    loaded = load_thread_lc_messages(conv_id)
    assert len(loaded) == 2
    assert isinstance(loaded[0], HumanMessage)
    assert isinstance(loaded[1], AIMessage)
    assert loaded[1].content[0]["signature"] == "sig_abc"


def test_trace_blob_api_and_reference_counted_gc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify HTTP blob endpoints and reference-counted GC preserving shared blobs across threads."""
    client = TestClient(app)
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(chats_db, "UPLOADS_DIR", uploads_dir)

    img_a = uploads_dir / "only_a.png"
    img_a.write_bytes(b"img-a")

    conv_a = create_conversation(title="Thread A")
    conv_b = create_conversation(title="Thread B")

    shared_sys = "SHARED_MASTER_INSTRUCTIONS"
    unique_a = "UNIQUE_PROMPT_FOR_THREAD_A"
    shared_blob = store_trace_blob(shared_sys, kind="system_prompt")
    unique_blob = store_trace_blob(unique_a, kind="user_prompt")

    start_run_record(run_id="run_a", thread_id=conv_a, query="Q_A", image_refs=["/api/agents/uploads/only_a.png"])
    start_run_record(run_id="run_b", thread_id=conv_b, query="Q_B")

    chats_db.append_trace_event_record(
        "run_a",
        {
            "type": "agent_start",
            "thread_id": conv_a,
            "data": {"context_manifest": [shared_blob, unique_blob]},
        },
    )
    chats_db.append_trace_event_record(
        "run_b",
        {
            "type": "agent_start",
            "thread_id": conv_b,
            "data": {"context_manifest": [shared_blob]},
        },
    )

    # Verify single & batch HTTP blob endpoints
    r_one = client.get(f"/api/agents/trace-blobs/{shared_blob['hash']}")
    assert r_one.status_code == 200
    assert r_one.json()["content"] == shared_sys

    r_bad = client.get("/api/agents/trace-blobs/not-a-hex-hash!")
    assert r_bad.status_code == 400

    r_batch = client.post("/api/agents/trace-blobs/batch", json={"hashes": [shared_blob["hash"], unique_blob["hash"]]})
    assert r_batch.status_code == 200
    assert r_batch.json()["blobs"][unique_blob["hash"]]["content"] == unique_a

    # Delete Thread A -> unique_blob & only_a.png must be deleted; shared_blob must survive for Thread B
    delete_conversation(conv_a)
    assert get_trace_blob(unique_blob["hash"]) is None
    assert get_trace_blob(shared_blob["hash"]) is not None
    assert not img_a.exists()

    # Delete Thread B -> shared_blob drops to 0 refs and is reclaimed
    delete_conversation(conv_b)
    assert get_trace_blob(shared_blob["hash"]) is None
    assert gc_unreferenced_telemetry(dry_run=True)["deleted_blobs"] == 0
