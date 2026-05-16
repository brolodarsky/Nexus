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
from tools.vault_tools import read_toc, read_note, search_vault
from agents.vault_reader.prompts import SYSTEM_PROMPT

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]

tools = [read_toc, read_note, search_vault]
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
    status = "error" if error else "success"
    error_str = str(error) if error else None

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

    log_entry = {
        "timestamp": timestamp,
        "query": query,
        "status": status,
        "cited_sources": unique_sources,
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

def run_ask_brain(query: str, filters: dict = None) -> str:
    """
    Entry point for the vault reader agent. Returns a string response.
    """
    try:
        final_state = execute_vault_query(query)
        last_message = final_state["messages"][-1]
        return last_message.content
    except Exception as e:
        return f"❌ Agent encountered an error: {e}"

def execute_vault_query(query: str, thread_id: str = None):
    """
    Executes a query against the vault reader agent and returns the final state.
    This is designed to be called by programmatic interfaces like the Telegram bot.
    """
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
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

