"""
api.py — Public entry points for the Universal NexusAgent.
Provides synchronous and trace-enriched execution helpers used by FastAPI (`/api/agents/ask`),
the Next.js + FastAPI Control Panel, direct invocation (`python -m nexus.agent.api`),
and the Evaluation Suite (`src/nexus/evals/runner.py`).
"""
import base64
from datetime import datetime
import mimetypes
import time
from pathlib import Path
from typing import Any, Optional
import uuid

from langchain_core.messages import HumanMessage, ToolMessage

from nexus.agent.graph import (
    TOOLS,
    extract_message_text,
    is_thread_cancelled,
    nexus_graph,
    nexus_tracer,
    reset_subagent_counter,
)
from nexus.core.chats_db import (
    append_thread_lc_messages,
    load_thread_lc_messages,
    start_run_record,
)
from nexus.core.constants import PROJECT_ROOT, resolve_model_config
from nexus.core.context_telemetry import build_head_agent_start_manifest
from nexus.core.engine_constitution import inject_root_instructions
from nexus.core.hitl_queue import reset_hitl_execution_context, set_hitl_execution_context
from nexus.core.run_logger import log_run
from nexus.core.trace import (
    bind_thread_run_id,
    reset_trace_run_id,
    reset_trace_thread_id,
    set_trace_run_id,
    set_trace_thread_id,
    trace_bus,
    unbind_thread_run_id,
)


# Resolves a relative upload path or URI into a base64 data URL for multimodal LLM consumption
def resolve_image_to_data_url(image_ref: str) -> str:
    """Converts a local file path, upload endpoint URL, or existing data URL into a base64 data URL.
    
    Cloud multimodal LLMs (Gemini, Claude, GPT) require direct base64 data URLs (`data:image/...;base64,...`)
    or public HTTPS URLs rather than private local disk paths or localhost server links.
    """
    if image_ref.startswith("data:"):
        return image_ref
    
    # Strip any URL query parameters or leading route prefixes (e.g. /api/agents/uploads/xyz.png -> xyz.png)
    filename = Path(image_ref.split("?")[0]).name
    uploads_dir = PROJECT_ROOT / "logs" / "uploads"
    file_path = uploads_dir / filename
    
    if not file_path.is_file():
        # Fallback check directly in PROJECT_ROOT or as an absolute path
        candidate = Path(image_ref)
        if candidate.is_file():
            file_path = candidate
        else:
            raise FileNotFoundError(f"Image attachment not found on disk: {image_ref}")
            
    mime, _ = mimetypes.guess_type(str(file_path))
    if not mime:
        mime = "image/png"
        
    data = file_path.read_bytes()
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


# Prepends a localized sent-at timestamp to each incoming HumanMessage (`[Current Time: YYYY-MM-DD HH:MM]`)
# so historical turns retain their immutable timestamp inside `thread_messages` and the static `SystemMessage`
# remains 100% cache-aligned across hour boundaries without invalidating provider KV prompt caches.
def prepend_current_time_to_prompt(prompt: str) -> str:
    """Attach the current local timestamp to an incoming user prompt idempotently."""
    stripped = prompt.lstrip()
    if stripped.startswith("[Current Time:"):
        return prompt
    current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not prompt:
        return f"[Current Time: {current_time_str}]"
    return f"[Current Time: {current_time_str}]\n\n{prompt}"


