"""
api.py — Public entry points for the Router Agent.
"""
import time

from agents.router.graph import router_graph, router_tracer

def route_content(content: str, filters: dict = None) -> dict:
    """
    Entry point: classify and route a piece of raw content.

    Args:
        content: The raw text to classify (email body, note, job description, etc.)
        filters: Optional filters dict to pass along to the Librarian agent

    Returns:
        dict with keys: domain, summary, confidence, reasoning, response
    """
    initial_state = {
        "messages": [],
        "raw_content": content,
        "filters": filters,
        "domain": None,
        "summary": None,
        "confidence": None,
        "reasoning": None,
    }

    t0 = time.time()
    final_state = router_graph.invoke(initial_state)
    elapsed = time.time() - t0

    last_message = final_state["messages"][-1] if final_state["messages"] else None
    router_tracer.agent_end()
    router_tracer.info(f"Pipeline completed in {elapsed:.1f}s")

    return {
        "domain": final_state.get("domain"),
        "summary": final_state.get("summary"),
        "confidence": final_state.get("confidence"),
        "reasoning": final_state.get("reasoning"),
        "response": last_message.content if last_message else "",
    }


# ── CLI End-to-End Test ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  NEXUS 3-AGENT PIPELINE: END-TO-END TEST")
    print("  Router (Email Subgraph) -> Career Agent (DPFH) -> Librarian (if needed)")
    print("=" * 60)

    test_query = "check my email for any recent job messages or recruiter outreach"

    print(f"\nINPUT: {test_query}\n")
    print("-" * 60)

    result = route_content(test_query)

    print(f"\n🔀 ROUTER CLASSIFICATION:")
    print(f"   Domain:     {result['domain']}")
    print(f"   Confidence: {result['confidence']}")
    print(f"   Summary:    {result['summary']}")
    print(f"   Reasoning:  {result['reasoning']}")
    print(f"\n{'='*60}")
    print(f"🎯 CAREER AGENT RESPONSE:")
    print(f"{'='*60}\n")
    print(result["response"])
