"""
graph.py — Content Router Agent Graph.
Uses an LLM to classify incoming content by domain (career, health, general)
and routes it to the appropriate domain agent.

This is the entry point for the multi-agent pipeline:
  Router → Domain Agent (e.g., Career) → Librarian (cross-domain escalation)
"""
# json: Standard library for parsing LLM structured output and extracting classification schemas
import json
import os
import sys
import time
# Typing primitives:
# - TypedDict: Defines rigid key-value types for LangGraph state dictionaries
# - Annotated: Attaches metadata (like reducers) to type definitions
# - Sequence: Generic collection type for immutable message sequences
# - Literal: Constrains string return values to an explicit enum-like set of node names
# - Optional: Indicates a field can be of the specified type or None
from typing import TypedDict, Annotated, Sequence, Literal, Optional

# LangGraph message reducer: appends new messages to history instead of overwriting the array
from langgraph.graph.message import add_messages
# LangChain Core Message schemas:
# - BaseMessage: Root class for all message types
# - HumanMessage: Represents user prompts or passed data payloads
# - SystemMessage: Represents instructions and procedural rules injected to guide the LLM
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
# LangGraph state machine primitives:
# - StateGraph: Directed graph that orchestrates state transitions between python functions (nodes)
# - START / END: Special sentinel nodes denoting the entry point and terminal state of a graph
from langgraph.graph import StateGraph, END, START
# ToolNode: Prebuilt LangGraph node that automatically executes tool calls emitted by an LLM
from langgraph.prebuilt import ToolNode
# ChatOpenAI: LangChain interface for OpenAI chat models (e.g., GPT-4o-mini)
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

from nexus.core.constants import AI_MODEL_LOW
from nexus.core.trace import AgentTracer
from nexus.agents.router.prompts import ROUTER_SYSTEM_PROMPT

# ── Tracer ───────────────────────────────────────────────────────────────────
# Yellow console logger and SSE event emitter for the Router agent
router_tracer = AgentTracer("Router", color="yellow")


# ── State Schema ─────────────────────────────────────────────────────────────

# TypedDict defining the state container that flows across all router nodes and edges
class RouterState(TypedDict):
    """State that flows through the routing graph."""
    # Annotated[Sequence[BaseMessage], add_messages]: Automatically merges newly returned messages
    # into the existing message list instead of replacing the entire array
    messages: Annotated[Sequence[BaseMessage], add_messages]
    raw_content: str                     # The original unparsed user query or document text
    filters: Optional[dict]              # Optional metadata filters (domain, tag, type) passed from CLI
    thread_id: Optional[str]            # UI conversation/thread UUID propagated to downstream subgraphs
    domain: Optional[str]                # Classified domain: "career" | "health" | "general"
    summary: Optional[str]               # Short 1-2 sentence distillation extracted by the router
    confidence: Optional[float]          # Router confidence score between 0.0 and 1.0
    reasoning: Optional[str]             # Plain-text justification for the classification choice


# ── LLM Setup & Tool Binding ─────────────────────────────────────────────────

from nexus.agents.router.tools import fetch_emails

# Register tools available to the router (e.g., email ingestion for inbound classification)
tools = [fetch_emails]
tool_node = ToolNode(tools) # Encapsulates tool execution into a runnable graph node

# AI_MODEL_LOW (GPT-4o-mini): Fast, low-cost model sufficient for deterministic classification
# temperature=0.0: Eliminates randomness to ensure deterministic JSON classification
llm = ChatOpenAI(model=AI_MODEL_LOW, temperature=0.0)
# bind_tools: Injects tool JSON schemas into the OpenAI API payload so the model can emit tool_calls
llm_with_tools = llm.bind_tools(tools)


# ── Graph Nodes ──────────────────────────────────────────────────────────────

