"""
agent.py — Core ReAct agent logic for the Email Agent.
Uses LangGraph to orchestrate a tool-calling loop that queries the IMAP mailbox.
"""
import os
import sys
from typing import TypedDict, Annotated, Sequence
import operator

# Add engine root to sys.path for internal imports
ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ENGINE_ROOT not in sys.path:
    sys.path.insert(0, ENGINE_ROOT)

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI

from core.constants import AI_MODEL
from core.trace import AgentTracer, _truncate, RESULT_TRUNCATE_LEN
from agents.email.tools import fetch_email_by_uid, list_recent_emails, search_emails
from agents.email.prompts import EMAIL_SYSTEM_PROMPT

# ── Tracer ───────────────────────────────────────────────────────────────────
email_tracer = AgentTracer("EmailAgent", color="magenta")

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]

tools = [fetch_email_by_uid, list_recent_emails, search_emails]
tool_node = ToolNode(tools)

llm = ChatOpenAI(model=AI_MODEL, temperature=0.0)
llm_with_tools = llm.bind_tools(tools)

def call_model(state: AgentState):
    messages = state['messages']
    email_tracer.llm_call()
    response = llm_with_tools.invoke(messages)

    # Trace tool calls or text response
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            email_tracer.tool_call(tc.get("name", "unknown"), tc.get("args", {}))
    else:
        email_tracer.llm_response(response.content if response.content else "")

    return {"messages": [response]}


def traced_tool_node(state: AgentState):
    """Runs tools and traces their results."""
    result = tool_node.invoke(state)
    for msg in result.get("messages", []):
        tool_name = getattr(msg, "name", "unknown")
        content = msg.content if hasattr(msg, "content") else str(msg)
        email_tracer.tool_result(tool_name, _truncate(content, RESULT_TRUNCATE_LEN))
    return result

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", traced_tool_node)

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

app = workflow.compile()