# Optional[dict], Optional[str], and Optional[list[str]] allow callers to omit metadata filters, explicit thread IDs,
# per-turn model overrides, or multimodal image attachments.
def run_nexus_agent_with_trace(
    query: str,
    filters: Optional[dict] = None,
    thread_id: Optional[str] = None,
    model_tier: Optional[str] = None,
    images: Optional[list[str]] = None,
    run_id: Optional[str] = None,
    source: str = "cli",
) -> dict[str, Any]:
    """
    Execute a user query against the universal `NexusAgent` and return the final response + lossless tool trace metadata.

    Args:
        query: The user's natural-language prompt or task instruction.
        filters: Optional CLI metadata filters (`domain`, `tag`, `type`) to prepend as search context hints.
        thread_id: Optional conversation UUID for persistent `chats.db` (`thread_messages`) history.
        model_tier: Optional per-turn model tier or model identifier (`"strong"`, `"medium"`, `"low"`, or explicit model name).
        images: Optional list of image file paths, upload endpoint URLs, or data URLs for multimodal analysis.
        run_id: Optional pre-allocated `runs.run_id` linking live emitted trace steps to SQLite.
        source: Execution origin tag (`"chat"`, `"telegram"`, `"cli"`, `"eval"`, `"daemon"`).

    Returns:
        Dictionary with keys: `run_id`, `response`, `agent`, `domain`, `confidence`, `reasoning`, `model_tier`, `model_name`, `tool_calls`, `final_state`.
    """
    active_thread = thread_id or "nexus_primary"
    active_run_id = run_id or str(uuid.uuid4())[:8]
    resolved_model = resolve_model_config(model_tier)
    effective_tier = resolved_model["tier"]
    active_model_name = resolved_model["model_name"]

    # Register run row upfront so live `trace_bus` events stream directly into `trace_events`
    start_run_record(
        run_id=active_run_id,
        thread_id=active_thread,
        agent_name="nexus",
        query=query,
        source=source,
        model_tier=effective_tier,
        model_name=active_model_name,
        image_refs=images,
    )

    # For standalone CLI invocations without an external trace_bus collector, capture events locally to finalize `runs`
    cli_captured_events: list[dict[str, Any]] = []
    cli_unsub = (
        trace_bus.subscribe(lambda evt: cli_captured_events.append(evt), thread_id=active_thread)
        if source == "cli"
        else None
    )

    # Scope trace context variables so all telemetry events emitted on this thread carry thread_id & run_id
    trace_token = set_trace_thread_id(active_thread)
    run_token = set_trace_run_id(active_run_id)
    bind_thread_run_id(active_thread, active_run_id)

    # Reset subagent serial counter strictly scoped to active_thread so concurrent turns in other conversations are untouched
    reset_subagent_counter(active_thread)

    # If CLI filters were supplied (e.g. `--domain career --tag medical`), prepend them as a concise hint.
    user_prompt = query
    if filters:
        filter_str = ", ".join(f"{k}={v}" for k, v in filters.items() if v)
        if filter_str:
            user_prompt = f"[Context Filter Hint: {filter_str}]\n\n{query}"

    # Attach current local timestamp to the new user message rather than SystemMessage to keep SystemMessage 100% cache-stable
    user_prompt = prepend_current_time_to_prompt(user_prompt)

    # Construct HumanMessage: plain text if no images, or structured multimodal content blocks if images are present
    if images:
        content_blocks: list[dict[str, Any]] = []
        effective_text = user_prompt.strip() if user_prompt else "Analyze the attached image(s)."
        content_blocks.append({"type": "text", "text": effective_text})
        for img_ref in images:
            data_url = resolve_image_to_data_url(img_ref)
            content_blocks.append({"type": "image_url", "image_url": {"url": data_url}})
        human_msg = HumanMessage(content=content_blocks)
    else:
        human_msg = HumanMessage(content=user_prompt)

    # Load prior canonical LangChain messages from `chats.db` (`thread_messages`) & assemble full boot manifest
    prior_lc_messages = load_thread_lc_messages(active_thread, image_resolver=resolve_image_to_data_url)
    start_manifest, start_summary = build_head_agent_start_manifest(
        system_prompt=inject_root_instructions(),
        tools=TOOLS,
        prior_messages=prior_lc_messages,
        user_prompt=user_prompt,
        images=images,
        run_id=active_run_id,
    )

    # Format start banner with optional image attachment count for live Thinking Panel observability
    start_label = f"Query ({effective_tier} · {active_model_name})"
    if images:
        start_label += f" [+{len(images)} image{'s' if len(images) > 1 else ''}]"
    start_label += f": {query}"

    # Emit 100% untruncated query context + content-addressed `context_manifest` for the Thinking Panel & DAG
    nexus_tracer.agent_start(
        start_label,
        metadata={
            "run_id": active_run_id,
            "query": query,
            "user_prompt": user_prompt,
            "thread_id": active_thread,
            "model_tier": effective_tier,
            "model_name": active_model_name,
            "has_images": bool(images),
            "image_count": len(images) if images else 0,
            "context_manifest": start_manifest,
            "context_summary": start_summary,
        },
    )

    # Pass `model_tier` and provenance inside LangGraph `configurable` so `call_model` and HITL tools resolve active context
    config = {
        "configurable": {
            "thread_id": active_thread,
            "conversation_id": active_thread,
            "model_tier": model_tier,
        }
    }
    ctx_token = set_hitl_execution_context(
        conversation_id=active_thread,
        thread_id=active_thread,
        agent_id="nexus",
        agent_role=f"Head Agent ({effective_tier})",
    )
    t0 = time.time()

    try:
        final_state = nexus_graph.invoke(
            {"messages": list(prior_lc_messages) + [human_msg]},
            config=config,
        )
        elapsed = time.time() - t0

        all_msgs = final_state.get("messages", [])
        # Persist only the new messages produced in this turn unless the user triggered Stop & Revert
        new_turn_msgs = list(all_msgs[len(prior_lc_messages):]) if len(all_msgs) > len(prior_lc_messages) else []
        if new_turn_msgs and not is_thread_cancelled(active_thread):
            append_thread_lc_messages(
                active_thread,
                new_turn_msgs,
                turn_id=active_run_id,
                image_refs=images,
            )

        # Build a lookup map of tool_call_id -> full ToolMessage output from the current turn
        last_human_idx = 0
        for idx in range(len(all_msgs) - 1, -1, -1):
            if isinstance(all_msgs[idx], HumanMessage):
                last_human_idx = idx
                break
        turn_msgs = all_msgs[last_human_idx:]

        tool_results_by_id: dict[str, str] = {}
        for msg in turn_msgs:
            if isinstance(msg, ToolMessage):
                tc_id = getattr(msg, "tool_call_id", None)
                if tc_id:
                    tool_results_by_id[tc_id] = extract_message_text(msg)

        # Collect 100% untruncated tool call metadata and results emitted during this invocation
        tool_calls: list[dict[str, Any]] = []
        for msg in turn_msgs:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_id = tc.get("id")
                    tool_calls.append({
                        "id": tc_id,
                        "name": tc.get("name", ""),
                        "args": dict(tc.get("args") or {}),
                        "result": tool_results_by_id.get(tc_id) if tc_id else None,
                    })

        last_message = all_msgs[-1] if all_msgs else None
        response_text = extract_message_text(last_message)
        reasoning_str = f"Single Universal Agent (Head Agent · {active_model_name} [{effective_tier}]) hydrated with Master Instructions."

        nexus_tracer.agent_end(f"Completed in {elapsed:.1f}s")
        nexus_tracer.info(f"Completed in {elapsed:.1f}s", data={"latency_seconds": round(elapsed, 3)})

        if source == "cli":
            log_run(
                agent_name="nexus",
                query=query,
                response=response_text,
                thread_id=active_thread,
                domain=(filters or {}).get("domain"),
                confidence=1.0,
                reasoning=reasoning_str,
                tool_calls=tool_calls,
                trace_events=cli_captured_events,
                latency_seconds=elapsed,
                metadata={"model_tier": effective_tier, "model_name": active_model_name, "source": "cli"},
                run_id=active_run_id,
                source="cli",
            )

        return {
            "run_id": active_run_id,
            "response": response_text,
            "agent": "nexus",
            "domain": (filters or {}).get("domain"),
            "confidence": 1.0,
            "reasoning": reasoning_str,
            "model_tier": effective_tier,
            "model_name": active_model_name,
            "tool_calls": tool_calls,
            "final_state": final_state,
        }
    except Exception as e:
        nexus_tracer.info(f"❌ Error: {e}")
        err_str = str(e)
        err_lower = err_str.lower()
        # Demystify 504 DEADLINE_EXCEEDED errors for chat users with clear remediation guidance
        if "504" in err_str or "DEADLINE_EXCEEDED" in err_str:
            user_msg = (
                f"❌ NexusAgent encountered a provider deadline timeout (504 DEADLINE_EXCEEDED).\n\n"
                f"The AI provider took longer than the configured timeout to complete reasoning over the active "
                f"conversation history. You can continue by sending your next prompt, or use `spawn_subagent` to isolate "
                f"heavy file reading so raw notes do not inflate the conversation context."
            )
        # Demystify 429 RESOURCE_EXHAUSTED / Rate Limit errors if backoff retries were exhausted
        elif any(k in err_str or k in err_lower for k in ("429", "resource_exhausted", "quota exceeded", "rate limit")):
            user_msg = (
                f"⏳ NexusAgent paused because the AI provider rate limit was reached (429 RESOURCE_EXHAUSTED).\n\n"
                f"The provider's token-per-minute (TPM) or request limit was exceeded during heavy reasoning or "
                f"parallel subagent execution. Provider sliding windows typically roll over within 20–60 seconds—"
                f"please re-send your prompt or instruct the agent to run tasks sequentially to stay within quota."
            )
        # Demystify Python ThreadPoolExecutor shutdown errors caused by mid-turn `uvicorn --reload` worker restarts
        elif "cannot schedule new futures after" in err_lower or "brokenthreadpool" in type(e).__name__.lower():
            user_msg = (
                f"⚠️ NexusAgent was interrupted mid-turn because the backend server reloaded or shut down "
                f"(typically triggered when `.py` files are edited while a chat turn is in flight).\n\n"
                f"The engine has restarted cleanly and your conversation history is intact—please re-send your prompt."
            )
        # Demystify cross-provider or stale cryptographic thought/thinking signature rejections (HTTP 400)
        elif (
            "invalid_thought_signature" in err_lower
            or "invalid thought signature" in err_lower
            or ("thinking" in err_lower and "invalid" in err_lower and "signature" in err_lower)
        ):
            user_msg = (
                f"❌ NexusAgent hit a reasoning signature mismatch (`INVALID_THOUGHT_SIGNATURE`) on `{active_model_name}`.\n\n"
                f"This happens when a thread switches between model providers or reasoning formats (for example, "
                f"Claude Opus thinking signatures replayed to Gemini Flash) and an incompatible signature persisted in the request. "
                f"You can re-send your prompt, switch back to the earlier model for this thread, or start a fresh branch."
            )
        else:
            user_msg = f"❌ NexusAgent encountered an error: {e}"

        if source == "cli":
            log_run(
                agent_name="nexus",
                query=query,
                response=user_msg,
                thread_id=active_thread,
                confidence=0.0,
                reasoning=f"Error: {e}",
                trace_events=cli_captured_events,
                latency_seconds=time.time() - t0,
                metadata={"model_tier": effective_tier, "model_name": active_model_name, "source": "cli", "error": str(e)},
                run_id=active_run_id,
                source="cli",
            )

        return {
            "run_id": active_run_id,
            "response": user_msg,
            "agent": "nexus",
            "domain": None,
            "confidence": 0.0,
            "reasoning": f"Error: {e}",
            "model_tier": effective_tier,
            "model_name": active_model_name,
            "tool_calls": [],
            "final_state": {"messages": []},
        }
    finally:
        if cli_unsub is not None:
            cli_unsub()
        unbind_thread_run_id(active_thread)
        reset_trace_run_id(run_token)
        reset_hitl_execution_context(ctx_token)
        reset_trace_thread_id(trace_token)


