from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from core.constants import OPENAI_API_KEY, AI_MODEL, TOP_K
from core.state import AgentState
from tools.chroma_tool import get_collection

def retrieve(state: AgentState) -> AgentState:
    """
    NODE 1: Semantic Retrieval — "What does my brain know about this?"
    """
    query = state["messages"][-1].content
    collection = get_collection()

    results = collection.query(
        query_texts=[query],
        n_results=TOP_K,
        include=["documents", "metadatas"],
    )

    docs = results["documents"][0]
    metadatas = results["metadatas"][0]

    context = docs
    sources = [m.get("source", "Unknown") for m in metadatas]

    return {**state, "context": context, "sources": sources}


def generate(state: AgentState) -> AgentState:
    """
    NODE 2: LLM Synthesis — "Given what my brain knows, answer the question."
    """
    llm = ChatOpenAI(
        model=AI_MODEL,
        temperature=0,
        api_key=OPENAI_API_KEY,
    )

    context = state["context"]
    sources = state["sources"]
    user_query = state["messages"][-1].content

    if not context:
        answer = AIMessage(content=(
            "I could not find any relevant notes in the vault for that question. "
            "Try rephrasing, or run the ingestion worker if you've added new notes recently."
        ))
        return {**state, "messages": state["messages"] + [answer]}

    context_block = "\n\n---\n\n".join(
        f"[Source: {src}]\n{doc}"
        for src, doc in zip(sources, context)
    )

    system_prompt = SystemMessage(content=(
        "You are a precise personal knowledge assistant."
        "Answer the user's question using ONLY the vault notes provided below. "
        "If the answer is not in the context, say 'I don't have that in my notes.' "
        "Always cite the source note (e.g., [Source: path/to/note.md]) "
        "at the end of your answer.\n\n"
        f"VAULT CONTEXT:\n{context_block}"
    ))

    response = llm.invoke([system_prompt, HumanMessage(content=user_query)])

    return {**state, "messages": state["messages"] + [response]}
