import sys
import traceback

# Force UTF-8 output
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.constants import VAULT_PATH, CHROMA_PATH
from tools.chroma_tool import get_or_create_collection
from tools.vault_walker import collect_markdown_files
from tools.text_utils import split_by_headers, truncate_to_token_limit, make_id

def ingest(force: bool = False):
    """
    The main ingestion pipeline.
    """
    print(f"[*] Scanning vault: {VAULT_PATH}")
    sys.stdout.flush()
    md_files = collect_markdown_files(VAULT_PATH)
    print(f"    Found {len(md_files)} markdown files.\n")
    sys.stdout.flush()

    try:
        print("[*] Connecting to ChromaDB...")
        sys.stdout.flush()
        collection = get_or_create_collection()
        print("[*] Connected successfully.")
        sys.stdout.flush()

        total_chunks = 0
        for md_file in md_files:
            relative_path = str(md_file.relative_to(VAULT_PATH))
            content = md_file.read_text(encoding="utf-8", errors="ignore")

            chunks = split_by_headers(content, relative_path)
            if not chunks:
                continue

            ids = [make_id(relative_path, c["section"], i) for i, c in enumerate(chunks)]
            texts = [truncate_to_token_limit(c["text"]) for c in chunks]
            metadatas = [{"source": c["source"], "section": c["section"]} for c in chunks]

            collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
            print(f"    [+] {relative_path}  ({len(chunks)} chunks)")
            sys.stdout.flush()
            total_chunks += len(chunks)

        print(f"\n[DONE] {total_chunks} chunks indexed into ChromaDB at: {CHROMA_PATH}")
    except BaseException as e:
        print(f"\n[CRITICAL ERROR] Ingestion failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    ingest()
