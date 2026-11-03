"""
web_search.py — Agentic web search engine for Nexus (Tavily API + Markdown formatting).

Provides deterministic, LLM-friendly web search capabilities backed by the Tavily Search API
(`langchain-tavily`). Returns structured result dictionaries (title, exact URL, snippet, relevance
score, and synthesized answer) as well as compact GitHub-Flavored Markdown digests designed to keep
agent context windows lean while preserving exact source citations.
"""
import argparse
import json
import sys
# Typing primitives:
# - Any: Dynamic value type for parsed JSON payloads from the Tavily API
# - Dict / List: Explicit collection types for structured search results and domain filter lists
# - Literal: Restricts string parameters (`search_depth`, `topic`) to valid Tavily API enum values
# - Optional: Equivalent to `T | None`, indicating parameters that may be omitted
from typing import Any, Dict, List, Literal, Optional

from nexus.core.config import EngineSettings
from nexus.core.logger import logger

# Type aliases constraining Tavily search configuration options:
# - SearchDepth: "basic" (1 API credit, fast ~1s lookup) vs. "advanced" (2 API credits, deeper content extraction)
# - SearchTopic: "general" (broad web/docs/studies), "news" (recent events), or "finance" (market/company data)
SearchDepth = Literal["basic", "advanced"]
SearchTopic = Literal["general", "news", "finance"]

# Cap individual snippet lengths so a single verbose webpage chunk never bloats the calling agent's context window
DEFAULT_MAX_SNIPPET_CHARS: int = 1200


# ── Core Data Layer: Tavily Search Execution ─────────────────────────────────

# Signature breakdown:
# - query: Natural-language or keyword search string (e.g. "Anthropic Claude 4.5 pricing", "fluoxetine CYP2D6")
# - max_results: Maximum number of ranked web results to return (clamped between 1 and 15)
# - search_depth: "basic" for fast standard lookups; "advanced" for deeper academic, clinical, or JD extraction
# - topic: Domain category filter ("general", "news", or "finance")
# - include_domains: Optional whitelist of domains (e.g. ["pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"])
# - exclude_domains: Optional blacklist of noisy or low-signal domains
# - include_answer: When True, requests a concise LLM-synthesized summary alongside individual source results
# - api_key: Optional explicit Tavily API key override; defaults to reading `TAVILY_API_KEY` via `EngineSettings()`
def execute_web_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    include_answer: bool = True,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a live web search via Tavily and return a normalized result dictionary.

    Returns:
        Dictionary with keys:
          - `query` (str): The executed search string.
          - `answer` (str | None): Optional synthesized summary from Tavily.
          - `results` (list[dict]): List of normalized items (`title`, `url`, `content`, `score`).
          - `error` (str | None): Present only if validation or network execution failed.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        return {"query": "", "answer": None, "results": [], "error": "Search query cannot be empty."}

    # Re-read `EngineSettings()` dynamically so `.env` updates to `TAVILY_API_KEY` take effect without restarting workers
    active_settings = EngineSettings()
    resolved_key = (api_key or active_settings.tavily_api_key or "").strip()
    if not resolved_key:
        return {
            "query": clean_query,
            "answer": None,
            "results": [],
            "error": "TAVILY_API_KEY is not configured in `.env`. Add `TAVILY_API_KEY=tvly-...` to enable web search.",
        }

    # Normalize and clamp arguments to safe bounds accepted by Tavily's REST validator
    clamped_max = max(1, min(int(max_results or 5), 15))
    normalized_depth: SearchDepth = "advanced" if str(search_depth).lower() == "advanced" else "basic"
    normalized_topic: SearchTopic = (
        str(topic).lower()  # type: ignore[assignment]
        if str(topic).lower() in ("general", "news", "finance")
        else "general"
    )
    clean_include = [d.strip() for d in (include_domains or []) if d and d.strip()]
    clean_exclude = [d.strip() for d in (exclude_domains or []) if d and d.strip()]

    try:
        # Lazy-import `TavilySearch` inside the function so static AST scanners (`tool_catalog.py`)
        # and lightweight CLI imports never pay import overhead unless a search is actually executed.
        from langchain_tavily import TavilySearch

        search_client = TavilySearch(
            max_results=clamped_max,
            search_depth=normalized_depth,
            topic=normalized_topic,
            include_answer=include_answer,
            include_domains=clean_include or None,
            exclude_domains=clean_exclude or None,
            tavily_api_key=resolved_key,
        )

        raw_response = search_client.invoke({"query": clean_query})

        # `TavilySearch.invoke` returns a dictionary on success, or an error string if the API rejected the request
        if isinstance(raw_response, str):
            return {"query": clean_query, "answer": None, "results": [], "error": raw_response}

        if not isinstance(raw_response, dict):
            return {
                "query": clean_query,
                "answer": None,
                "results": [],
                "error": f"Unexpected response type from Tavily: {type(raw_response).__name__}",
            }

        raw_results = raw_response.get("results") or []
        normalized_results: List[Dict[str, Any]] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            normalized_results.append(
                {
                    "title": (item.get("title") or "(Untitled)").strip(),
                    "url": (item.get("url") or "").strip(),
                    "content": (item.get("content") or "").strip(),
                    "score": item.get("score"),
                }
            )

        return {
            "query": clean_query,
            "answer": (raw_response.get("answer") or "").strip() or None,
            "results": normalized_results,
            "response_time": raw_response.get("response_time"),
        }

    except Exception as exc:
        logger.error(f"Web search failed for query '{clean_query}': {exc}")
        return {
            "query": clean_query,
            "answer": None,
            "results": [],
            "error": f"Web search failed: {exc}",
        }


