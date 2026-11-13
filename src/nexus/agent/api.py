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

from langchain_core.messages import HumanMessage, ToolMessage

from nexus.agent.graph import extract_message_text, nexus_graph, nexus_tracer, reset_subagent_counter
from nexus.core.constants import PROJECT_ROOT, resolve_model_config
from nexus.core.hitl_queue import reset_hitl_execution_context, set_hitl_execution_context
from nexus.core.trace import reset_trace_thread_id, set_trace_thread_id


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
# so historical turns retain their immutable timestamp inside `SqliteSaver` and the static `SystemMessage`
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
) -> dict[str, Any]:
    """
    Execute a user query against the universal `NexusAgent` and return the final response + lossless tool trace metadata.

    Args:
        query: The user's natural-language prompt or task instruction.
        filters: Optional CLI metadata filters (`domain`, `tag`, `type`) to prepend as search context hints.
        thread_id: Optional conversation UUID for persistent `SqliteSaver` checkpointer state.
        model_tier: Optional per-turn model tier or model identifier (`"strong"`, `"medium"`, `"low"`, or explicit model name).
        images: Optional list of image file paths, upload endpoint URLs, or data URLs for multimodal analysis.

    Returns:
        Dictionary with keys: `response`, `agent`, `domain`, `confidence`, `reasoning`, `model_tier`, `model_name`, `tool_calls`, `final_state`.
    """
    active_thread = thread_id or "nexus_primary"
    resolved_model = resolve_model_config(model_tier)
    effective_tier = resolved_model["tier"]
    active_model_name = resolved_model["model_name"]

    # Scope trace context variable so all telemetry events emitted on this thread carry its active UUID
    trace_token = set_trace_thread_id(active_thread)

    # Reset subagent serial counter strictly scoped to active_thread so concurrent turns in other conversations are untouched
    reset_subagent_counter(active_thread)
    # Format start banner with optional image attachment count for live Thinking Panel observability
    start_label = f"Query ({effective_tier} · {active_model_name})"
    if images:
        start_label += f" [+{len(images)} image{'s' if len(images) > 1 else ''}]"
    start_label += f": {query}"

    # Emit 100% untruncated query context + active per-turn model tier and model name for the Thinking Panel & DAG
    nexus_tracer.agent_start(
        start_label,
        metadata={
            "query": query,
            "thread_id": active_thread,
            "model_tier": effective_tier,
            "model_name": active_model_name,
            "has_images": bool(images),
            "image_count": len(images) if images else 0,
        },
    )

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
            {"messages": [human_msg]},
            config=config,
        )
        elapsed = time.time() - t0

        # Build a lookup map of tool_call_id -> full ToolMessage output from the current turn
        all_msgs = final_state.get("messages", [])
        # Identify the index of the latest HumanMessage so `tool_calls` only reports calls from this turn
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

        nexus_tracer.agent_end(f"Completed in {elapsed:.1f}s")
        nexus_tracer.info(f"Completed in {elapsed:.1f}s", data={"latency_seconds": round(elapsed, 3)})

        return {
            "response": response_text,
            "agent": "nexus",
            "domain": (filters or {}).get("domain"),
            "confidence": 1.0,
            "reasoning": f"Single Universal Agent (Head Agent · {active_model_name} [{effective_tier}]) hydrated with Master Instructions.",
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
        else:
            user_msg = f"❌ NexusAgent encountered an error: {e}"

        return {
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
        return nexus_graph.invoke(
            {"messages": [HumanMessage(content=prepend_current_time_to_prompt(query))]},
            config=config,
        )
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
