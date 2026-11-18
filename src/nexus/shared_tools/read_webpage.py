"""
read_webpage.py — Universal Webpage Extractor & Conversation Cache Reader for the Nexus Engine.

Checks the active per-conversation capture cache (`conversation_cache.get_capture`) first so
already-read browser tabs or webpages resolve instantaneously with zero network traffic, then
falls back to universal HTML extraction via `trafilatura` (with generic `<script type="application/ld+json">`
and `<meta>` fallback when static HTML is a client-side JS shell) and caches the result.
"""
import argparse
import html as html_lib
import json
import re
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import httpx
import trafilatura

from nexus.core.conversation_cache import (
    get_active_conversation_id,
    get_capture,
    put_capture,
)

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}
_MIN_VALID_LEN = 250


# ── HTTP & HTML/Markdown Utilities ───────────────────────────────────────────

# Fetches raw HTML text from `url`, used as secondary transport when `trafilatura.fetch_url` is blocked.
def _fetch_html(url: str, timeout: float = 15.0) -> Optional[str]:
    """Fetches raw HTML text from `url` via httpx, returning None on HTTP or network failure."""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=_HTTP_HEADERS) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return None
            return resp.text
    except Exception:
        return None


# Converts JSON-LD/meta HTML snippets (including entity-escaped `&lt;p&gt;`) to clean Markdown.
def _html_to_markdown(raw_html: str) -> str:
    """Converts HTML markup (unescaping entities if needed) into clean Markdown."""
    if not raw_html:
        return ""
    text = raw_html.strip()
    # Unescape entity-encoded HTML tags (`&lt;p&gt;...&lt;/p&gt;`) sometimes embedded in JSON-LD strings
    if "&lt;" in text and "<" not in text:
        text = html_lib.unescape(text)

    # Strip non-content `<script>`/`<style>` blocks before tag conversion
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)

    # Convert headings `<h1>`..`<h6>` into Markdown headings
    def _heading_repl(match: re.Match[str]) -> str:
        level = min(6, max(1, int(match.group(1))))
        inner = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        return f"\n\n{'#' * level} {inner}\n\n" if inner else "\n\n"

    text = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>", _heading_repl, text, flags=re.IGNORECASE | re.DOTALL)

    # Convert anchor links `<a href="...">label</a>` into `[label](url)` when href is an HTTP link
    def _link_repl(match: re.Match[str]) -> str:
        href = (match.group(1) or "").strip()
        label = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if href.startswith(("http://", "https://")) and label:
            return f"[{label}]({href})"
        return label

    text = re.sub(
        r"""<a[^>]+href=["']([^"']+)["'][^>]*>(.*?)</a>""",
        _link_repl,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Convert inline bold/italic formatting cleanly when inner text is non-empty
    text = re.sub(
        r"<(?:strong|b)[^>]*>(.*?)</(?:strong|b)>",
        lambda m: f"**{m.group(1).strip()}**" if m.group(1).strip() else "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<(?:em|i)[^>]*>(.*?)</(?:em|i)>",
        lambda m: f"*{m.group(1).strip()}*" if m.group(1).strip() else "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Convert list items (`<li>`) and block breaks (`<br>`, `<p>`, `<div>`) into readable Markdown lines
    text = re.sub(r"<li[^>]*>\s*(?:<p[^>]*>)?", "\n- ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:</p>)?\s*</li>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(?:p|div|ul|ol|section|article|tr)[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<t[dh][^>]*>", " | ", text, flags=re.IGNORECASE)

    # Strip remaining HTML tags and unescape any remaining HTML entities (`&amp;`, `&nbsp;`, etc.)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text).replace("\xa0", " ").replace("\r\n", "\n")

    # Collapse horizontal whitespace inside lines while preserving paragraph and bullet boundaries
    cleaned_lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    collapsed = "\n".join(cleaned_lines)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    return collapsed.strip()


def _is_spa_shell(text: str) -> bool:
    """Returns True if extracted text is empty or a client-side JavaScript SPA placeholder."""
    low = (text or "").strip().lower()
    if not low:
        return True
    if "you need to enable javascript to run this app" in low:
        return True
    if ("please enable javascript" in low or "enable javascript to view" in low) and len(low) < 600:
        return True
    return False


def _extract_html_title(raw_html: str, fallback_url: str = "") -> str:
    """Extracts a clean page title from `<title>` or `og:title`, falling back to URL host/path."""
    if raw_html:
        for pattern in (
            r"<title[^>]*>(.*?)</title>",
            r"""<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']""",
            r"""<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:title["']""",
        ):
            match = re.search(pattern, raw_html, flags=re.IGNORECASE | re.DOTALL)
            if match:
                cleaned = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", "", match.group(1)))).strip()
                if cleaned:
                    return cleaned
    if fallback_url:
        parts = urlsplit(fallback_url)
        tail = parts.path.strip("/").split("/")[-1] if parts.path.strip("/") else ""
        return f"{parts.netloc} - {tail}" if tail else (parts.netloc or fallback_url)
    return "Web Capture"


# ── Universal JSON-LD & Meta Fallback (for Static SPA Shells) ────────────────

def _extract_jsonld_content(raw_html: str) -> Optional[str]:
    """Extracts structured Schema.org content (`JobPosting`, `Article`, etc.) from JSON-LD `<script>` tags."""
    if not raw_html:
        return None
    scripts = re.findall(
        r"""<script[^>]+type=["']application/ld\+json["'][^>]*>(.*?)</script>""",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    candidates: List[Dict[str, Any]] = []
    for raw_script in scripts:
        try:
            parsed = json.loads(raw_script.strip())
        except Exception:
            continue
        stack = parsed if isinstance(parsed, list) else [parsed]
        while stack:
            node = stack.pop(0)
            if isinstance(node, dict):
                if isinstance(node.get("@graph"), list):
                    stack.extend(node["@graph"])
                if node.get("description") or node.get("articleBody"):
                    candidates.append(node)

    for item in candidates:
        title = str(item.get("title") or item.get("headline") or item.get("name") or "Web Document").strip()
        org_raw = item.get("hiringOrganization") or item.get("publisher") or item.get("author")
        if isinstance(org_raw, list) and org_raw:
            org_raw = org_raw[0]
        org_name = str(org_raw.get("name") or "").strip() if isinstance(org_raw, dict) else str(org_raw or "").strip()

        # Format `jobLocation` (single dict or list of Place dicts) if present
        locs_raw = item.get("jobLocation")
        loc_items = locs_raw if isinstance(locs_raw, list) else ([locs_raw] if locs_raw else [])
        loc_strings: List[str] = []
        for loc in loc_items:
            if isinstance(loc, dict):
                addr = loc.get("address") if isinstance(loc.get("address"), dict) else {}
                parts = [
                    str(addr.get(k) or "").strip()
                    for k in ("addressLocality", "addressRegion", "addressCountry")
                ]
                loc_str = ", ".join(p for p in parts if p) or str(loc.get("name") or "").strip()
                if loc_str:
                    loc_strings.append(loc_str)
            elif isinstance(loc, str) and loc.strip():
                loc_strings.append(loc.strip())

        # Format `baseSalary` MonetaryAmount if present
        salary_str = ""
        sal_raw = item.get("baseSalary")
        if isinstance(sal_raw, dict):
            curr = str(sal_raw.get("currency") or "").strip()
            val = sal_raw.get("value")
            if isinstance(val, dict):
                lo, hi, exact = val.get("minValue"), val.get("maxValue"), val.get("value")
                if lo is not None and hi is not None:
                    salary_str = f"{curr} {lo} – {hi}".strip()
                elif exact is not None:
                    salary_str = f"{curr} {exact}".strip()
            elif val is not None:
                salary_str = f"{curr} {val}".strip()

        raw_body = str(item.get("articleBody") or item.get("description") or "")
        body_md = _html_to_markdown(raw_body)
        if len(body_md) < _MIN_VALID_LEN or _is_spa_shell(body_md):
            continue

        header_lines = [f"# {title}"]
        if org_name:
            org_label = "Company" if item.get("hiringOrganization") else "Organization / Author"
            header_lines.append(f"- **{org_label}:** {org_name}")
        if loc_strings:
            header_lines.append(f"- **Location:** {'; '.join(loc_strings)}")
        if salary_str:
            header_lines.append(f"- **Compensation:** {salary_str}")
        return "\n".join(header_lines) + "\n\n" + body_md
    return None


def _extract_meta_description(raw_html: str) -> Optional[str]:
    """Extracts `<meta name="description">` or `og:description` if substantial (>=250 chars)."""
    if not raw_html:
        return None
    for pattern in (
        r"""<meta[^>]+(?:name|property)=["'](?:og:)?description["'][^>]+content=["']([^"']+)["']""",
        r"""<meta[^>]+content=["']([^"']+)["'][^>]+(?:name|property)=["'](?:og:)?description["']""",
    ):
        match = re.search(pattern, raw_html, flags=re.IGNORECASE)
        if match:
            text = _html_to_markdown(html_lib.unescape(match.group(1)))
            if len(text) >= _MIN_VALID_LEN and not _is_spa_shell(text):
                return text
    return None


# ── Public Universal Extraction + Per-Conversation Cache API ─────────────────

# `url`: Target HTTP/HTTPS URL to resolve from cache or fetch via `trafilatura`.
# `output_format`: Output format passed to `trafilatura.extract` (default `"markdown"`).
# `conversation_id`: Optional explicit conversation scope (defaults via `get_active_conversation_id()`).
# Returns `(content, cache_key)` tuple so callers get both the verbatim body and its `cache://...` handle.
def scrape_url_with_cache(
    url: str,
    output_format: str = "markdown",
    conversation_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Checks `conversation_cache` first, else extracts universally via `trafilatura` (+ JSON-LD/meta fallback) and caches."""
    cleaned_url = (url or "").strip()
    if not cleaned_url:
        return None, None

    convo_id = (conversation_id or "").strip() or get_active_conversation_id()

    try:
        # 1. Instant hit if already read in this conversation (e.g. from `read_browser_tabs` or an earlier `read_webpage` call)
        try:
            cached = get_capture(convo_id, cleaned_url)
            if cached and str(cached.get("content") or "").strip():
                return str(cached["content"]), str(cached["cache_key"])
        except Exception:
            pass

        # 2. Universal static HTML fetch (`trafilatura` first, then `httpx`)
        downloaded = trafilatura.fetch_url(cleaned_url)
        if downloaded is None:
            downloaded = _fetch_html(cleaned_url)

        final_content: Optional[str] = None
        if downloaded:
            extracted = trafilatura.extract(
                downloaded,
                output_format=output_format,
                include_comments=False,
                include_tables=True,
                include_links=True,
            )
            if extracted and len(extracted.strip()) >= _MIN_VALID_LEN and not _is_spa_shell(extracted):
                final_content = extracted.strip()
            else:
                # Universal fallback for static SPA shells containing JSON-LD or `<meta>` text
                final_content = _extract_jsonld_content(downloaded) or _extract_meta_description(downloaded)

        if final_content:
            cache_key: Optional[str] = None
            try:
                title = _extract_html_title(downloaded or "", fallback_url=cleaned_url)
                cache_key = put_capture(
                    conversation_id=convo_id,
                    source_type="web",
                    title=title,
                    content=final_content,
                    source_url=cleaned_url,
                )
            except Exception:
                cache_key = None
            return final_content, cache_key

        if downloaded is None:
            print(f"Error: Could not fetch content from {cleaned_url}", file=sys.stderr)
        return None, None
    except Exception as e:
        print(f"Exception while scraping {cleaned_url}: {e}", file=sys.stderr)
        return None, None


def scrape_url(url: str, output_format: str = "markdown") -> Optional[str]:
    """Extracts clean webpage content (checking `conversation_cache` first and auto-caching fresh fetches)."""
    content, _ = scrape_url_with_cache(url, output_format=output_format)
    return content


def main() -> None:
    """CLI entrypoint for `python -m nexus.shared_tools.read_webpage`."""
    parser = argparse.ArgumentParser(description="Universal webpage extractor & cache reader for Nexus Engine.")
    parser.add_argument("url", help="The URL to scrape")
    parser.add_argument("-o", "--output", help="Path to save the output (optional)")
    parser.add_argument(
        "-f",
        "--format",
        choices=["markdown", "txt", "json", "xml"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    args = parser.parse_args()
    content, cache_key = scrape_url_with_cache(args.url, output_format=args.format)

    if content:
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(content)
            key_note = f" (cache key: {cache_key})" if cache_key else ""
            print(f"Successfully saved content to {args.output}{key_note}")
        else:
            if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
                sys.stdout.reconfigure(encoding="utf-8")
            if cache_key and args.format in ("markdown", "txt"):
                short_key = cache_key[len("cache://") :] if cache_key.startswith("cache://") else cache_key
                print(
                    f"- **Cache Key:** `{cache_key}` *(embed verbatim via `{{{{cache:{short_key}}}}}`)*\n\n"
                    f"{content}"
                )
            else:
                print(content)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
