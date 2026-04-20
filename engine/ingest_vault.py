import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace") # Force UTF-8 output to prevent "Invalid UTF-8" errors

"""
ingest_vault.py — Brain 2 Vault Indexer
========================================
This script is the MEMORY BUILDER for the RAG agent. It does NOT query or
answer anything. Its only job is to read your vault notes and convert them
into a format that a computer can search semantically — not by keywords, but
by *meaning*.

Think of it like this:
  - This script: Reads every book in a library and builds the card catalog.
  - ask_brain.py: Uses the card catalog to answer your questions.

You run this script ONCE to build the index, then re-run it whenever you add
significant new notes. ChromaDB uses "upsert", so it's safe to re-run — it
will update existing entries and add new ones without creating duplicates.

Usage:
    python engine/ingest_vault.py
"""

import os
import re
import hashlib
from pathlib import Path

# chromadb  — the local vector database that stores and searches our embeddings.
# Think of it like SQLite, but instead of searching by text match, it searches
# by mathematical similarity between vectors.
import chromadb
from chromadb.utils import embedding_functions

# python-dotenv — loads API keys from a .env file into os.environ so we don't
# have to hardcode secrets in our code.
from dotenv import load_dotenv

# tiktoken — OpenAI's tokenizer. A "token" is roughly a word or word-fragment.
# We use this to measure chunk size so we don't accidentally send a chunk that's
# too long to the embedding API (which has an 8192 token limit).
import tiktoken


# ── Config ───────────────────────────────────────────────────────────────────
# These are module-level constants — effectively, the "settings" for this script.
# Path() works like os.path but is cleaner. __file__ is the current script's path.

load_dotenv()  # Reads .env and sets OPENAI_API_KEY in the environment

# Path(__file__).parent.parent navigates up TWO folders from this script:
# From: Brain2/engine/ingest_vault.py
# To:   Brain2/
VAULT_PATH = Path(__file__).parent.parent / "Vault"
CHROMA_PATH = Path(__file__).parent.parent / ".chroma_db"
COLLECTION_NAME = "brain2_vault"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"


MAX_TOKENS = 8000  # OpenAI's embedding model allows up to 8192 tokens per input.
                   # We use 8000 to leave a small safety buffer.

# cl100k_base is the tokenizer used by GPT-4 and text-embedding-3-small.
# We load it once at module startup (it's slow to load) so it's reused.
_TOKENIZER = tiktoken.get_encoding("cl100k_base")

# Vault subdirectories we want to skip.
# Audio files, images, and Obsidian's own config folder aren't useful for text search.
IGNORE_DIRS = {
    "Audio",
    ".trash",
    ".obsidian",
    "Memories_Log_Images",
    "Pilot Diagrams",
}


# ── Chunking ─────────────────────────────────────────────────────────────────
# "Chunking" = splitting a large document into smaller, meaningful pieces.
#
# WHY CHUNK? Vector databases work best with focused, single-topic snippets.
# If you embed an entire 500-line note as one unit, the resulting vector is a
# "blurry average" of all the topics in that note. When you ask a specific
# question, the match quality is poor.
#
# WHY BY HEADERS? A markdown header (## Section Name) signals a topic boundary.
# Splitting there keeps each chunk thematically coherent.


def truncate_to_token_limit(text: str, max_tokens: int = MAX_TOKENS) -> str:
    """
    Trims text so it doesn't exceed the embedding API's token limit.

    How it works:
    1. Encode the text into a list of integers (tokens).
    2. If that list is short enough, return the original text unchanged.
    3. If it's too long, slice the token list and decode back to a string.

    Example:
        "The quick brown fox" → [791, 4062, 14198, 39935]  (4 tokens)
        truncate_to_token_limit(very_long_text, max_tokens=3)
        → "The quick brown"  (first 3 tokens decoded back to text)
    """
    tokens = _TOKENIZER.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _TOKENIZER.decode(tokens[:max_tokens])