def run_nexus_agent(
    query: str,
    filters: Optional[dict] = None,
    thread_id: Optional[str] = None,
    model_tier: Optional[str] = None,
) -> str:
    """Execute a query against `NexusAgent` and return the markdown response string."""
    result = run_nexus_agent_with_trace(query=query, filters=filters, thread_id=thread_id, model_tier=model_tier)
    return result["response"]


# Alias for clean semantic imports across interfaces
ask_nexus = run_nexus_agent


def route_content(
    content: str,
    filters: Optional[dict] = None,
    thread_id: Optional[str] = None,
    model_tier: Optional[str] = None,
) -> dict[str, Any]:
    """
    Universal entrypoint returning a structured dict (`response`, `agent`, `domain`, `confidence`, `reasoning`).
    Replaces the legacy 3-agent router pipeline with direct execution on `NexusAgent`.
    """
    return run_nexus_agent_with_trace(query=content, filters=filters, thread_id=thread_id, model_tier=model_tier)


def execute_vault_query(
    query: str,
    thread_id: Optional[str] = None,
    model_tier: Optional[str] = None,
) -> dict[str, Any]:
    """
    Executes a query against `NexusAgent` and returns the raw LangGraph `final_state` dict (`{"messages": [...]}`).
    Used by `src/nexus/evals/runner.py` to inspect message history, tool calls, and token usage.
    """
    active_thread = thread_id or f"eval_{int(time.time() * 1000)}"
    trace_token = set_trace_thread_id(active_thread)
    config = {"configurable": {"thread_id": active_thread, "conversation_id": active_thread, "model_tier": model_tier}}
    ctx_token = set_hitl_execution_context(
        conversation_id=active_thread,
        thread_id=active_thread,
        agent_id="nexus",
        agent_role="Commander",
    )
    try:
        prior_msgs = load_thread_lc_messages(active_thread)
        human_msg = HumanMessage(content=prepend_current_time_to_prompt(query))
        final_state = nexus_graph.invoke(
            {"messages": list(prior_msgs) + [human_msg]},
            config=config,
        )
        all_msgs = final_state.get("messages", [])
        if len(all_msgs) > len(prior_msgs):
            append_thread_lc_messages(active_thread, list(all_msgs[len(prior_msgs):]), turn_id=f"eval_{active_thread}")
        return final_state
    finally:
        reset_hitl_execution_context(ctx_token)
        reset_trace_thread_id(trace_token)


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    test_query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What are my top priorities in Plan.md today?"
    print(f"\n🧠 Querying NexusAgent: {test_query}\n" + "-" * 60)
    res = run_nexus_agent_with_trace(test_query)
    print("\n" + "=" * 60)
    print(res["response"])
