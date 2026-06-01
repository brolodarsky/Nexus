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
from agents.router.prompts import ROUTER_SYSTEM_PROMPT


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

@tool
def fetch_emails(query: str) -> str:
    """If the user asks to check their email, read a recent email, or mentions an email, use this tool to retrieve the email data."""
    from agents.email.agent import fetch_emails as _fetch
    return _fetch(query)

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
        messages = [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=raw_content),
        ]

    # If we just executed a tool, remind the LLM to output ONLY JSON
    if len(messages) > 0 and hasattr(messages[-1], "type") and messages[-1].type == "tool":
        messages.append(SystemMessage(content="You have retrieved the necessary data. Now, you MUST return ONLY a valid JSON object containing your final routing decision (domain, summary, confidence, reasoning). No conversational text."))

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
        except json.JSONDecodeError:
            # Fallback: if the LLM didn't return clean JSON, default to general
            domain = "general"
            summary = "Could not parse classification — defaulting to general."
            confidence = 0.0
            reasoning = f"JSON parse error. Raw LLM output: {response_text[:200]}"

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
    from agents.librarian.agent import ask_librarian

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
    from agents.career.agent import run_career_agent

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


# ── Public API ───────────────────────────────────────────────────────────────

def route_content(content: str, filters: dict = None) -> dict:
    """
    Entry point: classify and route a piece of raw content.

    Args:
        content: The raw text to classify (email body, note, job description, etc.)
        filters: Optional filters dict to pass along to the Librarian agent

    Returns:
        dict with keys: domain, summary, confidence, reasoning, response
    """
    initial_state = {
        "messages": [],
        "raw_content": content,
        "filters": filters,
        "domain": None,
        "summary": None,
        "confidence": None,
        "reasoning": None,
    }

    final_state = router_graph.invoke(initial_state)

    last_message = final_state["messages"][-1] if final_state["messages"] else None

    return {
        "domain": final_state.get("domain"),
        "summary": final_state.get("summary"),
        "confidence": final_state.get("confidence"),
        "reasoning": final_state.get("reasoning"),
        "response": last_message.content if last_message else "",
    }


# ── CLI End-to-End Test ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  NEXUS 3-AGENT PIPELINE: END-TO-END TEST")
    print("  Router (Email Subgraph) -> Career Agent (DPFH) -> Librarian (if needed)")
    print("=" * 60)

    test_query = "check my email for any recent job messages or recruiter outreach"

    print(f"\n📨 INPUT: {test_query}\n")
    print("-" * 60)

    result = route_content(test_query)

    print(f"\n🔀 ROUTER CLASSIFICATION:")
    print(f"   Domain:     {result['domain']}")
    print(f"   Confidence: {result['confidence']}")
    print(f"   Summary:    {result['summary']}")
    print(f"   Reasoning:  {result['reasoning']}")
    print(f"\n{'='*60}")
    print(f"🎯 CAREER AGENT RESPONSE:")
    print(f"{'='*60}\n")
    print(result["response"])
