from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """
    The data structure that travels through every node of the RAG graph.
    """
    messages: Annotated[list, add_messages]
    context: list[str]
    sources: list[str]
    filters: dict  # Optional ChromaDB metadata filters (e.g. {"domain": "health"})
