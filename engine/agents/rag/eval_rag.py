import json
import time
import sys
from pathlib import Path

# Ensure the 'engine' directory is in sys.path
engine_path = Path(__file__).parent.parent.parent
if str(engine_path) not in sys.path:
    sys.path.insert(0, str(engine_path))

# Remove the current script's directory from sys.path
script_dir = str(Path(__file__).parent)
if script_dir in sys.path:
    sys.path.remove(script_dir)

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from core.constants import AI_MODEL, OPENAI_API_KEY
from agents.rag.graph import build_rag_graph

def evaluate_with_llm(query, expected_criteria, actual_answer):
    llm = ChatOpenAI(model=AI_MODEL, temperature=0, api_key=OPENAI_API_KEY)
    prompt = f"""You are an evaluator grading a RAG agent's response.
Query: {query}
Expected Criteria: {expected_criteria}
Actual Answer: {actual_answer}

Did the actual answer meet the expected criteria? Answer ONLY with "PASS" or "FAIL", followed by a one sentence reason."""
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content

def run_evals():
    print("Running RAG Evals...")
    dataset_path = Path(__file__).parent / "eval_dataset.json"
    with open(dataset_path, "r") as f:
        dataset = json.load(f)
    
    graph = build_rag_graph()
    
    total = len(dataset)
    passed = 0

    for i, item in enumerate(dataset):
        query = item["query"]
        expected = item.get("expected_criteria", "Provide an accurate answer based on notes.")
        print(f"\n[{i+1}/{total}] Query: {query}")
        
        initial_state = {"messages": [HumanMessage(content=query)]}
        result = graph.invoke(initial_state)
        answer = result["messages"][-1].content
        print(f"Actual Answer: {answer}")
        
        eval_result = evaluate_with_llm(query, expected, answer)
        print(f"Result: {eval_result}")
        if eval_result.strip().startswith("PASS"):
            passed += 1
            
    print(f"\nEval Results: {passed}/{total} Passed")

if __name__ == "__main__":
    run_evals()
