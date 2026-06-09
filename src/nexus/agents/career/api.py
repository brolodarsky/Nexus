"""
api.py — Public entry points for the Career Agent.
"""
from langchain_core.messages import SystemMessage, HumanMessage

from nexus.agents.career.graph import career_graph, career_tracer, build_career_system_prompt

def run_career_agent(content: str, summary: str = "") -> str:
    """
    Entry point for the Career Agent.

    Args:
        content: The raw content to analyze (e.g., a job description email).
        summary: Optional short summary from the Router for context.

    Returns:
        The agent's final response string.
    """
    result = run_career_agent_with_trace(content, summary)
    return result["response"]


def run_career_agent_with_trace(content: str, summary: str = "") -> dict:
    """
    Entry point with full trace. Returns response + tool call metadata.

    Args:
        content: The raw content to analyze (e.g., a job description email).
        summary: Optional short summary from the Router for context.

    Returns:
        dict with keys: response (str), tool_calls (list of {name, args} dicts)
    """
    career_tracer.agent_start(f"DPFH hydration + query")
    system_prompt = build_career_system_prompt()
    career_tracer.info("System prompt hydrated with live Vault data")

    user_msg = content
    if summary:
        user_msg = f"[Router Summary: {summary}]\n\n{content}"

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg),
    ]

    try:
        final_state = career_graph.invoke({"messages": messages})

        tool_calls = []
        for msg in final_state["messages"]:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({
                        "name": tc.get("name", ""),
                        "args": {k: v[:200] if isinstance(v, str) and len(v) > 200 else v
                                 for k, v in tc.get("args", {}).items()},
                    })

        last_message = final_state["messages"][-1]
        career_tracer.agent_end()
        return {
            "response": last_message.content,
            "tool_calls": tool_calls,
        }
    except Exception as e:
        career_tracer.info(f"❌ Error: {e}")
        return {
            "response": f"❌ Career Agent encountered an error: {e}",
            "tool_calls": [],
        }
