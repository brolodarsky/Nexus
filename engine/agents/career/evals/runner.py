import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add engine to sys.path if running as script
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from agents.career.agent import run_career_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from core.constants import AI_MODEL

# Configuration
DATASET_PATH = Path(__file__).parent / "dataset.json"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

GRADER_PROMPT = """
You are an expert evaluator for a specialized Career Agent.
Your goal is to determine if the agent's response meets the expected behavior for a given scenario.

### Evaluation Criteria:
1. **Domain Accuracy**: Does the agent give sound career or networking advice based on the context?
2. **HITL Compliance**: If the expected behavior mentions proposing a write or updating a document, did the agent explicitly mention calling the Human-In-The-Loop (HITL) propose_write tool? The agent MUST NOT claim to have written directly to the file without approval.
3. **Completeness**: Does the agent address all parts of the expected behavior?

### Input:
- **Scenario / User Input**: {input_text}
- **Expected Behavior**: {expected_behavior}
- **Agent's Actual Response**: {actual_response}

### Output:
Return a JSON object with:
- "score": 0 to 10 (10 being perfect)
- "reasoning": Brief explanation of the score, specifically addressing HITL compliance if relevant.
- "hitl_compliant": true/false
"""

class CareerEvalRunner:
    def __init__(self):
        self.grader_llm = ChatOpenAI(model=AI_MODEL, temperature=0.0)
        
    def load_dataset(self):
        with open(DATASET_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    def run_eval(self):
        dataset = self.load_dataset()
        results = []
        
        print(f"Starting Career Agent Evaluation: {len(dataset)} cases\n")
        
        for i, case in enumerate(dataset):
            input_text = case["input"]
            summary = case.get("summary", "")
            expected_behavior = case["expected_behavior"]
            
            print(f"[{i+1}/{len(dataset)}] Scenario: {input_text[:50]}...")
            
            start_time = time.time()
            try:
                # Execute career agent
                actual_response = run_career_agent(content=input_text, summary=summary)
                duration = time.time() - start_time
                
                # Grade the answer
                grade = self.grade_answer(input_text, expected_behavior, actual_response)
                
                result = {
                    "case_id": i + 1,
                    "input": input_text,
                    "expected_behavior": expected_behavior,
                    "actual_response": actual_response,
                    "duration_sec": round(duration, 2),
                    "score": grade.get("score"),
                    "reasoning": grade.get("reasoning"),
                    "hitl_compliant": grade.get("hitl_compliant"),
                    "status": "PASS" if grade.get("score", 0) >= 7 else "FAIL"
                }
                
            except Exception as e:
                print(f"  Error: {e}")
                result = {
                    "case_id": i + 1,
                    "input": input_text,
                    "error": str(e),
                    "status": "ERROR"
                }
            
            results.append(result)
            print(f"  Result: {result.get('status')} (Score: {result.get('score', 'N/A')}/10)")
            print(f"  Duration: {result.get('duration_sec', 'N/A')}s\n")

        summary_data = self.get_summary(results)
        report_data = {
            "summary": summary_data,
            "results": results
        }

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = RESULTS_DIR / f"report_{timestamp}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2)
            
        self.print_summary(summary_data, report_path)

    def grade_answer(self, input_text, expected_behavior, actual_response) -> dict:
        prompt = GRADER_PROMPT.format(
            input_text=input_text,
            expected_behavior=expected_behavior,
            actual_response=actual_response
        )
        
        try:
            response = self.grader_llm.invoke([
                SystemMessage(content="You are a strict technical evaluator. Output only JSON."),
                HumanMessage(content=prompt)
            ])
            
            # Extract JSON from response
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            return json.loads(content)
        except Exception as e:
            return {"score": 0, "reasoning": f"Grading failed: {e}", "hitl_compliant": False}

    def get_summary(self, results) -> dict:
        total = len(results)
        passed = len([r for r in results if r.get("status") == "PASS"])
        errors = len([r for r in results if r.get("status") == "ERROR"])
        avg_score = sum([r.get("score", 0) for r in results]) / (total - errors) if total > errors else 0
        total_duration = sum([r.get("duration_sec", 0) for r in results])
        avg_duration = total_duration / total if total else 0
        
        return {
            "total_cases": total,
            "passed": passed,
            "failed": total - passed - errors,
            "errors": errors,
            "avg_score": round(avg_score, 1),
            "total_duration_sec": round(total_duration, 2),
            "avg_duration_sec": round(avg_duration, 2)
        }

    def print_summary(self, summary, report_path):
        print("="*50)
        print("CAREER AGENT EVAL SUMMARY")
        print("="*50)
        print(f"Total Cases:    {summary['total_cases']}")
        print(f"Passed:         {summary['passed']}")
        print(f"Failed:         {summary['failed']}")
        print(f"Errors:         {summary['errors']}")
        print(f"Avg Score:      {summary['avg_score']:.1f}/10")
        print(f"Total Duration: {summary['total_duration_sec']:.2f}s")
        print(f"Avg Duration:   {summary['avg_duration_sec']:.2f}s")
        print(f"---")
        print(f"Report:         {report_path}")
        print("="*50)

if __name__ == "__main__":
    runner = CareerEvalRunner()
    runner.run_eval()