def split_by_headers(content: str, source_file: str) -> list[dict]:
    """
    Splits one markdown file into a list of chunks, one chunk per section.

    The regex  r"(?=^#{1,3} )"  uses a "lookahead" to find the position
    BEFORE any line starting with #, ##, or ###. This means the header line
    itself stays attached to its section's content (not the previous section).

    Example input:
        "# My Note\nIntro text\n\n## Section A\nContent A\n\n## Section B\nContent B"

    Example output:
        [
            {"text": "# My Note\nIntro text", "source": "path/to/file.md", "section": "My Note"},
            {"text": "## Section A\nContent A", "source": "path/to/file.md", "section": "Section A"},
            {"text": "## Section B\nContent B", "source": "path/to/file.md", "section": "Section B"},
        ]

    For notes with no headers at all, we treat the entire file as one chunk.
    """
    # re.split with a lookahead doesn't consume the match, so headers stay in their chunks
    parts = re.split(r"(?=^#{1,3} )", content, flags=re.MULTILINE)

    chunks = []
    for part in parts:
        part = part.strip()

        # Skip near-empty chunks — not worth embedding noise or frontmatter-only sections
        if not part or len(part) < 50:
            continue

        # The first line of each chunk is the header (or the first sentence for header-less notes)
        first_line = part.splitlines()[0].strip()

        # Strip the leading #, ##, ### from the header to get a clean section name
        section_name = re.sub(r"^#+\s*", "", first_line)

        chunks.append({
            "text": part,
            "source": source_file,          # Relative path inside Vault/ — used for citations
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

    ChromaDB requires every stored item to have a unique string ID.
    We derive it from the file path + section name + position index so that:
    - Re-running this script on the same file produces the SAME IDs
      (this is what makes "upsert" work — it can find and update existing entries)
    - Two sections with the same name in the same file still get different IDs
      (the `index` parameter prevents collisions for repeated headers like "## Notes")

    MD5 is used purely for compactness — not for security. Collision risk is
    negligible given the input uniqueness.
    """
    raw = f"{source}::{section}::{index}"
    return hashlib.md5(raw.encode()).hexdigest()


# ── Ingestion ─────────────────────────────────────────────────────────────────

def collect_markdown_files(vault_path: Path) -> list[Path]:
    """
    Recursively finds all .md files in the vault, skipping ignored directories.

    vault_path.rglob("*.md") is a generator that walks the entire folder tree.
    We filter out any file whose path contains a directory in IGNORE_DIRS.
    """
    md_files = []
    for path in vault_path.rglob("*.md"):
        # path.parts gives a tuple of each folder and filename in the path
        # e.g. ('Vault', '2. Health', 'Audio', 'note.md') → skip because 'Audio' is in IGNORE_DIRS
        if any(ignored in path.parts for ignored in IGNORE_DIRS):
            continue
        md_files.append(path)
    return md_files


def ingest(force: bool = False):
    """
    The main ingestion pipeline. Orchestrates all the steps above.

    Step-by-step:
    1. Find all markdown files in Vault/
    2. Connect to (or create) the ChromaDB collection
    3. For each file:
       a. Read its content
       b. Split it into header-based chunks
       c. Truncate any chunk that's too long for the embedding API
       d. Give each chunk a stable unique ID
       e. Upsert (insert-or-update) into ChromaDB, letting it handle embedding
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not found. Check your .env file.")

    print(f"[*] Scanning vault: {VAULT_PATH}")
    md_files = collect_markdown_files(VAULT_PATH)
    print(f"    Found {len(md_files)} markdown files.\n")

    # PersistentClient saves the database to disk at CHROMA_PATH.
    # This folder is created automatically if it doesn't exist.
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    # The embedding function is what converts text → vectors.
    # We pass this to the collection so ChromaDB calls it automatically
    # when we upsert documents or query — we never call it manually.
    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=OPENAI_API_KEY,
        model_name=EMBEDDING_MODEL,
        # text-embedding-3-small produces 1536-dimensional vectors.
        # Each "dimension" is a number representing some learned semantic feature.
    )

    # get_or_create_collection: returns the collection if it exists, creates it if not.
    # hnsw:space=cosine means similarity is measured by the angle between vectors
    # (cosine similarity), not their raw distance. Better for text.
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )

    total_chunks = 0
    for md_file in md_files:
        # Read the file. errors="ignore" silently skips any undecodable bytes
        # (rare in markdown, but some notes may have odd characters).
        content = md_file.read_text(encoding="utf-8", errors="ignore")

        # relative_to() strips the absolute Vault/ prefix, giving us a clean
        # relative path like "2. Health\\Health Summary.md" for display + citations.
        relative_path = str(md_file.relative_to(VAULT_PATH))

        chunks = split_by_headers(content, relative_path)
        if not chunks:
            continue

        # Build the three parallel lists that ChromaDB's upsert() needs:
        #   ids        — unique key for each chunk (for upsert deduplication)
        #   texts      — the actual content to embed and store
        #   metadatas  — arbitrary key-value data stored alongside, returned on query
        ids = [make_id(relative_path, c["section"], i) for i, c in enumerate(chunks)]
        texts = [truncate_to_token_limit(c["text"]) for c in chunks]
        metadatas = [{"source": c["source"], "section": c["section"]} for c in chunks]

        # upsert = "insert or update". If an ID already exists, its stored
        # data is replaced. If it's new, a new entry is created.
        # ChromaDB calls the embed_fn on `texts` automatically here.
        collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
        total_chunks += len(chunks)
        print(f"    [+] {relative_path}  ({len(chunks)} chunks)")

    print(f"\n[DONE] {total_chunks} chunks indexed into ChromaDB at: {CHROMA_PATH}")


# ── Entry Point ───────────────────────────────────────────────────────────────
# The "if __name__ == '__main__'" guard means this block only runs when you
# execute the script directly (python engine/ingest_vault.py).
# If another script imported this file as a module, ingest() would NOT auto-run.

if __name__ == "__main__":
    ingest()
