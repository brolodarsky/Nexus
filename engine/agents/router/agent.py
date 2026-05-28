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
from langchain_openai import ChatOpenAI

from core.constants import AI_MODEL
from agents.router.prompts import ROUTER_SYSTEM_PROMPT


# ── State Schema ─────────────────────────────────────────────────────────────

class RouterState(TypedDict):
    """State that flows through the routing graph."""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    raw_content: str                     # The original content to classify
    domain: Optional[str]                # Classified domain: career | health | general
    summary: Optional[str]              # Short summary extracted by the router
    confidence: Optional[float]         # Router's confidence in classification
    reasoning: Optional[str]            # Router's reasoning for classification


# ── LLM Setup ────────────────────────────────────────────────────────────────

llm = ChatOpenAI(model=AI_MODEL, temperature=0.0)


# ── Graph Nodes ──────────────────────────────────────────────────────────────

def classify_content(state: RouterState) -> dict:
    """
    Calls the LLM to classify the incoming content into a domain.
    Parses the structured JSON response and updates state.
    """
    raw_content = state["raw_content"]

    messages = [
        SystemMessage(content=ROUTER_SYSTEM_PROMPT),
        HumanMessage(content=raw_content),
    ]

    response = llm.invoke(messages)
    response_text = response.content.strip()

    # Parse the JSON response from the LLM
    try:
        # Handle potential markdown code fences
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        classification = json.loads(response_text)
    except json.JSONDecodeError:
        # Fallback: if the LLM didn't return clean JSON, default to general
        classification = {
            "domain": "general",
            "summary": "Could not parse classification — defaulting to general.",
            "confidence": 0.0,
            "reasoning": f"JSON parse error. Raw LLM output: {response_text[:200]}",
        }

    return {
        "messages": [response],
        "domain": classification.get("domain", "general"),
        "summary": classification.get("summary", ""),
        "confidence": classification.get("confidence", 0.0),
        "reasoning": classification.get("reasoning", ""),
    }


def route_to_domain(state: RouterState) -> Literal["career_agent", "general_response"]:
    """
    Conditional edge: routes to the appropriate domain agent based on classification.
    Currently supports 'career' as the implemented domain agent.
    Health and general fall through to a placeholder response.
    """
    domain = state.get("domain", "general")
    if domain == "career":
        return "career_agent"
    # health and general are not yet implemented as full agents
    return "general_response"


def general_response(state: RouterState) -> dict:
    """
    Placeholder node for domains without a dedicated agent yet.
    Returns a message indicating the classification result.
    """
    domain = state.get("domain", "general")
    summary = state.get("summary", "")
    confidence = state.get("confidence", 0.0)

    msg = (
        f"📋 **Content classified as: `{domain}`** (confidence: {confidence:.0%})\n\n"
        f"**Summary:** {summary}\n\n"
        f"_No dedicated `{domain}` agent is implemented yet. "
        f"This content would be routed to the `{domain}` domain agent once built._"
    )
    return {"messages": [HumanMessage(content=msg)]}


def run_career_agent_node(state: RouterState) -> dict:
    """
    Invokes the real Career Agent with DPFH and full ReAct tool loop.
    Passes the raw content and the router's summary for context.
    """
    from agents.career.agent import run_career_agent

    raw_content = state.get("raw_content", "")
    summary = state.get("summary", "")

    response_text = run_career_agent(content=raw_content, summary=summary)

    return {"messages": [HumanMessage(content=response_text)]}


# ── Graph Assembly ───────────────────────────────────────────────────────────

workflow = StateGraph(RouterState)

# Nodes
workflow.add_node("classify", classify_content)
workflow.add_node("career_agent", run_career_agent_node)
workflow.add_node("general_response", general_response)

# Edges
workflow.add_edge(START, "classify")
workflow.add_conditional_edges("classify", route_to_domain)
workflow.add_edge("career_agent", END)
workflow.add_edge("general_response", END)

router_graph = workflow.compile()


# ── Public API ───────────────────────────────────────────────────────────────

def route_content(content: str) -> dict:
    """
    Entry point: classify and route a piece of raw content.

    Args:
        content: The raw text to classify (email body, note, job description, etc.)

    Returns:
        dict with keys: domain, summary, confidence, reasoning, response
    """
    initial_state = {
        "messages": [],
        "raw_content": content,
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
    print("  Router → Career Agent (DPFH) → Librarian (if needed)")
    print("=" * 60)

    test_job_email = """\
Hi Will,

We're hiring a Senior AI Engineer to build multi-agent systems using
LangGraph and LangChain. Requirements include:
- 3+ years Python experience
- Experience with LLM orchestration frameworks
- Familiarity with RAG pipelines and vector databases
- Strong evaluation and testing methodology
- Knowledge of prompt engineering and context optimization

Nice to have:
- Kubernetes / Docker deployment experience
- React/Next.js for internal tooling
- GraphRAG or knowledge graph experience

Please apply at careers@techstartup.com
"""

    print(f"\n📨 INPUT: Job description email (Senior AI Engineer)\n")
    print("-" * 60)

    result = route_content(test_job_email)

    print(f"\n🔀 ROUTER CLASSIFICATION:")
    print(f"   Domain:     {result['domain']}")
    print(f"   Confidence: {result['confidence']:.0%}")
    print(f"   Summary:    {result['summary']}")
    print(f"   Reasoning:  {result['reasoning']}")
    print(f"\n{'='*60}")
    print(f"🎯 CAREER AGENT RESPONSE:")
    print(f"{'='*60}\n")
    print(result["response"])
