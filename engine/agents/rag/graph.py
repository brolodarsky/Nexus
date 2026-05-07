from langgraph.graph import StateGraph, END
from agents.rag.state import AgentState
from agents.rag.nodes import retrieve, generate

def build_rag_graph():
    """
    Assembles and compiles the RAG LangGraph state machine.
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile()
