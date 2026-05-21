"""
agent.py — Core ReAct agent logic for the Vault Reader.
Uses LangGraph to orchestrate a tool-calling loop that navigates the local Vault filesystem.
"""
import os
import sys
from typing import TypedDict, Annotated, Sequence
import operator
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI

from core.constants import AI_MODEL
from tools.vault_tools import read_toc, read_note, search_vault, get_vault_structure
from tools.vault_tools import get_vault_structure as _get_vault_structure_fn
from agents.librarian.prompts import SYSTEM_PROMPT

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]

tools = [read_toc, read_note, search_vault, get_vault_structure]
tool_node = ToolNode(tools)

llm = ChatOpenAI(model=AI_MODEL, temperature=0.0)
llm_with_tools = llm.bind_tools(tools)

def call_model(state: AgentState):
    messages = state['messages']
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

app = workflow.compile()

def log_query_run(query: str, final_state=None, error=None):
    """
    Logs the query execution details to engine/logs/run_logs.jsonl.
    """
    import re
    import json
    from datetime import datetime

    timestamp = datetime.utcnow().isoformat() + "Z"
    error_str = str(error) if error else None

    # Determine status: error > not_found > success
    if error:
        status = "error"
    elif final_state and "messages" in final_state:
        last_content = final_state["messages"][-1].content if final_state["messages"] else ""
        status = "not_found" if "[Not Found]" in last_content else "success"
    else:
        status = "error"

    cited_sources = []
    tool_calls = []

    if final_state and "messages" in final_state:
        messages = final_state["messages"]
        for msg in messages:
            # Check for tool calls
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    t_call = {
                        "tool": tc.get("name"),
                        "args": tc.get("args")
                    }
                    tool_calls.append(t_call)

                    # Extract sources from read_note tool calls
                    if tc.get("name") == "read_note":
                        note_path = tc.get("args", {}).get("note_path")
                        if note_path:
                            cited_sources.append(note_path)
                    elif tc.get("name") == "read_toc":
                        cited_sources.append("Table of Contents.md")
                    elif tc.get("name") == "get_vault_structure":
                        vs_path = tc.get("args", {}).get("path")
                        cited_sources.append(f"[structure] {vs_path or 'root'}")

        # Extract sources from the final assistant message content (using the [Sources] section)
        if messages:
            last_msg = messages[-1]
            if last_msg and hasattr(last_msg, 'content') and last_msg.content:
                content = last_msg.content
                # Parse [Sources] section
                sources_match = re.search(r'(?:\[Sources\]|Sources:)(.*)', content, re.IGNORECASE | re.DOTALL)
                if sources_match:
                    sources_text = sources_match.group(1)
                    lines = sources_text.strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        # Skip the "(none)" marker from [Not Found] responses
                        if line.lower() == '(none)':
                            continue
                        # Remove markdown bullet points, e.g. -, *, 1.
                        line = re.sub(r'^[\-\*\+\d\.\s]+', '', line).strip()
                        # Extract wiki-link content if present
                        wiki_match = re.search(r'\[\[(.*?)\]\]', line)
                        if wiki_match:
                            cited_sources.append(wiki_match.group(1))
                        else:
                            # Also check for regular markdown links [label](path)
                            link_match = re.search(r'\[.*?\]\((.*?)\)', line)
                            if link_match:
                                cited_sources.append(link_match.group(1))
                            else:
                                if line:
                                    cited_sources.append(line)

    # Deduplicate and clean sources
    unique_sources = []
    seen = set()
    for src in cited_sources:
        src_clean = src.strip().strip('`"\'').replace('\\', '/')
        if src_clean and src_clean not in seen:
            seen.add(src_clean)
            unique_sources.append(src_clean)

    # Extract token usage from AI messages
    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if final_state and "messages" in final_state:
        for msg in final_state["messages"]:
            usage = getattr(msg, 'usage_metadata', None)
            if usage:
                token_usage["prompt_tokens"] += usage.get("input_tokens", 0)
                token_usage["completion_tokens"] += usage.get("output_tokens", 0)
                token_usage["total_tokens"] += usage.get("total_tokens", 0)

    log_entry = {
        "timestamp": timestamp,
        "query": query,
        "status": status,
        "cited_sources": unique_sources,
        "token_usage": token_usage,
        "errors": error_str,
        "tool_calls": tool_calls
    }

    # Ensure logs directory exists in engine/
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "run_logs.jsonl"

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        sys.stderr.write(f"Failed to write query log: {e}\n")

def ask_librarian(query: str, filters: dict = None) -> str:
    """
    Entry point for the vault reader agent. Returns a string response.
    """
    try:
        final_state = execute_vault_query(query)
        last_message = final_state["messages"][-1]
        return last_message.content
    except Exception as e:
        return f"❌ Agent encountered an error: {e}"

def _build_system_prompt() -> str:
    """
    Builds the system prompt with the live vault folder structure injected.
    This is called at query time so the agent always sees the current structure
    without wasting an LLM round-trip on a get_vault_structure() tool call.
    """
    try:
        vault_tree = _get_vault_structure_fn.invoke({})
    except Exception:
        vault_tree = "(vault structure unavailable)"
    return SYSTEM_PROMPT.format(vault_structure=vault_tree)

def execute_vault_query(query: str, thread_id: str = None):
    """
    Executes a query against the vault reader agent and returns the final state.
    This is designed to be called by programmatic interfaces like the Telegram bot.
    """
    system_prompt = _build_system_prompt()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query)
    ]
    
    config = {}
    if thread_id:
        config = {"configurable": {"thread_id": thread_id}}
        
    try:
        final_state = app.invoke({"messages": messages}, config=config)
        log_query_run(query, final_state=final_state)
        return final_state
    except Exception as e:
        log_query_run(query, error=e)
        raise e

