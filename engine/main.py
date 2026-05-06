import sys
import urllib.parse
from langchain_core.messages import HumanMessage
from core.constants import CHROMA_PATH
from agents.rag.graph import build_rag_graph

# Force UTF-8 output
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def run_ask_brain(query: str):
    """
    Executes the RAG agent for a given query.
    """
    print(f"\n[Brain 2] Query: {query}\n")
    
    app = build_rag_graph()
    
    initial_state = {
        "messages": [HumanMessage(content=query)],
        "context": [],
        "sources": [],
    }
    
    final_state = app.invoke(initial_state)
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
            print(f"    {obsidian_link}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python engine/main.py \"<your question>\"")
        sys.exit(1)
        
    query = " ".join(sys.argv[1:])
    
    # In the future, we can add a dispatcher here to choose different agents
    # based on query classification or flags.
    run_ask_brain(query)

if __name__ == "__main__":
    main()
