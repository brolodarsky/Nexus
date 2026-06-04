"""
agent.py — Content Router Agent.
Uses an LLM to classify incoming content by domain (career, health, general)
and routes it to the appropriate domain agent.

This is the entry point for the multi-agent pipeline:
  Router → Domain Agent (e.g., Career) → Librarian (cross-domain escalation)
"""
import json
import os
import sys
import time
from typing import TypedDict, Annotated, Sequence, Literal, Optional
import operator

# ── Path Setup (allows direct execution from any working directory) ──────────
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

from core.constants import AI_MODEL
from core.trace import AgentTracer
from agents.router.prompts import ROUTER_SYSTEM_PROMPT

# ── Tracer ───────────────────────────────────────────────────────────────────
router_tracer = AgentTracer("Router", color="yellow")


# ── State Schema ─────────────────────────────────────────────────────────────

class RouterState(TypedDict):
    """State that flows through the routing graph."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    raw_content: str                     # The original content to classify
    filters: Optional[dict]              # Optional filters (domain, tag, type) passed from CLI
    domain: Optional[str]                # Classified domain: career | health | general
    summary: Optional[str]              # Short summary extracted by the router
    confidence: Optional[float]         # Router's confidence in classification
    reasoning: Optional[str]            # Router's reasoning for classification


# ── LLM Setup ────────────────────────────────────────────────────────────────

from agents.router.tools import fetch_emails

tools = [fetch_emails]
tool_node = ToolNode(tools)

llm = ChatOpenAI(model=AI_MODEL, temperature=0.0)
llm_with_tools = llm.bind_tools(tools)


# ── Graph Nodes ──────────────────────────────────────────────────────────────

def classify_content(state: RouterState) -> dict:
    """
    Calls the LLM to classify the incoming content into a domain.
    If the LLM needs email data, it will emit a tool call.
    Parses the structured JSON response and updates state if no tool calls.
    """
    raw_content = state["raw_content"]
    messages = list(state.get("messages", []))
    
    if not messages:
        router_tracer.agent_start(f"Classifying: {raw_content[:80]}")
        messages = [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=raw_content),
        ]

    # If we just executed a tool, remind the LLM to output ONLY JSON
    if len(messages) > 0 and hasattr(messages[-1], "type") and messages[-1].type == "tool":
        router_tracer.info("Tool data received, re-prompting LLM for classification JSON...")
        messages.append(SystemMessage(content="You have retrieved the necessary data. Now, you MUST return ONLY a valid JSON object containing your final routing decision (domain, summary, confidence, reasoning). No conversational text."))

    router_tracer.llm_call()
    response = llm_with_tools.invoke(messages)

    domain = None
    summary = None
    confidence = None
    reasoning = None

    if not response.tool_calls:
        response_text = response.content.strip()
        try:
            # Handle potential markdown code fences
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            classification = json.loads(response_text)
            domain = classification.get("domain", "general")
            summary = classification.get("summary", "")
            confidence = classification.get("confidence", 0.0)
            reasoning = classification.get("reasoning", "")
            router_tracer.route(domain, confidence)
            if reasoning:
                router_tracer.info(f"Reasoning: {reasoning[:120]}")
        except json.JSONDecodeError:
            # Fallback: if the LLM didn't return clean JSON, default to general
            domain = "general"
            summary = "Could not parse classification — defaulting to general."
            confidence = 0.0
            reasoning = f"JSON parse error. Raw LLM output: {response_text[:200]}"
            router_tracer.info(f"⚠️ JSON parse failed, defaulting to 'general'")
    else:
        for tc in response.tool_calls:
            router_tracer.tool_call(tc.get("name", "unknown"), tc.get("args", {}))

    return {
        "messages": [response],
        "domain": domain,
        "summary": summary,
        "confidence": confidence,
        "reasoning": reasoning,
    }


def route_after_classify(state: RouterState) -> Literal["tools", "career_agent", "run_librarian_node"]:
    """
    Conditional edge: routes to tools if tool call made, else to appropriate domain agent.
    """
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
        
    domain = state.get("domain", "general")
    if domain == "career":
        return "career_agent"
    return "run_librarian_node"
def run_librarian_node(state: RouterState) -> dict:
    """
    Fallback for domains without a dedicated agent yet, or explicit general knowledge queries.
    Passes the query and any CLI filters to the Librarian subgraph.
    """
    from agents.librarian.api import ask_librarian

    router_tracer.delegate("Librarian")

    raw_content = state.get("raw_content", "")
    filters = state.get("filters", None)
    
    # Also pass context from messages if tools were used
    context_str = ""
    for msg in state.get("messages", []):
        if hasattr(msg, "name") and msg.name == "fetch_emails" and msg.content:
            context_str += f"\n[Fetched Email Data]:\n{msg.content}\n"
            
    final_content = raw_content + "\n" + context_str if context_str else raw_content

    response_text = ask_librarian(final_content, filters=filters)

    return {"messages": [HumanMessage(content=response_text)]}


def run_career_agent_node(state: RouterState) -> dict:
    """
    Invokes the real Career Agent with DPFH and full ReAct tool loop.
    Passes the raw content and the router's summary for context.
    """
    from agents.career.api import run_career_agent

    router_tracer.delegate("CareerAgent")

    raw_content = state.get("raw_content", "")
    summary = state.get("summary", "")
    
    # Also pass context from messages if emails were fetched
    context_str = ""
    for msg in state.get("messages", []):
        if hasattr(msg, "name") and msg.name == "fetch_emails" and msg.content:
            context_str += f"\n[Fetched Email Data]:\n{msg.content}\n"
            
    final_content = raw_content + "\n" + context_str if context_str else raw_content

    response_text = run_career_agent(content=final_content, summary=summary)

    return {"messages": [HumanMessage(content=response_text)]}


# ── Graph Assembly ───────────────────────────────────────────────────────────

workflow = StateGraph(RouterState)

# Nodes
workflow.add_node("classify", classify_content)
workflow.add_node("tools", tool_node)
workflow.add_node("career_agent", run_career_agent_node)
workflow.add_node("run_librarian_node", run_librarian_node)

# Edges
workflow.add_edge(START, "classify")
workflow.add_conditional_edges("classify", route_after_classify)
workflow.add_edge("tools", "classify")
workflow.add_edge("career_agent", END)
workflow.add_edge("run_librarian_node", END)

router_graph = workflow.compile()



