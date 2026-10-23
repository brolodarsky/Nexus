"""
api.py — Public entry points for the Universal NexusAgent.
Provides synchronous and trace-enriched execution helpers used by FastAPI (`/api/agents/ask`),
CLI (`src/nexus/main.py`), Telegram (`src/nexus/interfaces/telegram.py`), Voice (`voice.py`),
and the Evaluation Suite (`src/nexus/evals/runner.py`).
"""
import time
from typing import Any, Optional

from langchain_core.messages import HumanMessage

from nexus.agent.graph import extract_message_text, nexus_graph, nexus_tracer


# Optional[dict] and Optional[str] allow callers to omit metadata filters or explicit thread IDs.
def run_nexus_agent_with_trace(
    query: str,
    filters: Optional[dict] = None,
    thread_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Execute a user query against the universal `NexusAgent` and return the final response + tool trace metadata.

    Args:
        query: The user's natural-language prompt or task instruction.
        filters: Optional CLI metadata filters (`domain`, `tag`, `type`) to prepend as search context hints.
        thread_id: Optional conversation UUID for persistent `SqliteSaver` checkpointer state.

    Returns:
        Dictionary with keys: `response`, `agent`, `domain`, `confidence`, `reasoning`, `tool_calls`, `final_state`.
    """
    active_thread = thread_id or "nexus_primary"
    nexus_tracer.agent_start(f"Query: {query[:80]}")

    # If CLI filters were supplied (e.g. `--domain career --tag medical`), prepend them as a concise hint.
    user_prompt = query
    if filters:
        filter_str = ", ".join(f"{k}={v}" for k, v in filters.items() if v)
        if filter_str:
            user_prompt = f"[Context Filter Hint: {filter_str}]\n\n{query}"

    config = {"configurable": {"thread_id": active_thread}}
    t0 = time.time()

    try:
        final_state = nexus_graph.invoke(
            {"messages": [HumanMessage(content=user_prompt)]},
            config=config,
        )
        elapsed = time.time() - t0

        # Collect tool call metadata emitted during this invocation
        tool_calls: list[dict[str, Any]] = []
        for msg in final_state.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "name": tc.get("name", ""),
                        "args": {
                            k: (v[:200] if isinstance(v, str) and len(v) > 200 else v)
                            for k, v in (tc.get("args") or {}).items()
                        },
                    })

        last_message = final_state["messages"][-1] if final_state.get("messages") else None
        response_text = extract_message_text(last_message)

        nexus_tracer.agent_end()
        nexus_tracer.info(f"Completed in {elapsed:.1f}s")

        return {
            "response": response_text,
            "agent": "nexus",
            "domain": (filters or {}).get("domain"),
            "confidence": 1.0,
            "reasoning": "Single Universal Agent (NexusAgent) hydrated with Master Instructions.",
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
            "tool_calls": [],
            "final_state": {"messages": []},
        }


def run_nexus_agent(
    query: str,
    filters: Optional[dict] = None,
    thread_id: Optional[str] = None,
) -> str:
    """Execute a query against `NexusAgent` and return the markdown response string."""
    result = run_nexus_agent_with_trace(query=query, filters=filters, thread_id=thread_id)
    return result["response"]


# Alias for clean semantic imports across interfaces
ask_nexus = run_nexus_agent


def route_content(
    content: str,
    filters: Optional[dict] = None,
    thread_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Universal entrypoint returning a structured dict (`response`, `agent`, `domain`, `confidence`, `reasoning`).
    Replaces the legacy 3-agent router pipeline with direct execution on `NexusAgent`.
    """
    return run_nexus_agent_with_trace(query=content, filters=filters, thread_id=thread_id)


def execute_vault_query(query: str, thread_id: Optional[str] = None) -> dict[str, Any]:
    """
    Executes a query against `NexusAgent` and returns the raw LangGraph `final_state` dict (`{"messages": [...]}`).
    Used by `src/nexus/evals/runner.py` to inspect message history, tool calls, and token usage.
    """
    active_thread = thread_id or f"eval_{int(time.time() * 1000)}"
    config = {"configurable": {"thread_id": active_thread}}
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
