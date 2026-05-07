import re
import hashlib
import yaml
import tiktoken
from agents.rag.constants import MAX_TOKENS

# cl100k_base is the tokenizer used by GPT-4 and text-embedding-3-small.
_TOKENIZER = tiktoken.get_encoding("cl100k_base")

# ── Domain heuristic: map tags → domain category ─────────────────────
# The first matching tag wins. Order matters (most specific first).
_TAG_TO_DOMAIN = {
    "health": "health",
    "medical": "health",
    "clinical": "health",
    "career": "career",
    "jobs": "career",
    "finance": "finance",
    "money": "finance",
    "journal": "personal",
    "log": "personal",
    "personal": "personal",
    "relationships": "personal",
    "pkm": "meta",
    "meta": "meta",
    "maintenance": "meta",
    "projects": "projects",
    "engineering": "tech",
    "ai": "tech",
    "programming": "tech",
    "ml": "tech",
    "learning": "learning",
}


def parse_frontmatter(content: str) -> dict:
    """
    Extract YAML frontmatter from a markdown file.

    Returns a dict with:
        tags:    comma-separated string (ChromaDB can't store lists)
        type:    note type string (e.g. 'overview', 'journal', 'workshop')
        domain:  best-effort category derived from tags
    """
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {"tags": "", "type": "", "domain": ""}

    try:
        fm = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {"tags": "", "type": "", "domain": ""}

    if not isinstance(fm, dict):
        return {"tags": "", "type": "", "domain": ""}

    # Tags: normalize to comma-separated string
    raw_tags = fm.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split(",")]
    tags_str = ",".join(str(t) for t in raw_tags) if raw_tags else ""

    # Type
    note_type = str(fm.get("type", "")) if fm.get("type") else ""

    # Domain: first matching tag wins
    domain = ""
    for tag in (raw_tags or []):
        tag_lower = str(tag).lower()
        if tag_lower in _TAG_TO_DOMAIN:
            domain = _TAG_TO_DOMAIN[tag_lower]
            break

    return {"tags": tags_str, "type": note_type, "domain": domain}

def truncate_to_token_limit(text: str, max_tokens: int = MAX_TOKENS) -> str:
    """
    Trims text so it doesn't exceed the embedding API's token limit.
    """
    tokens = _TOKENIZER.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _TOKENIZER.decode(tokens[:max_tokens])

def split_by_headers(content: str, source_file: str) -> list[dict]:
    """
    Splits one markdown file into a list of chunks, one chunk per section.
    """
    # re.split with a lookahead doesn't consume the match, so headers stay in their chunks
    parts = re.split(r"(?=^#{1,3} )", content, flags=re.MULTILINE)

    chunks = []
    for part in parts:
        part = part.strip()

        # Skip near-empty chunks
        if not part or len(part) < 50:
            continue

        first_line = part.splitlines()[0].strip()
        section_name = re.sub(r"^#+\s*", "", first_line)

        chunks.append({
            "text": part,
            "source": source_file,
            "section": section_name or "Introduction",
        })

    # Fallback: if the file had no headers at all, index it as one big chunk
    if not chunks and content.strip():
        chunks.append({
            "text": content.strip(),
            "source": source_file,
            "section": "Full Note",
        })

    return chunks

def make_id(source: str, section: str, index: int) -> str:
    """
    Creates a stable, unique string ID for each chunk.
    """
    raw = f"{source}::{section}::{index}"
    return hashlib.md5(raw.encode()).hexdigest()
