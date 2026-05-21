import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

# Add engine to sys.path if running as script
sys.path.append(str(Path(__file__).parent.parent))

from agents.librarian.agent import execute_vault_query
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from core.constants import AI_MODEL

# Configuration
DATASET_PATH = Path(__file__).parent / "dataset.json"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

GRADER_PROMPT = """
You are an expert evaluator for an agentic file reader and responder system.
Your goal is to determine if the system's generated answer is accurate and grounded based on the provided expected answer and the files it claimed to read.

### Evaluation Criteria:
1. **Accuracy**: Does the answer correctly convey the facts mentioned in the expected answer?
2. **Groundedness**: Does the agent cite or use the correct files?
3. **Hallucination**: Does the agent make up facts not present in the vault?

### Input:
- **Question**: {question}
- **Expected Answer**: {expected_answer}
- **Actual Answer**: {actual_answer}
- **Files Read**: {files_read}

### Output:
Return a JSON object with:
- "score": 0 to 10 (10 being perfect)
- "reasoning": Brief explanation of the score.
- "grounded": true/false
"""

class EvalRunner:
    def __init__(self):
        self.grader_llm = ChatOpenAI(model=AI_MODEL, temperature=0.0)
        
    def load_dataset(self) -> List[Dict]:
        with open(DATASET_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    def run_eval(self):
        dataset = self.load_dataset()
        results = []
        
        print(f"Starting Evaluation: {len(dataset)} cases\n")
        
        for i, case in enumerate(dataset):
            question = case["question"]
            expected = case["expected_answer"]
            target_source = case.get("source_file")
            
            print(f"[{i+1}/{len(dataset)}] Q: {question}")
            
            start_time = time.time()
            try:
                # Execute query
                final_state = execute_vault_query(question)
                duration = time.time() - start_time
                
                # Extract results
                messages = final_state["messages"]
                actual_answer = messages[-1].content
                
                # Extract tool calls (files read)
                files_read = []
                for msg in messages:
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for tc in msg.tool_calls:
                            if tc['name'] == 'read_note':
                                files_read.append(tc['args'].get('note_path'))
                            elif tc['name'] == 'read_toc':
                                files_read.append("Table of Contents.md")
                            elif tc['name'] == 'get_vault_structure':
                                vs_path = tc['args'].get('path')
                                files_read.append(f"[structure] {vs_path or 'root'}")
                
                # Extract token usage from AI messages
                token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                for msg in messages:
                    usage = getattr(msg, 'usage_metadata', None)
                    if usage:
                        token_usage["prompt_tokens"] += usage.get("input_tokens", 0)
                        token_usage["completion_tokens"] += usage.get("output_tokens", 0)
                        token_usage["total_tokens"] += usage.get("total_tokens", 0)

                # Grade the answer
                grade = self.grade_answer(question, expected, actual_answer, files_read)
                
                result = {
                    "case_id": i + 1,
                    "question": question,
                    "expected_answer": expected,
                    "actual_answer": actual_answer,
                    "files_read": list(set(files_read)),
                    "target_source": target_source,
                    "duration_sec": round(duration, 2),
                    "token_usage": token_usage,
                    "score": grade.get("score"),
                    "reasoning": grade.get("reasoning"),
                    "grounded": grade.get("grounded"),
                    "status": "PASS" if grade.get("score", 0) >= 7 else "FAIL"
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
            tok = result.get('token_usage', {})
            print(f"  Result: {result.get('status')} (Score: {result.get('score', 'N/A')}/10)")
            print(f"  Duration: {result.get('duration_sec', 'N/A')}s | Tokens: {tok.get('total_tokens', 'N/A')}")
            print(f"  Files Read: {result.get('files_read', [])}\n")

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = RESULTS_DIR / f"report_{timestamp}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
            
        self.print_summary(results, report_path)

    def grade_answer(self, question, expected, actual, files_read) -> Dict:
        prompt = GRADER_PROMPT.format(
            question=question,
            expected_answer=expected,
            actual_answer=actual,
            files_read=", ".join(files_read) if files_read else "None"
        )
        
        try:
            response = self.grader_llm.invoke([
                SystemMessage(content="You are a strict technical evaluator."),
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
            return {"score": 0, "reasoning": f"Grading failed: {e}", "grounded": False}

    def print_summary(self, results, report_path):
        total = len(results)
        passed = len([r for r in results if r.get("status") == "PASS"])
        errors = len([r for r in results if r.get("status") == "ERROR"])
        avg_score = sum([r.get("score", 0) for r in results]) / (total - errors) if total > errors else 0
        avg_duration = sum([r.get("duration_sec", 0) for r in results]) / total if total else 0
        
        # Token totals
        total_prompt = sum(r.get("token_usage", {}).get("prompt_tokens", 0) for r in results)
        total_completion = sum(r.get("token_usage", {}).get("completion_tokens", 0) for r in results)
        total_tokens = sum(r.get("token_usage", {}).get("total_tokens", 0) for r in results)
        
        print("="*50)
        print("SUMMARY")
        print("="*50)
        print(f"Total Cases:    {total}")
        print(f"Passed:         {passed}")
        print(f"Failed:         {total - passed - errors}")
        print(f"Errors:         {errors}")
        print(f"Avg Score:      {avg_score:.1f}/10")
        print(f"Avg Duration:   {avg_duration:.2f}s")
        print(f"---")
        print(f"Prompt Tokens:  {total_prompt:,}")
        print(f"Output Tokens:  {total_completion:,}")
        print(f"Total Tokens:   {total_tokens:,}")
        print(f"Avg Tokens/Q:   {total_tokens // total if total else 0:,}")
        print(f"---")
        print(f"Report:         {report_path}")
        print("="*50)

if __name__ == "__main__":
    runner = EvalRunner()
    runner.run_eval()
