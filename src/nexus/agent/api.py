"""
api.py — Public entry points for the Universal NexusAgent.
Provides synchronous and trace-enriched execution helpers used by FastAPI (`/api/agents/ask`),
CLI (`src/nexus/main.py`), Telegram (`src/nexus/interfaces/telegram.py`), Voice (`voice.py`),
and the Evaluation Suite (`src/nexus/evals/runner.py`).
"""
import time
from typing import Any, Optional

from langchain_core.messages import HumanMessage, ToolMessage

from nexus.agent.graph import extract_message_text, nexus_graph, nexus_tracer, reset_subagent_counter
from nexus.core.constants import resolve_model_config


# Optional[dict] and Optional[str] allow callers to omit metadata filters, explicit thread IDs, or per-turn model overrides.
def run_nexus_agent_with_trace(
    query: str,
    filters: Optional[dict] = None,
    thread_id: Optional[str] = None,
    model_tier: Optional[str] = None,
) -> dict[str, Any]:
    """
    Execute a user query against the universal `NexusAgent` and return the final response + lossless tool trace metadata.

    Args:
        query: The user's natural-language prompt or task instruction.
        filters: Optional CLI metadata filters (`domain`, `tag`, `type`) to prepend as search context hints.
        thread_id: Optional conversation UUID for persistent `SqliteSaver` checkpointer state.
        model_tier: Optional per-turn model tier or model identifier (`"strong"`, `"medium"`, `"low"`, or explicit model name).

    Returns:
        Dictionary with keys: `response`, `agent`, `domain`, `confidence`, `reasoning`, `model_tier`, `model_name`, `tool_calls`, `final_state`.
    """
    active_thread = thread_id or "nexus_primary"
    resolved_model = resolve_model_config(model_tier)
    effective_tier = resolved_model["tier"]
    active_model_name = resolved_model["model_name"]

    reset_subagent_counter()
    # Emit 100% untruncated query context + active per-turn model tier and model name for the Thinking Panel & DAG
    nexus_tracer.agent_start(
        f"Query ({effective_tier} · {active_model_name}): {query}",
        metadata={
            "query": query,
            "thread_id": active_thread,
            "model_tier": effective_tier,
            "model_name": active_model_name,
        },
    )

    # If CLI filters were supplied (e.g. `--domain career --tag medical`), prepend them as a concise hint.
    user_prompt = query
    if filters:
        filter_str = ", ".join(f"{k}={v}" for k, v in filters.items() if v)
        if filter_str:
            user_prompt = f"[Context Filter Hint: {filter_str}]\n\n{query}"

    # Pass `model_tier` inside LangGraph `configurable` so `call_model` resolves the chosen model for this turn
    config = {"configurable": {"thread_id": active_thread, "model_tier": model_tier}}
    t0 = time.time()

    try:
        final_state = nexus_graph.invoke(
            {"messages": [HumanMessage(content=user_prompt)]},
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
            "reasoning": f"Single Universal Agent (NexusAgent · {active_model_name} [{effective_tier}]) hydrated with Master Instructions.",
            "model_tier": effective_tier,
            "model_name": active_model_name,
            "tool_calls": tool_calls,
            "final_state": final_state,
        }
    except Exception as e:
        nexus_tracer.info(f"❌ Error: {e}")
        err_str = str(e)
        # Demystify 504 DEADLINE_EXCEEDED errors for chat users with clear remediation guidance
        if "504" in err_str or "DEADLINE_EXCEEDED" in err_str:
            user_msg = (
                f"❌ NexusAgent encountered a provider deadline timeout (504 DEADLINE_EXCEEDED).\n\n"
                f"The AI provider took longer than the configured timeout to complete reasoning over the active "
                f"conversation history. You can continue by sending your next prompt, or use `spawn_subagent` to isolate "
                f"heavy file reading so raw notes do not inflate the conversation context."
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
    config = {"configurable": {"thread_id": active_thread, "model_tier": model_tier}}
    return nexus_graph.invoke(
        {"messages": [HumanMessage(content=query)]},
        config=config,
    )


if __name__ == "__main__":
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    test_query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What are my top priorities in Plan.md today?"
    print(f"\n🧠 Querying NexusAgent: {test_query}\n" + "-" * 60)
    res = run_nexus_agent_with_trace(test_query)
    print("\n" + "=" * 60)
    print(res["response"])
