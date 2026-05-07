import sys
import argparse
import urllib.parse
from langchain_core.messages import HumanMessage
from agents.rag.constants import CHROMA_PATH
from agents.rag.graph import build_rag_graph

# Force UTF-8 output
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def execute_rag_query(query: str, thread_id: str = None, filters: dict = None) -> dict:
    """
    Core function to execute the RAG LangGraph agent and return the final state.

    Args:
        query:     The user's natural language question.
        thread_id: Optional thread ID for multi-turn continuity.
        filters:   Optional metadata filters (e.g. {"domain": "health", "tag": "medical"}).
    """
    app = build_rag_graph()
    
    config = {}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}
        
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "context": [],
        "sources": [],
        "filters": filters or {},
    }
    
    return app.invoke(initial_state, config=config)

def run_ask_brain(query: str, filters: dict = None):
    """
    CLI Wrapper: Executes the RAG agent and prints the output to stdout.
    """
    filter_parts = []
    if filters:
        for k, v in filters.items():
            if v:
                filter_parts.append(f"{k}={v}")

    filter_label = f" [{', '.join(filter_parts)}]" if filter_parts else ""
    print(f"\n[Brain 2] Query: {query}{filter_label}\n")
    
    final_state = execute_rag_query(query, filters=filters)
    answer = final_state["messages"][-1].content
    
    print("=" * 60)
    print(answer)
    print("=" * 60)
    
    if final_state["sources"]:
        vault_name = urllib.parse.quote(CHROMA_PATH.parent.name)
        print("\n[Sources]")
        for src in dict.fromkeys(final_state["sources"]):
            encoded = urllib.parse.quote(src.replace("\\", "/"))
            obsidian_link = f"obsidian://open?vault={vault_name}&file={encoded}"
            print(f"  - {src}")
            # print(f"    {obsidian_link}")

def main():
    parser = argparse.ArgumentParser(
        description="Brain 2 — Vault RAG Agent",
        usage='python engine/main.py "your question" [--domain DOMAIN] [--tag TAG] [--type TYPE]',
    )
    parser.add_argument("query", nargs="+", help="Your question for the brain")
    parser.add_argument("--domain", type=str, default=None,
                        help="Filter by domain (health, career, tech, personal, meta, projects, learning)")
    parser.add_argument("--tag", type=str, default=None,
                        help="Filter by tag substring (e.g. 'medical', 'ai', 'finance')")
    parser.add_argument("--type", type=str, default=None,
                        help="Filter by note type (e.g. 'journal', 'overview', 'workshop')")

    args = parser.parse_args()
    query = " ".join(args.query)

    filters = {}
    if args.domain:
        filters["domain"] = args.domain
    if args.tag:
        filters["tag"] = args.tag
    if args.type:
        filters["type"] = args.type

    # In the future, we can add a dispatcher here to choose different agents
    # based on query classification or flags.
    run_ask_brain(query, filters=filters if filters else None)

if __name__ == "__main__":
    main()