# ── Presentation Layer: Markdown Formatting ──────────────────────────────────

def format_search_results_as_markdown(
    search_data: Dict[str, Any],
    max_snippet_chars: int = DEFAULT_MAX_SNIPPET_CHARS,
) -> str:
    """Format a normalized `execute_web_search` dictionary into clean Markdown with clickable citations.

    Args:
        search_data: Output dictionary returned by `execute_web_search()`.
        max_snippet_chars: Maximum character length per result snippet before appending an ellipsis.
    """
    if search_data.get("error"):
        return f"Error executing web search: {search_data['error']}"

    query = search_data.get("query", "")
    answer = search_data.get("answer")
    results = search_data.get("results") or []

    lines: List[str] = [f"### Web Search Results: `{query}`"]

    if answer:
        lines.append(f"\n**Synthesized Summary:** {answer}")

    if not results:
        lines.append("\n*(No matching web results found.)*")
        return "\n".join(lines)

    lines.append("")
    for idx, item in enumerate(results, start=1):
        title = item.get("title") or "(Untitled)"
        url = item.get("url") or ""
        snippet = item.get("content") or ""
        if max_snippet_chars > 0 and len(snippet) > max_snippet_chars:
            snippet = snippet[:max_snippet_chars].rstrip() + "..."

        # Render exact markdown link `[Title](URL)` so downstream agents can cite the exact source URL
        header = f"{idx}. **[{title}]({url})**" if url else f"{idx}. **{title}**"
        lines.append(header)
        if url:
            lines.append(f"   - **URL:** {url}")
        if snippet:
            lines.append(f"   - **Snippet:** {snippet}")
        lines.append("")

    return "\n".join(lines).strip()


# ── CLI Entrypoint (`python -m nexus.shared_tools.web_search`) ───────────────

def main() -> None:
    """Command-line interface for running web searches via `.venv\\Scripts\\python.exe -m nexus.shared_tools.web_search`."""
    parser = argparse.ArgumentParser(
        description="Agentic web search engine for Nexus (Tavily API). Returns Markdown with exact citation URLs."
    )
    parser.add_argument("query", nargs="?", help="Search query string (e.g. 'LangGraph StateGraph docs').")
    parser.add_argument("-q", "--query", dest="query_flag", help="Search query string (alternative flag syntax).")
    parser.add_argument(
        "-n",
        "--max-results",
        type=int,
        default=5,
        help="Maximum number of results to return (1-15, default: 5).",
    )
    parser.add_argument(
        "-d",
        "--depth",
        choices=["basic", "advanced"],
        default="basic",
        help="Search depth: 'basic' (fast) or 'advanced' (deep extraction, default: basic).",
    )
    parser.add_argument(
        "-t",
        "--topic",
        choices=["general", "news", "finance"],
        default="general",
        help="Search topic category (default: general).",
    )
    parser.add_argument(
        "--domain",
        action="append",
        dest="include_domains",
        help="Restrict search to specific domain(s) (repeatable, e.g. --domain pubmed.ncbi.nlm.nih.gov).",
    )
    parser.add_argument(
        "--exclude-domain",
        action="append",
        dest="exclude_domains",
        help="Exclude specific domain(s) from results (repeatable).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted Markdown.",
    )

    args = parser.parse_args()
    final_query = (args.query_flag or args.query or "").strip()
    if not final_query:
        parser.error("A search query is required (pass as positional argument or via `-q/--query`).")

    # Ensure UTF-8 stdout on Windows consoles so Unicode punctuation and arrows never raise UnicodeEncodeError
    if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    data = execute_web_search(
        query=final_query,
        max_results=args.max_results,
        search_depth=args.depth,
        topic=args.topic,
        include_domains=args.include_domains,
        exclude_domains=args.exclude_domains,
    )

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(format_search_results_as_markdown(data))

    if data.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
