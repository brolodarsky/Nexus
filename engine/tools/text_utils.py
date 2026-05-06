import re
import hashlib
import tiktoken
from core.constants import MAX_TOKENS

# cl100k_base is the tokenizer used by GPT-4 and text-embedding-3-small.
_TOKENIZER = tiktoken.get_encoding("cl100k_base")

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
