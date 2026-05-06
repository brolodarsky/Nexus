from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from core.constants import OPENAI_API_KEY, AI_MODEL, TOP_K, SIMILARITY_THRESHOLD, RE_RANK_TOP_K
from core.state import AgentState
from tools.chroma_tool import get_collection

def _generate_hyde(query: str, llm: ChatOpenAI) -> str:
    """Generate a hypothetical document to improve retrieval."""
    system_prompt = SystemMessage(content=(
        "You are a knowledgeable assistant. Given a user's question, write a "
        "short, factual, hypothetical document that answers the question. "
        "Do not worry about whether the facts are perfectly accurate, just provide "
        "the structure and terminology that a relevant document would have."
    ))
    response = llm.invoke([system_prompt, HumanMessage(content=query)])
    return response.content

def _rerank_docs(query: str, docs: list[str], sources: list[str], distances: list[float], llm: ChatOpenAI) -> tuple[list[str], list[str]]:
    """Re-rank documents using an LLM and return the top RE_RANK_TOP_K."""
    if not docs:
        return [], []
    
    scored_docs = []
    for i, (doc, source, dist) in enumerate(zip(docs, sources, distances)):
        prompt = f"""Rate the relevance of the following document to the query on a scale of 0 to 10.
Respond ONLY with a single integer between 0 and 10.
Query: {query}
Document: {doc[:1000]}"""
        try:
            score_response = llm.invoke([HumanMessage(content=prompt)])
            score = int(score_response.content.strip())
        except Exception:
            score = 5
            
        scored_docs.append((score, dist, doc, source))
        
    scored_docs.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    
    best_docs = [d[2] for d in scored_docs[:RE_RANK_TOP_K]]
    best_sources = [d[3] for d in scored_docs[:RE_RANK_TOP_K]]
    
    return best_docs, best_sources

def retrieve(state: AgentState) -> AgentState:
    """
    NODE 1: Semantic Retrieval — "What does my brain know about this?"
    """
    query = state["messages"][-1].content
    collection = get_collection()
    
    llm = ChatOpenAI(
        model=AI_MODEL,
        temperature=0,
        api_key=OPENAI_API_KEY,
    )
    
    hypothetical_doc = _generate_hyde(query, llm)
    search_query = f"{query}\n\n{hypothetical_doc}"

    results = collection.query(
        query_texts=[search_query],
        n_results=TOP_K,
        include=["documents", "metadatas", "distances"],
    )

    raw_docs = results["documents"][0]
    raw_metadatas = results["metadatas"][0]
    raw_distances = results["distances"][0]

    filtered_docs = []
    filtered_sources = []
    filtered_distances = []
    
    for doc, meta, dist in zip(raw_docs, raw_metadatas, raw_distances):
        print(f"DEBUG: Retrieved source {meta.get('source')} with distance {dist}")
        if dist <= SIMILARITY_THRESHOLD:
            filtered_docs.append(doc)
            filtered_sources.append(meta.get("source", "Unknown"))
            filtered_distances.append(dist)

    final_docs, final_sources = _rerank_docs(query, filtered_docs, filtered_sources, filtered_distances, llm)

    return {**state, "context": final_docs, "sources": final_sources}


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
