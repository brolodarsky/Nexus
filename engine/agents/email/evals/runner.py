import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict

# Add engine to sys.path if running as script
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from agents.email.graph import app
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from core.constants import AI_MODEL

# Configuration
DATASET_PATH = Path(__file__).parent / "dataset.json"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

class EvalRunner:
    def __init__(self):
        self.grader_llm = ChatOpenAI(model=AI_MODEL, temperature=0.0)
        
    def load_dataset(self) -> List[Dict]:
        with open(DATASET_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    def run_eval(self):
        dataset = self.load_dataset()
        results = []
        
        print(f"Starting Email Agent Evaluation: {len(dataset)} cases\n")
        
        for i, case in enumerate(dataset):
            question = case["question"]
            expected_tools = case.get("tools_expected", [])
            
            print(f"[{i+1}/{len(dataset)}] Q: {question}")
            
            start_time = time.time()
            try:
                # Execute query directly on app to get full state trace
                from agents.email.prompts import EMAIL_SYSTEM_PROMPT
                messages = [
                    SystemMessage(content=EMAIL_SYSTEM_PROMPT),
                    HumanMessage(content=question)
                ]
                
                final_state = app.invoke({"messages": messages})
                duration = time.time() - start_time
                
                # Extract results
                out_messages = final_state["messages"]
                actual_answer = out_messages[-1].content
                
                # Extract tool calls
                tools_used = []
                for msg in out_messages:
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for tc in msg.tool_calls:
                            tools_used.append(tc['name'])
                
                # Verify JSON parsing
                is_json = False
                try:
                    ans_clean = actual_answer.strip()
                    if ans_clean.startswith("```"):
                        ans_clean = ans_clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                    parsed = json.loads(ans_clean)
                    if isinstance(parsed, list):
                        is_json = True
                except json.JSONDecodeError:
                    pass
                
                # Grading heuristics
                score = 0
                reasoning = ""
                
                if is_json:
                    score += 5
                    reasoning += "Returned valid JSON array. "
                else:
                    reasoning += "Did NOT return valid JSON array. "
                    
                tool_match = any(t in tools_used for t in expected_tools) if expected_tools else True
                if tool_match:
                    score += 5
                    reasoning += "Used correct tool. "
                else:
                    reasoning += f"Expected tools {expected_tools} but used {tools_used}. "
                
                result = {
                    "case_id": i + 1,
                    "question": question,
                    "actual_answer": actual_answer,
                    "tools_used": list(set(tools_used)),
                    "duration_sec": round(duration, 2),
                    "score": score,
                    "reasoning": reasoning,
                    "status": "PASS" if score >= 8 else "FAIL"
                }
                
            except Exception as e:
                print(f"  Error: {e}")
                result = {
                    "case_id": i + 1,
                    "question": question,
                    "error": str(e),
                    "status": "ERROR"
                }
            
            results.append(result)
            print(f"  Result: {result.get('status')} (Score: {result.get('score', 'N/A')}/10)")
            print(f"  Tools Used: {result.get('tools_used', [])}\n")

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = RESULTS_DIR / f"report_{timestamp}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({"results": results}, f, indent=2)
            
        print(f"Evaluation complete. Results saved to {report_path}")

if __name__ == "__main__":
    runner = EvalRunner()
    runner.run_eval()