def classify_content(state: RouterState) -> dict:
    """
    Node: Calls the LLM to classify the incoming content into a domain.
    If the LLM requires external data (e.g., emails), it emits a tool call.
    Otherwise, it returns a structured JSON payload with domain, confidence, and reasoning.
    """
    raw_content = state["raw_content"]
    messages = list(state.get("messages", []))
    
    # Initialize message history if this is the first step in the graph
    if not messages:
        router_tracer.agent_start(f"Classifying: {raw_content[:80]}")
        messages = [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=raw_content),
        ]

    # Re-prompt guard: If a tool just executed, remind the LLM to output pure JSON
    if len(messages) > 0 and hasattr(messages[-1], "type") and messages[-1].type == "tool":
        router_tracer.info("Tool data received, re-prompting LLM for classification JSON...")
        messages.append(SystemMessage(
            content="You have retrieved the necessary data. Now, you MUST return ONLY a valid JSON object "
                    "containing your final routing decision (domain, summary, confidence, reasoning). No conversational text."
        ))

    router_tracer.llm_call()
    response = llm_with_tools.invoke(messages)

    domain = None
    summary = None
    confidence = None
    reasoning = None

    # Case A: LLM produced final text output (not requesting a tool call)
    if not response.tool_calls:
        response_text = response.content.strip()
        try:
            # Strip markdown code fences (```json ... ```) if generated by the LLM
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
            # Fallback: Default to 'general' domain if JSON parsing fails
            domain = "general"
            summary = "Could not parse classification — defaulting to general."
            confidence = 0.0
            reasoning = f"JSON parse error. Raw LLM output: {response_text[:200]}"
            router_tracer.info(f"⚠️ JSON parse failed, defaulting to 'general'")
    else:
        # Case B: LLM requested one or more tool calls (e.g., fetch_emails)
        for tc in response.tool_calls:
            router_tracer.tool_call(tc.get("name", "unknown"), tc.get("args", {}))

    # Return state update dictionary; add_messages appends 'response' to state["messages"]
    return {
        "messages": [response],
        "domain": domain,
        "summary": summary,
        "confidence": confidence,
        "reasoning": reasoning,
    }


def route_after_classify(state: RouterState) -> Literal["tools", "career_agent", "run_librarian_node"]:
    """
    Conditional Edge: Inspects the latest message and state to decide next node transition:
    - If tool_calls exist -> route to 'tools' node.
    - If classified as 'career' -> dispatch to 'career_agent'.
    - Otherwise -> fallback to 'run_librarian_node' for general vault traversal.
    """
    messages = state["messages"]
    last_message = messages[-1]
    # Check if the LLM emitted a tool call request
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
        
    domain = state.get("domain", "general")
    if domain == "career":
        return "career_agent"
    return "run_librarian_node"


def run_librarian_node(state: RouterState) -> dict:
    """
    Node: Fallback dispatcher for general knowledge queries or unhandled domains.
    Invokes the Librarian subgraph to navigate the physical vault filesystem.
    """
    from nexus.agents.librarian.api import ask_librarian

    router_tracer.delegate("Librarian")

    raw_content = state.get("raw_content", "")
    filters = state.get("filters", None)
    thread_id = state.get("thread_id") or "librarian_primary"
    
    # Extract any tool output context (e.g., fetched emails) to pass to the Librarian
    context_str = ""
    for msg in state.get("messages", []):
        if hasattr(msg, "name") and msg.name == "fetch_emails" and msg.content:
            context_str += f"\n[Fetched Email Data]:\n{msg.content}\n"
            
    final_content = raw_content + "\n" + context_str if context_str else raw_content

    response_text = ask_librarian(final_content, filters=filters, thread_id=thread_id)

    return {"messages": [HumanMessage(content=response_text)]}


def run_career_agent_node(state: RouterState) -> dict:
    """
    Node: Dispatches career queries to the specialized Career Agent.
    Passes raw content along with the Router's extracted summary.
    """
    from nexus.agents.career.api import run_career_agent

    router_tracer.delegate("CareerAgent")

    raw_content = state.get("raw_content", "")
    summary = state.get("summary", "")
    thread_id = state.get("thread_id") or "career_primary"
    
    # Extract any tool output context (e.g., fetched recruiter emails)
    context_str = ""
    for msg in state.get("messages", []):
        if hasattr(msg, "name") and msg.name == "fetch_emails" and msg.content:
            context_str += f"\n[Fetched Email Data]:\n{msg.content}\n"
            
    final_content = raw_content + "\n" + context_str if context_str else raw_content

    response_text = run_career_agent(content=final_content, summary=summary, thread_id=thread_id)

    return {"messages": [HumanMessage(content=response_text)]}


# ── Graph Assembly ───────────────────────────────────────────────────────────

# Initialize StateGraph parameterized with RouterState schema
workflow = StateGraph(RouterState)

# 1. Register Graph Nodes (Python execution functions)
workflow.add_node("classify", classify_content)
workflow.add_node("tools", tool_node)
workflow.add_node("career_agent", run_career_agent_node)
workflow.add_node("run_librarian_node", run_librarian_node)

# 2. Define Execution Edges & Control Flow
workflow.add_edge(START, "classify")                              # Entry point -> classify
workflow.add_conditional_edges("classify", route_after_classify) # Classify -> (tools | career_agent | run_librarian_node)
workflow.add_edge("tools", "classify")                            # Tool execution loops back to classify for final decision
workflow.add_edge("career_agent", END)                            # Career agent finishes -> END
workflow.add_edge("run_librarian_node", END)                      # Librarian finishes -> END

# 3. Compile graph into an executable Runnable
router_graph = workflow.compile()



