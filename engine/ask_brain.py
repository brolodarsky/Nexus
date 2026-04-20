import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

"""
ask_brain.py — Brain 2 RAG Query Agent
========================================
This is the QUESTION ANSWERER. It picks up where ingest_vault.py left off.

ingest_vault.py built a searchable index of your vault notes in ChromaDB.
This script uses that index to answer questions.

The process for every single query is always:
  1. RETRIEVE: Convert the question to a vector, find the top-5 most similar
               chunks in ChromaDB, pull their text and source paths.
  2. GENERATE: Give those chunks + the question to GPT-4o as context.
               GPT-4o synthesizes a grounded answer citing your actual notes.

This two-step process is called RAG — Retrieval Augmented Generation.
"Augmented" because the LLM's generation is augmented with real retrieved data,
preventing hallucination and keeping answers grounded in YOUR notes.

The whole thing is wired together using LangGraph, which manages the flow of
data between steps (called "nodes") and keeps a shared "state" object that
every node can read from and write to.

Usage:
    python engine/ask_brain.py "What were my symptoms at my last doctor visit?"
"""

import os
from typing import TypedDict, Annotated  # TypedDict: like a dict with enforced key types
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

# ChatOpenAI — the LangChain wrapper around OpenAI's chat API (GPT-4o, etc.)
from langchain_openai import ChatOpenAI

# Message types — LangChain uses typed message objects instead of raw strings.
# This makes it easy to build multi-turn conversations with clear role labels.
#   HumanMessage  → a message from the user
#   AIMessage     → a response from the model
#   SystemMessage → hidden instructions that shape how the model behaves
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# StateGraph — the core LangGraph class. You define nodes (functions) and
# edges (connections between them), then compile it into a runnable "app".
# END — a special sentinel that tells LangGraph the graph is finished.
from langgraph.graph import StateGraph, END

# add_messages — a special "reducer" function for LangGraph state.
# When a node returns new messages, add_messages APPENDS them to the existing
# list instead of replacing it. This is how conversation history accumulates.
from langgraph.graph.message import add_messages


# ── Config ───────────────────────────────────────────────────────────────────

load_dotenv()

# These paths mirror what ingest_vault.py used — they must point to the same
# ChromaDB folder, or the agent can't find the indexed vault data.
CHROMA_PATH = Path(__file__).parent.parent / ".chroma_db"
COLLECTION_NAME = "brain2_vault"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AI_MODEL = "gpt-4o"

TOP_K = 5  # How many chunks to retrieve. Higher = more context, more cost, slower.
           # 5 is a good balance for a personal knowledge base of ~1400 chunks.


# ── State ────────────────────────────────────────────────────────────────────
# In LangGraph, "state" is the shared data object that flows through the graph.
# Every node receives the full current state and returns an updated version of it.
# Think of it like a baton being passed between runners in a relay race.
#
# TypedDict gives us a dict with enforced key types — better than a plain dict
# because it makes mistakes (like typos in key names) visible at development time.

class AgentState(TypedDict):
    """
    The data structure that travels through every node of the graph.

    Fields:
        messages: The full conversation history.
                  The `Annotated[list, add_messages]` type hint tells LangGraph
                  to use the add_messages reducer — meaning when a node returns
                  {"messages": [new_message]}, it gets APPENDED to the existing
                  list, not replacing it. This is how multi-turn memory works.

        context:  The raw text of the vault chunks retrieved from ChromaDB.
                  The `retrieve` node writes this; the `generate` node reads it.

        sources:  The relative vault paths of the retrieved chunks.
                  Used to print citations at the end of each answer.
    """
    messages: Annotated[list, add_messages]
    context: list[str]
    sources: list[str]


# ── ChromaDB Setup ───────────────────────────────────────────────────────────

