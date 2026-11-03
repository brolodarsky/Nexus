"""
test_web_search.py — Unit tests for the Nexus Agentic Web Search tool (`web_search.py` & `search_web`).

Validates:
  1. Empty query and missing `TAVILY_API_KEY` guards in `execute_web_search()`.
  2. Normalized result extraction and parameter clamping (`max_results`, `search_depth`, `topic`, domain filters).
  3. Markdown digest formatting (`format_search_results_as_markdown`) with synthesized summary, exact citation URLs,
     and snippet truncation (`max_snippet_chars`).
  4. LangChain `@tool` wrapper (`search_web`) and binding into `CORE_TOOLS` (`src/nexus/agent/graph.py`).
"""
from typing import Any, Dict
import pytest

from nexus.agent.graph import CORE_TOOLS, TOOLS
from nexus.shared_tools import web_search
from nexus.shared_tools.shared import search_web


def test_execute_web_search_empty_query():
    """Verifies that an empty or whitespace-only query returns a clean validation error without calling Tavily."""
    res = web_search.execute_web_search("   ")
    assert res["query"] == ""
    assert res["results"] == []
    assert "cannot be empty" in (res.get("error") or "")


def test_execute_web_search_missing_api_key(monkeypatch: pytest.MonkeyPatch):
    """Verifies that missing `TAVILY_API_KEY` returns an actionable configuration error."""
    class DummySettings:
        tavily_api_key = None

    monkeypatch.setattr(web_search, "EngineSettings", lambda: DummySettings())
    res = web_search.execute_web_search("LangGraph StateGraph", api_key="")
    assert res["query"] == "LangGraph StateGraph"
    assert res["results"] == []
    assert "TAVILY_API_KEY is not configured" in (res.get("error") or "")


def test_execute_web_search_normalizes_tavily_response(monkeypatch: pytest.MonkeyPatch):
    """Verifies that `execute_web_search` clamps parameters and normalizes Tavily results."""
    captured_init: Dict[str, Any] = {}
    captured_invoke: Dict[str, Any] = {}

    class FakeTavilySearch:
        def __init__(self, **kwargs: Any):
            captured_init.update(kwargs)

        def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
            captured_invoke.update(payload)
            return {
                "query": payload["query"],
                "answer": "Fluoxetine is a potent CYP2D6 inhibitor.",
                "response_time": 0.42,
                "results": [
                    {
                        "title": "  CYP2D6 Drug Interactions - PubMed  ",
                        "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
                        "content": "Clinical review of SSRI CYP2D6 inhibition mechanisms.",
                        "score": 0.96,
                        "raw_content": None,
                    }
                ],
            }

    import langchain_tavily
    monkeypatch.setattr(langchain_tavily, "TavilySearch", FakeTavilySearch)

    res = web_search.execute_web_search(
        query="fluoxetine CYP2D6",
        max_results=99,  # Should clamp to 15
        search_depth="advanced",
        topic="general",
        include_domains=[" pubmed.ncbi.nlm.nih.gov ", ""],
        api_key="tvly-test-key",
    )

    assert captured_init["max_results"] == 15
    assert captured_init["search_depth"] == "advanced"
    assert captured_init["topic"] == "general"
    assert captured_init["include_domains"] == ["pubmed.ncbi.nlm.nih.gov"]
    assert captured_init["tavily_api_key"] == "tvly-test-key"
    assert captured_invoke["query"] == "fluoxetine CYP2D6"

    assert res.get("error") is None
    assert res["answer"] == "Fluoxetine is a potent CYP2D6 inhibitor."
    assert len(res["results"]) == 1
    assert res["results"][0]["title"] == "CYP2D6 Drug Interactions - PubMed"
    assert res["results"][0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/12345678/"


def test_format_search_results_as_markdown_and_truncation():
    """Verifies Markdown rendering with clickable links, explicit URLs, and snippet length capping."""
    sample_data = {
        "query": "LangGraph checkpointing",
        "answer": "SqliteSaver persists state across turns.",
        "results": [
            {
                "title": "LangGraph Persistence Guide",
                "url": "https://langchain-ai.github.io/langgraph/how-tos/persistence/",
                "content": "A" * 100,
                "score": 0.91,
            }
        ],
    }

    md = web_search.format_search_results_as_markdown(sample_data, max_snippet_chars=25)
    assert "### Web Search Results: `LangGraph checkpointing`" in md
    assert "**Synthesized Summary:** SqliteSaver persists state across turns." in md
    assert "1. **[LangGraph Persistence Guide](https://langchain-ai.github.io/langgraph/how-tos/persistence/)**" in md
    assert "- **URL:** https://langchain-ai.github.io/langgraph/how-tos/persistence/" in md
    assert f"- **Snippet:** {'A' * 25}..." in md


def test_search_web_tool_wrapper_and_graph_binding(monkeypatch: pytest.MonkeyPatch):
    """Verifies that `@tool def search_web` is bound into `CORE_TOOLS` and `TOOLS` and returns formatted Markdown."""
    core_tool_names = [t.name for t in CORE_TOOLS]
    parent_tool_names = [t.name for t in TOOLS]
    assert "search_web" in core_tool_names
    assert "search_web" in parent_tool_names

    monkeypatch.setattr(
        web_search,
        "execute_web_search",
        lambda **kwargs: {
            "query": kwargs["query"],
            "answer": "Verified test answer.",
            "results": [
                {
                    "title": "Example Study",
                    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9999999/",
                    "content": "Detailed study findings.",
                    "score": 0.99,
                }
            ],
        },
    )

    output = search_web.invoke({"query": "test clinical query", "max_results": 3})
    assert "Verified test answer." in output
    assert "https://pmc.ncbi.nlm.nih.gov/articles/PMC9999999/" in output
