import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add engine to sys.path if running as script

from nexus.agents.router.graph import classify_content

# Configuration
DATASET_PATH = Path(__file__).parent / "dataset.json"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

class RouterEvalRunner:
    def load_dataset(self):
        with open(DATASET_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    def run_eval(self):
        dataset = self.load_dataset()
        results = []
        
        print(f"Starting Router Evaluation: {len(dataset)} cases\n")
        
        for i, case in enumerate(dataset):
            input_text = case["input"]
            expected = case["expected_domain"]
            
            print(f"[{i+1}/{len(dataset)}] Input: {input_text[:50]}...")
            
            start_time = time.time()
            try:
                # We only need to test the classifier node, not the full graph
                state = {"raw_content": input_text, "messages": []}
                result_state = classify_content(state)
                
                duration = time.time() - start_time
                actual_domain = result_state.get("domain")
                
                # Discrete assertion
                passed = (actual_domain == expected)
                
                # Extract token usage from the LLM message if available
                token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                if result_state.get("messages") and hasattr(result_state["messages"][0], 'usage_metadata'):
                    usage = result_state["messages"][0].usage_metadata
                    if usage:
                        token_usage["prompt_tokens"] = usage.get("input_tokens", 0)
                        token_usage["completion_tokens"] = usage.get("output_tokens", 0)
                        token_usage["total_tokens"] = usage.get("total_tokens", 0)

                result = {
                    "case_id": i + 1,
                    "input": input_text,
                    "expected_domain": expected,
                    "actual_domain": actual_domain,
                    "summary": result_state.get("summary"),
                    "confidence": result_state.get("confidence"),
                    "reasoning": result_state.get("reasoning"),
                    "duration_sec": round(duration, 2),
                    "token_usage": token_usage,
                    "status": "PASS" if passed else "FAIL"
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
            tok = result.get('token_usage', {})
            print(f"  Result: {result.get('status')} (Expected: {expected}, Got: {result.get('actual_domain')})")
            print(f"  Duration: {result.get('duration_sec', 'N/A')}s | Tokens: {tok.get('total_tokens', 'N/A')}\n")

        summary = self.get_summary(results)
        report_data = {
            "summary": summary,
            "results": results
        }

        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = RESULTS_DIR / f"report_{timestamp}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2)
            
        self.print_summary(summary, report_path)

    def get_summary(self, results) -> dict:
        total = len(results)
        passed = len([r for r in results if r.get("status") == "PASS"])
        errors = len([r for r in results if r.get("status") == "ERROR"])
        total_duration = sum([r.get("duration_sec", 0) for r in results])
        avg_duration = total_duration / total if total else 0
        
        total_prompt = sum(r.get("token_usage", {}).get("prompt_tokens", 0) for r in results)
        total_completion = sum(r.get("token_usage", {}).get("completion_tokens", 0) for r in results)
        total_tokens = sum(r.get("token_usage", {}).get("total_tokens", 0) for r in results)
        
        return {
            "total_cases": total,
            "passed": passed,
            "failed": total - passed - errors,
            "errors": errors,
            "accuracy": round(passed / total * 100, 1) if total > 0 else 0,
            "total_duration_sec": round(total_duration, 2),
            "avg_duration_sec": round(avg_duration, 2),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "avg_tokens_per_query": total_tokens // total if total else 0
        }

    def print_summary(self, summary, report_path):
        print("="*50)
        print("ROUTER EVAL SUMMARY")
        print("="*50)
        print(f"Total Cases:    {summary['total_cases']}")
        print(f"Passed:         {summary['passed']}")
        print(f"Failed:         {summary['failed']}")
        print(f"Accuracy:       {summary['accuracy']}%")
        print(f"Avg Duration:   {summary['avg_duration_sec']:.2f}s")
        print(f"Total Tokens:   {summary['total_tokens']:,}")
        print(f"Avg Tokens/Q:   {summary['avg_tokens_per_query']:,}")
        print(f"---")
        print(f"Report:         {report_path}")
        print("="*50)

if __name__ == "__main__":
    runner = RouterEvalRunner()
    runner.run_eval()