def get_collection():
    """
    Connects to the existing ChromaDB collection on disk.

    IMPORTANT: We use get_collection() (not get_or_create_collection()) because
    the collection MUST already exist — created by ingest_vault.py. If it doesn't
    exist yet, ChromaDB will raise an error, which is the correct behavior: it
    tells you to run the ingestion step first.

    The embedding function here must be IDENTICAL to the one used in ingest_vault.py.
    If you used a different model to embed your vault than you use to embed the
    query, the vectors will be in different "spaces" and similarity scores will
    be meaningless. Always keep these in sync.
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not found. Check your .env file.")
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name="text-embedding-3-small",  # Must match ingest_vault.py
    )
    return client.get_collection(name=COLLECTION_NAME, embedding_function=embed_fn)


# ── Nodes ────────────────────────────────────────────────────────────────────
# A "node" in LangGraph is just a regular Python function with a specific signature:
#   - Input:  the current AgentState
#   - Output: a dict with the keys you want to UPDATE in the state
#
# LangGraph merges your returned dict into the existing state automatically.
# You don't have to return ALL keys — just the ones you changed.


def retrieve(state: AgentState) -> AgentState:
    """
    NODE 1: Semantic Retrieval — "What does my brain know about this?"

    How it works:
    1. Pull the user's question from the last message in state.
    2. Convert that question to an embedding vector (via ChromaDB's embed_fn).
    3. Mathematically compare that vector against all 1,391 stored vault vectors.
    4. Return the TOP_K most similar chunks (by cosine similarity score).
    5. Save those chunks and their source paths into the state for the next node.

    This is the "R" in RAG. Without this step, the LLM would only know what it
    learned during pre-training — not anything specific to YOUR notes.
    """
    # state["messages"] is a list of HumanMessage / AIMessage objects.
    # [-1] gets the most recent one — the fresh question the user just asked.
    query = state["messages"][-1].content

    collection = get_collection()

    # collection.query() is where the actual semantic search happens.
    # ChromaDB:
    #   1. Embeds query_texts using the embed_fn (same API call as ingest)
    #   2. Computes cosine similarity between the query vector and all stored vectors
    #   3. Returns the n_results most similar items
    #
    # Results structure (note the extra nesting — results are grouped by query,
    # even if you only sent one):
    #   results["documents"][0]  → list of chunk text strings
    #   results["metadatas"][0]  → list of metadata dicts (source, section)
    results = collection.query(
        query_texts=[query],
        n_results=TOP_K,
        include=["documents", "metadatas"],
    )

    docs = results["documents"][0]    # The actual text of the top-5 matching chunks
    metas = results["metadatas"][0]   # Their metadata (source file paths, section names)

    context = docs
    sources = [m.get("source", "Unknown") for m in metas]

    # Return updated state with the retrieved chunks loaded in.
    # The spread (**state) copies all existing state keys, then we override
    # "context" and "sources" with our fresh values.
    return {**state, "context": context, "sources": sources}


def generate(state: AgentState) -> AgentState:
    """
    NODE 2: LLM Synthesis — "Given what my brain knows, answer the question."

    How it works:
    1. If no relevant context was found, return an honest "I don't know" response.
    2. Otherwise, format the retrieved chunks into a readable context block.
    3. Build a strict SystemMessage that tells GPT-4o to ONLY use the provided context.
    4. Call GPT-4o with [SystemMessage, HumanMessage] and get an AIMessage back.
    5. Append that AIMessage to the state's message history.

    The SystemMessage is the key to preventing hallucination. Without it, GPT-4o
    would answer from its training data, which may contain nothing about YOUR life.
    With it, the model is constrained to only cite what the Retrieve node found.
    """
    llm = ChatOpenAI(
        model=AI_MODEL,
        temperature=0,          # Temperature 0 = deterministic, no creativity.
                                # For a factual knowledge retrieval tool, we want
                                # precise, consistent answers, not creative ones.
        api_key=OPENAI_API_KEY,
    )

    context = state["context"]
    sources = state["sources"]
    user_query = state["messages"][-1].content

    # Fallback: if ChromaDB returned nothing useful, don't hallucinate
    if not context:
        answer = AIMessage(content=(
            "I could not find any relevant notes in the vault for that question. "
            "Try rephrasing, or run `ingest_vault.py` if you've added new notes recently."
        ))
        # Append the fallback answer to message history and return
        return {**state, "messages": state["messages"] + [answer]}

    # Format the retrieved chunks into a clean block.
    # Each chunk is labeled with its source file so the LLM can cite it.
    # \n\n---\n\n is a markdown horizontal rule — visually separates chunks.
    context_block = "\n\n---\n\n".join(
        f"[Source: {src}]\n{doc}"
        for src, doc in zip(sources, context)
    )

    # The SystemMessage is the instruction set for the LLM.
    # It's prepended to every conversation invisibly (the user never sees it).
    # The f-string injects the actual vault content into the instructions.
    system_prompt = SystemMessage(content=(
        "You are Brain 2, a precise personal knowledge assistant. "
        "Answer the user's question using ONLY the vault notes provided below. "
        "If the answer is not in the context, say 'I don't have that in my notes.' "
        "Always cite the source note (e.g., [Source: path/to/note.md]) "
        "at the end of your answer.\n\n"
        f"VAULT CONTEXT:\n{context_block}"
    ))

    # Invoke the LLM with a two-message conversation:
    #   [0] SystemMessage — the grounding instructions + vault context
    #   [1] HumanMessage  — the user's actual question
    # The LLM returns an AIMessage with its synthesized answer.
    response = llm.invoke([system_prompt, HumanMessage(content=user_query)])

    # Append the LLM's response to the running message history in state
    return {**state, "messages": state["messages"] + [response]}


# ── Graph ────────────────────────────────────────────────────────────────────
# LangGraph builds a directed acyclic graph (DAG) where:
#   - Nodes are Python functions that transform state
#   - Edges define the execution order
#
# Our graph is deliberately simple for the prototype:
#   retrieve → generate → END
#
# In a more advanced version, you could add conditional edges:
# e.g., if retrieve returns 0 results, skip generate and return a fallback directly.


def build_graph():
    """
    Assembles and compiles the LangGraph state machine.

    StateGraph(AgentState) creates a new graph that uses AgentState as its
    shared data schema. Every node must accept and return a dict compatible
    with AgentState.

    After adding nodes and edges, compile() "locks in" the graph and returns
    a runnable object (similar to compiling code — you can't add more nodes
    after this point without rebuilding).
    """
    workflow = StateGraph(AgentState)

    # Register functions as named nodes in the graph
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)

    # set_entry_point defines where the graph starts
    workflow.set_entry_point("retrieve")

    # add_edge defines a directed connection: "after retrieve runs, run generate"
    workflow.add_edge("retrieve", "generate")

    # "generate" connects to END — the built-in terminal state.
    # When a node connects to END, the graph stops execution and returns the
    # final state to the caller.
    workflow.add_edge("generate", END)

    return workflow.compile()


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python engine/ask_brain.py \"<your question>\"")
        sys.exit(1)

    # Join all args after the script name in case the question was not quoted
    # e.g.:  python engine/ask_brain.py What is my blood type?
    # → sys.argv[1:] = ["What", "is", "my", "blood", "type?"]
    # → " ".join(...) = "What is my blood type?"
    query = " ".join(sys.argv[1:])
    print(f"\n[Brain 2] Query: {query}\n")

    app = build_graph()

    # The initial state is what we hand to the graph at the very start.
    # LangGraph will pass this dict into the first node (retrieve), which
    # will return an updated dict, and so on until we hit END.
    initial_state: AgentState = {
        "messages": [HumanMessage(content=query)],  # The user's question
        "context": [],    # Empty — retrieve will fill this in
        "sources": [],    # Empty — retrieve will fill this in
    }

    # app.invoke() runs the full graph synchronously and returns the final state.
    # This is the simplest execution mode — no streaming, no async.
    final_state = app.invoke(initial_state)

    # The last message in the history is always the most recent AIMessage
    answer = final_state["messages"][-1].content

    print("=" * 60)
    print(answer)
    print("=" * 60)

    # Print deduplicated source citations with Obsidian deep links.
    # obsidian://open?vault=<vault>&file=<relative_path> is the URI scheme that
    # opens a specific note directly in Obsidian when clicked in a terminal or
    # markdown renderer that supports clickable links.
    #
    # urllib.parse.quote() URL-encodes the path so spaces and special characters
    # (like '&' in folder names) don't break the URI.
    if final_state["sources"]:
        import urllib.parse
        # Derive the vault name from the Vault/ directory name — keeps it portable
        vault_name = urllib.parse.quote(CHROMA_PATH.parent.name)
        print("\n[Sources]")
        for src in dict.fromkeys(final_state["sources"]):  # deduplicate, preserve order
            # Convert Windows backslashes to forward slashes for the URI
            encoded = urllib.parse.quote(src.replace("\\", "/"))
            obsidian_link = f"obsidian://open?vault={vault_name}&file={encoded}"
            print(f"  - {src}")
            print(f"    {obsidian_link}")


if __name__ == "__main__":
    main()
