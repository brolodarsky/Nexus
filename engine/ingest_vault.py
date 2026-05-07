import sys
import traceback

# Force UTF-8 output
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.constants import VAULT_PATH
from agents.rag.constants import CHROMA_PATH
from agents.rag.tools.chroma_tool import get_or_create_collection
from tools.vault_walker import collect_markdown_files
from agents.rag.tools.text_utils import split_by_headers, truncate_to_token_limit, make_id, parse_frontmatter
from agents.rag.index_manifest import get_changed_files, save_manifest

def ingest(force: bool = False):
    """
    The main ingestion pipeline.

    Args:
        force: If True, re-embed all files regardless of modification time.
               If False (default), only re-embed files changed since last run.
    """
    print(f"[*] Scanning vault: {VAULT_PATH}")
    sys.stdout.flush()
    md_files = collect_markdown_files(VAULT_PATH)
    print(f"    Found {len(md_files)} markdown files.")
    sys.stdout.flush()

    # Incremental indexing: filter to only changed files
    if force:
        files_to_index = md_files
        new_manifest = {
            str(f.relative_to(VAULT_PATH)): f.stat().st_mtime for f in md_files
        }
        print(f"    --force: re-indexing all {len(files_to_index)} files.\n")
    else:
        files_to_index, new_manifest = get_changed_files(md_files, VAULT_PATH)
        skipped = len(md_files) - len(files_to_index)
        print(f"    {len(files_to_index)} changed, {skipped} unchanged (skipped).\n")
    sys.stdout.flush()

    try:
        print("[*] Connecting to ChromaDB...")
        sys.stdout.flush()
        collection = get_or_create_collection()
        print("[*] Connected successfully.")
        sys.stdout.flush()

        # ── Indexing ──────────────────────────────────────────────
        if not files_to_index:
            print("[*] No files changed since last index run. Skipping embedding.")
        else:
            total_chunks = 0
            for md_file in files_to_index:
                relative_path = str(md_file.relative_to(VAULT_PATH))
                content = md_file.read_text(encoding="utf-8", errors="ignore")

                # Extract frontmatter metadata (tags, type, domain)
                fm = parse_frontmatter(content)

                chunks = split_by_headers(content, relative_path)
                if not chunks:
                    continue

                ids = [make_id(relative_path, c["section"], i) for i, c in enumerate(chunks)]
                texts = [truncate_to_token_limit(c["text"]) for c in chunks]
                metadatas = [
                    {
                        "source": c["source"],
                        "section": c["section"],
                        "tags": fm["tags"],
                        "type": fm["type"],
                        "domain": fm["domain"],
                    }
                    for c in chunks
                ]

                collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
                print(f"    [+] {relative_path}  ({len(chunks)} chunks)")
                sys.stdout.flush()
                total_chunks += len(chunks)

            print(f"\n[DONE] {total_chunks} chunks indexed into ChromaDB at: {CHROMA_PATH}")

        # ── Orphan Cleanup ────────────────────────────────────────
        current_sources = {str(f.relative_to(VAULT_PATH)) for f in md_files}
        orphan_ids, orphan_sources = _find_orphans(collection, current_sources)

        if orphan_ids:
            collection.delete(ids=orphan_ids)
            # Also remove deleted files from the manifest
            for src in orphan_sources:
                new_manifest.pop(src, None)
            print(f"[CLEANUP] Removed {len(orphan_ids)} orphaned chunks from deleted/moved notes.")
        else:
            print("[CLEANUP] No orphaned entries found.")
        sys.stdout.flush()

        # Save manifest only after successful ingestion + cleanup
        save_manifest(new_manifest)
        print(f"[*] Index manifest saved.")

    except BaseException as e:
        print(f"\n[CRITICAL ERROR] Ingestion failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def _find_orphans(collection, current_sources: set[str]) -> tuple[list[str], set[str]]:
    """
    Query ChromaDB for all entries and return IDs + source paths
    whose 'source' metadata doesn't match any file currently on disk.
    """
    all_data = collection.get(include=["metadatas"])
    orphan_ids = []
    orphan_sources = set()
    for doc_id, meta in zip(all_data["ids"], all_data["metadatas"]):
        source = meta.get("source", "")
        if source not in current_sources:
            orphan_ids.append(doc_id)
            orphan_sources.add(source)
    return orphan_ids, orphan_sources


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    ingest(force=force_flag)
