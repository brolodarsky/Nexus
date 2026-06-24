"""
agent.py — Core ReAct agent logic for the Vault Reader.
Uses LangGraph to orchestrate a tool-calling loop that navigates the local Vault filesystem.
"""
import os
import sys
from typing import TypedDict, Annotated, Sequence
import operator
from pathlib import Path
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI

from nexus.core.constants import AI_MODEL
from nexus.core.trace import AgentTracer, _truncate, RESULT_TRUNCATE_LEN
from nexus.agents.librarian.tools import read_toc, read_note, search_vault, get_vault_structure
from nexus.agents.librarian.tools import get_vault_structure as _get_vault_structure_fn
from nexus.agents.librarian.prompts import SYSTEM_PROMPT

# ── Tracer ───────────────────────────────────────────────────────────────────
librarian_tracer = AgentTracer("Librarian", color="green")

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]

tools = [read_toc, read_note, search_vault, get_vault_structure]
tool_node = ToolNode(tools)

llm = ChatOpenAI(model=AI_MODEL, temperature=0.0)
llm_with_tools = llm.bind_tools(tools)

def call_model(state: AgentState):
    messages = state['messages']
    librarian_tracer.llm_call()
    response = llm_with_tools.invoke(messages)

    # Trace tool calls or text response
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            librarian_tracer.tool_call(tc.get("name", "unknown"), tc.get("args", {}))
    else:
        librarian_tracer.llm_response(response.content if response.content else "")

    return {"messages": [response]}


def traced_tool_node(state: AgentState):
    """Runs tools and traces their results."""
    result = tool_node.invoke(state)
    for msg in result.get("messages", []):
        tool_name = getattr(msg, "name", "unknown")
        content = msg.content if hasattr(msg, "content") else str(msg)
        librarian_tracer.tool_result(tool_name, _truncate(content, RESULT_TRUNCATE_LEN))
    return result

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", traced_tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

# Set up co-located SQLite memory for the agent's checkpointer
db_path = Path(__file__).parent / "memory.sqlite"
conn = sqlite3.connect(db_path, check_same_thread=False)
memory = SqliteSaver(conn)

app = workflow.compile(checkpointer=memory)

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

