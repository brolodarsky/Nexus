"""
vault_reader.py — Pure Python filesystem operations for Vault navigation and recent modification queries (`--today`, `--hours`, `--tree`, `--search`).
No LangChain @tool decorators here. These functions can be used by any agent, CLI call, or HTTP route.
"""
import argparse
from datetime import datetime, time, timedelta, timezone
import difflib
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from nexus.core.constants import IGNORE_DIRS, VAULT_PATH

def read_toc_content() -> str:
    """Reads the Table of Contents.md file to understand the folder structure of the Vault."""
    toc_path = VAULT_PATH / "Table of Contents.md"
    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading Table of Contents: {str(e)}"


def _resolve_vault_dir(rel_path: Optional[str]) -> Tuple[Optional[Path], Optional[str]]:
    """Resolves a folder path against VAULT_PATH, enforcing containment within VAULT_PATH.resolve().

    Rejects absolute paths, drive-letter paths, directory traversal escapes, and non-directories.
    Returns (resolved_dir_path, None) on success or (None, error_message) on failure.
    """
    resolved_vault = VAULT_PATH.resolve()
    if not rel_path:
        return resolved_vault, None

    clean = rel_path.strip()
    # Reject absolute and Windows drive-letter paths upfront before Path construction
    if (
        clean.startswith(("/", "\\"))
        or os.path.isabs(clean)
        or bool(re.match(r"^[a-zA-Z]:", clean))
        or Path(clean).is_absolute()
        or bool(Path(clean).drive)
    ):
        return None, f"Error: Refusing to access path outside the Vault: '{rel_path}'"

    # .resolve() collapses any '..' components and evaluates symlinks to their canonical target
    resolved_dir = (resolved_vault / clean).resolve()
    # is_relative_to guarantees resolved_dir is strictly inside the Vault root directory
    if not resolved_dir.is_relative_to(resolved_vault):
        return None, f"Error: Refusing to access path outside the Vault: '{rel_path}'"

    if not resolved_dir.exists() or not resolved_dir.is_dir():
        return (
            None,
            f"Error: Path '{rel_path}' does not exist or is not a directory. "
            f"Call with no arguments to see available folders.",
        )

    return resolved_dir, None


# Optional[str] / Optional[int] are union types (str | None, int | None) allowing callers to omit path/depth limits.
def get_directory_tree(
    path: Optional[str] = None,
    show_files: bool = False,
    max_depth: Optional[int] = None,
) -> str:
    """
    Returns an indented directory tree string.
    
    Args:
        path: Optional relative path from Vault root.
        show_files: If True, include files in the output.
        max_depth: Optional maximum folder depth to expand as separate lines; deeper child folders collapse inline.
    """
    start_path, err = _resolve_vault_dir(path)
    if err:
        return err

    lines: List[str] = []
    # Start recursive traversal at depth=1 (immediate children of start_path).
    _build_tree(
        start_path,
        lines,
        prefix="",
        show_files=show_files,
        max_depth=max_depth,
        current_depth=1,
    )

    if not lines:
        return f"No contents found at '{path or 'Vault root'}'."

    header = f"{path.strip()}/" if path else "Vault/"
    return header + "\n" + "\n".join(lines)


def _build_tree(
    directory: Path,
    lines: list,
    prefix: str,
    show_files: bool,
    max_depth: Optional[int] = None,
    current_depth: int = 1,
):
    """Recursively build an indented tree representation of a directory."""
    try:
        # Sort directory entries alphabetically by filename (case-sensitive) for deterministic prompt caching.
        entries = sorted(directory.iterdir(), key=lambda e: e.name)
    except PermissionError:
        # Ignore OS-protected folders rather than crashing the entire tree traversal.
        return

    resolved_vault = VAULT_PATH.resolve()
    # List comprehensions filter entries into directories (excluding IGNORE_DIRS and symlinks escaping the Vault) and files.
    dirs = [
        e for e in entries
        if e.is_dir()
        and e.name not in IGNORE_DIRS
        and e.resolve().is_relative_to(resolved_vault)
    ]
    files = [
        e for e in entries
        if e.is_file()
        and e.resolve().is_relative_to(resolved_vault)
    ] if show_files else []

    for d in dirs:
        # When max_depth is reached, collapse immediate child folders inline (e.g. `dir/ [sub1, sub2]`) to save vertical lines.
        if max_depth is not None and current_depth >= max_depth:
            try:
                sub_dirs = sorted(
                    e.name for e in d.iterdir()
                    if e.is_dir()
                    and e.name not in IGNORE_DIRS
                    and e.resolve().is_relative_to(resolved_vault)
                )
            except PermissionError:
                sub_dirs = []
            inline_suffix = f" [{', '.join(sub_dirs)}]" if sub_dirs else ""
            lines.append(f"{prefix}  {d.name}/{inline_suffix}")
        else:
            lines.append(f"{prefix}  {d.name}/")
            _build_tree(
                d,
                lines,
                prefix=prefix + "  ",
                show_files=show_files,
                max_depth=max_depth,
                current_depth=current_depth + 1,
            )

    for f in files:
        lines.append(f"{prefix}  {f.name}")


def _parse_frontmatter_tags(content: str) -> list:
    """Extract tags from YAML frontmatter using lightweight regex parsing."""
    fm_match = re.match(r'^---\s*\r?\n(.*?)\r?\n---', content, re.DOTALL)
    if not fm_match:
        return []

    frontmatter = fm_match.group(1)

    # Try inline style: tags: [tag1, tag2]
    inline_match = re.search(r'tags:\s*\[([^\]]*)\]', frontmatter)
    if inline_match:
        raw = inline_match.group(1)
        return [t.strip().strip('"').strip("'") for t in raw.split(',') if t.strip()]

    # Try list style: tags:\n  - tag1\n  - tag2
    list_match = re.search(r'tags:\s*\r?\n((?:\s+-\s+.*\r?\n?)+)', frontmatter)
    if list_match:
        raw_lines = list_match.group(1).strip().splitlines()
        tags = []
        for line in raw_lines:
            line = line.strip()
            if line.startswith('- '):
                tags.append(line[2:].strip().strip('"').strip("'"))
        return tags

    return []


# Optional[int] (int | None) allows callers to optionally slice a specific 1-indexed line range (start_line..end_line) for large files.
# Optional[int] for start_page/end_page allows document callers to inspect specific page slices of multi-page PDF documents.
def _read_pdf_content(
    pdf_path: Path,
    rel_path: Path,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    """Reads and extracts text, structured tables, and layout-aware content from a PDF document.

    Utilizes PyMuPDF (`pymupdf`) to extract text with columnar block sorting and convert detected
    tabular regions directly into GitHub Flavored Markdown tables (`tab.to_markdown()`).
    Flags scanned/image-only pages where text density is near zero so agents recognize image documents.

    Args:
        pdf_path: Absolute resolved Path to the target PDF file on disk.
        rel_path: Vault-relative Path for header display.
        start_page: Optional 1-indexed starting page number (inclusive).
        end_page: Optional 1-indexed ending page number (inclusive).
        start_line: Optional 1-indexed starting line number of the assembled text (inclusive).
        end_line: Optional 1-indexed ending line number of the assembled text (inclusive).
    """
    try:
        import pymupdf
    except ImportError:
        return f"Error reading PDF {rel_path}: 'pymupdf' package is not installed."

    try:
        # Open PDF document handle using PyMuPDF context manager for deterministic resource disposal
        with pymupdf.open(pdf_path) as doc:
            total_pages = len(doc)
            if total_pages == 0:
                return f"--- File: {rel_path} (Empty PDF document, 0 pages) ---"

            s_page = max(1, start_page) if start_page and start_page > 0 else 1
            e_page = min(total_pages, end_page) if end_page and end_page > 0 else total_pages

            if s_page > total_pages:
                return (
                    f"Error: Requested start_page ({s_page}) exceeds total document pages "
                    f"({total_pages}) in '{rel_path}'."
                )

            extracted_sections: List[str] = []

            # Iterate 0-indexed page indices within requested [s_page-1, e_page) bounds
            for page_idx in range(s_page - 1, e_page):
                # Assign to persistent local variable to avoid weakref garbage collection during table analysis
                page = doc[page_idx]
                page_num = page_idx + 1

                # 1. Detect tabular structures via PyMuPDF native table recognition
                # CRITICAL RESILIENCE DIRECTIVE (`use_layout=False`):
                # PyMuPDF 2.1's native C++ layout analyzer (invoked by default via `page.get_layout()` when `use_layout=True`)
                # contains an uncatchable access violation / NULL pointer dereference bug (SEH 0xc0000005) in `mupdfcpp64.dll`
                # on specific PDF drawing vector streams or receipt fonts (e.g., student loan or banking payment receipts).
                # Because native C++ segfaults bypass Python exception handling and terminate the entire process,
                # passing `use_layout=False` restricts detection to line/edge-based vector analysis, which is memory-safe,
                # fast, and prevents catastrophic crashes of the backend server worker.
                table_entries: List[Tuple[Tuple[float, float, float, float], str]] = []
                try:
                    tabs = page.find_tables(use_layout=False)
                    if tabs and tabs.tables:
                        for tab in tabs:
                            try:
                                md_tab = tab.to_markdown()
                                if md_tab and md_tab.strip():
                                    table_entries.append((tab.bbox, md_tab.strip()))
                            except Exception:
                                pass
                except Exception:
                    pass

                # 2. Extract layout-aware text blocks sorted top-to-bottom, column-by-column
                # Each block tuple: (x0, y0, x1, y1, text, block_no, block_type) where block_type == 0 is text
                page_items: List[Tuple[float, str]] = []
                try:
                    blocks = page.get_text("blocks", sort=True)
                except Exception:
                    blocks = []

                for b in blocks:
                    # Filter for text blocks (block_type 0) with non-whitespace content
                    is_text_block = b[6] == 0 if len(b) > 6 else True
                    if len(b) >= 5 and is_text_block:
                        block_text = b[4].strip()
                        if not block_text:
                            continue

                        # Check if this text block intersects any detected table bounding box
                        block_rect = pymupdf.Rect(b[:4])
                        intersects_table = any(
                            block_rect.intersects(pymupdf.Rect(t_bbox))
                            for t_bbox, _ in table_entries
                        )
                        # Exclude duplicate text that is already captured inside a markdown table
                        if not intersects_table:
                            # Use vertical coordinate y0 (b[1]) for natural page reading sequence
                            page_items.append((b[1], block_text))

                # Inject detected markdown tables positioned by their top boundary (bbox y0)
                for t_bbox, t_markdown in table_entries:
                    page_items.append((t_bbox[1], t_markdown))

                # Sort combined text blocks and markdown tables in chronological reading order
                page_items.sort(key=lambda item: item[0])
                page_text = "\n\n".join(item[1] for item in page_items if item[1])

                # 3. Detect scanned / image-only pages (< 50 chars of extractable text)
                if len(page_text.strip()) < 50:
                    try:
                        images = page.get_images()
                        img_count = len(images)
                    except Exception:
                        img_count = 0

                    if img_count > 0:
                        page_text = (
                            f"[Page {page_num}: Scanned or image document ({img_count} embedded image(s), "
                            f"low text layer density). Use chat upload for multimodal vision inspection.]\n"
                            + (f"\n{page_text}" if page_text.strip() else "")
                        )

                extracted_sections.append(
                    f"--- Page {page_num} of {total_pages} ---\n\n{page_text if page_text.strip() else '[No text on page]'}"
                )

            full_extracted = "\n\n".join(extracted_sections)

            # Optional line slicing on the final assembled text
            if start_line is not None or end_line is not None:
                lines = full_extracted.splitlines()
                total_lines = len(lines)
                s_idx = max(0, (start_line - 1) if start_line and start_line > 0 else 0)
                e_idx = min(total_lines, end_line if end_line is not None else total_lines)
                sliced_body = "\n".join(lines[s_idx:e_idx])
                return (
                    f"--- File: {rel_path} (pages {s_page}-{e_page} of {total_pages}, "
                    f"lines {s_idx + 1}-{e_idx} of {total_lines}) ---\n\n{sliced_body}"
                )

            return f"--- File: {rel_path} (pages {s_page}-{e_page} of {total_pages}) ---\n\n{full_extracted}"
    except Exception as exc:
        return f"Error reading PDF file {rel_path}: {str(exc)}"


def read_note_content(
    note_path: str,
    domain_path: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
) -> str:
    """Reads the contents of a specific note or file in the Vault (supports Markdown, text, and PDF documents).
    
    Args:
        note_path: The file name or relative path.
        domain_path: Optional path relative to Vault to restrict search and resolution.
        start_line: Optional 1-indexed starting line number (inclusive).
        end_line: Optional 1-indexed ending line number (inclusive).
        start_page: Optional 1-indexed starting page for PDF documents (inclusive).
        end_page: Optional 1-indexed ending page for PDF documents (inclusive).
    """
    resolved_path, err = resolve_vault_note_path(note_path, domain_path=domain_path)
    if err:
        return err

    try:
        try:
            rel_path = resolved_path.relative_to(VAULT_PATH.resolve())
        except ValueError:
            rel_path = resolved_path

        # Check if target is a binary PDF document
        if resolved_path.suffix.lower() == ".pdf":
            return _read_pdf_content(
                resolved_path,
                rel_path=rel_path,
                start_page=start_page,
                end_page=end_page,
                start_line=start_line,
                end_line=end_line,
            )

        content = resolved_path.read_text(encoding="utf-8")

        # If line bounds are specified, slice the lines array (converting 1-indexed to 0-indexed Python slices)
        if start_line is not None or end_line is not None:
            all_lines = content.splitlines()
            total_lines = len(all_lines)
            s_idx = max(0, (start_line - 1) if start_line and start_line > 0 else 0)
            e_idx = min(total_lines, end_line if end_line is not None else total_lines)
            selected = "\n".join(all_lines[s_idx:e_idx])
            return f"--- File: {rel_path} (lines {s_idx + 1}-{e_idx} of {total_lines}) ---\n\n{selected}"

        return f"--- File: {rel_path} ---\n\n" + content
    except Exception as e:
        return f"Error reading file {note_path}: {str(e)}"


# Tuple[Optional[Path], Optional[str]] returns (resolved_path, None) on success or (None, error_message) on failure.
def resolve_vault_note_path(note_path: str, domain_path: Optional[str] = None) -> Tuple[Optional[Path], Optional[str]]:
    """Deterministically resolves a note path or filename to an exact Path inside VAULT_PATH.

    Supports exact relative paths (e.g. '3. Operations/3.1. Career Strategy & Revenue/Job Hunt War Room.md'),
    paths omitting '.md', or unique base filenames (e.g. 'Job Hunt War Room').
    Enforces strict containment within VAULT_PATH (or the domain directory if domain_path is provided).
    """
    if not note_path or not note_path.strip():
        return None, "Error: Path cannot be empty."

    clean_input = note_path.strip()
    # Reject absolute and Windows drive-letter paths upfront (e.g., 'C:\\Windows\\win.ini', '/etc/passwd', '\\boot.ini')
    if (
        clean_input.startswith(("/", "\\"))
        or os.path.isabs(clean_input)
        or bool(re.match(r"^[a-zA-Z]:", clean_input))
        or Path(clean_input).is_absolute()
        or bool(Path(clean_input).drive)
    ):
        return None, f"Error: Refusing to access path outside the Vault: '{note_path}'"

    # If clean_input begins with 'Vault/' or 'Vault\\', strip the redundant prefix for resolution
    norm_input = clean_input
    if norm_input.replace("\\", "/").startswith("Vault/"):
        norm_input = norm_input[6:]

    resolved_vault = VAULT_PATH.resolve()

    if domain_path:
        clean_domain = domain_path.strip()
        if (
            clean_domain.startswith(("/", "\\"))
            or os.path.isabs(clean_domain)
            or bool(re.match(r"^[a-zA-Z]:", clean_domain))
            or Path(clean_domain).is_absolute()
            or bool(Path(clean_domain).drive)
        ):
            return None, f"Error: Refusing to access path outside the Vault: '{domain_path}'"
        resolved_domain = (resolved_vault / clean_domain.lstrip("/\\")).resolve()
        if not resolved_domain.is_relative_to(resolved_vault):
            return None, f"Error: Refusing to access path outside the Vault: '{domain_path}'"
        search_root = resolved_domain
        resolved_root = resolved_domain
    else:
        search_root = resolved_vault
        resolved_root = resolved_vault

    # Candidate 1: Direct path relative to search_root
    target_path = search_root / norm_input
    # .resolve() collapses '..' segments and follows symlinks to their canonical target on disk
    resolved_target = target_path.resolve()
    # Path.is_relative_to (Python 3.9+): True only if resolved_target is within resolved_root
    if not resolved_target.is_relative_to(resolved_root):
        err_msg = (
            f"Error: Cannot read {note_path}. Restricted to the {domain_path} domain."
            if domain_path
            else f"Error: Refusing to access path outside the Vault: '{note_path}'"
        )
        return None, err_msg

    if resolved_target.exists() and resolved_target.is_file():
        return resolved_target, None

    # Candidate 2: Try appending '.md' if not already present
    if not norm_input.endswith(".md"):
        target_md = search_root / f"{norm_input}.md"
        resolved_md = target_md.resolve()
        if not resolved_md.is_relative_to(resolved_root):
            err_msg = (
                f"Error: Cannot read {note_path}. Restricted to the {domain_path} domain."
                if domain_path
                else f"Error: Refusing to access path outside the Vault: '{note_path}'"
            )
            return None, err_msg
        if resolved_md.exists() and resolved_md.is_file():
            return resolved_md, None

    # Candidate 3: If domain_path is set, caller might have passed a full vault-relative path
    if domain_path:
        vault_target = (resolved_vault / norm_input).resolve()
        if vault_target.is_relative_to(resolved_root) and vault_target.exists() and vault_target.is_file():
            return vault_target, None
        if not norm_input.endswith(".md"):
            vault_target_md = (resolved_vault / f"{norm_input}.md").resolve()
            if vault_target_md.is_relative_to(resolved_root) and vault_target_md.exists() and vault_target_md.is_file():
                return vault_target_md, None

    # Fallback: search by base filename across search_root
    base_name = os.path.basename(norm_input)
    if not base_name.endswith(".md"):
        base_name += ".md"

    found_paths: List[Path] = []
    for root, dirs, files in os.walk(search_root):
        dirs[:] = [
            d for d in dirs
            if d not in IGNORE_DIRS
            and (Path(root) / d).resolve().is_relative_to(resolved_root)
        ]
        for file in files:
            if file == base_name or file == os.path.basename(norm_input):
                candidate_file = (Path(root) / file).resolve()
                if candidate_file.is_relative_to(resolved_root) and candidate_file.is_file():
                    found_paths.append(candidate_file)

    if not found_paths:
        scope = f" in {domain_path}" if domain_path else ""
        return None, f"File not found{scope}: {note_path}. Try using search to find the correct path."
    elif len(found_paths) == 1:
        resolved_match = found_paths[0].resolve()
        if not resolved_match.is_relative_to(resolved_root):
            return None, f"Error: Refusing to access path outside the Vault: '{note_path}'"
        return resolved_match, None
    else:
        rel_paths = [str(p.relative_to(resolved_vault)).replace("\\", "/") for p in found_paths]
        scope = f" in {domain_path}" if domain_path else ""
        return None, f"Multiple files found for {note_path}{scope}. Please be more specific. Matches:\n" + "\n".join(rel_paths)


def _parse_frontmatter_aliases(content: str) -> List[str]:
    """Extract note aliases from YAML frontmatter (`aliases: [A, B]` or `aliases:\\n  - A`) for wiki-link resolution."""
    fm_match = re.match(r'^---\s*\r?\n(.*?)\r?\n---', content, re.DOTALL)
    if not fm_match:
        return []

    frontmatter = fm_match.group(1)
    # Inline YAML array syntax: aliases: [Alias One, Alias Two]
    inline_match = re.search(r'^aliases:\s*\[([^\]]*)\]', frontmatter, re.MULTILINE)
    if inline_match:
        return [a.strip().strip('"').strip("'") for a in inline_match.group(1).split(',') if a.strip()]

    # Multi-line YAML bullet list syntax: aliases:\n  - Alias One
    list_match = re.search(r'^aliases:\s*\r?\n((?:\s+-\s+.*\r?\n?)+)', frontmatter, re.MULTILINE)
    if list_match:
        aliases: List[str] = []
        for line in list_match.group(1).strip().splitlines():
            stripped = line.strip()
            if stripped.startswith('- '):
                val = stripped[2:].strip().strip('"').strip("'")
                if val:
                    aliases.append(val)
        return aliases
    return []


# -> Dict[str, Any] returns normalized lookup sets/lists built from a single Vault walk for fast path/wiki-link verification.
def _build_vault_file_index() -> Dict[str, Any]:
    """Builds an in-memory index of all Vault relative paths, basenames, stems, and YAML frontmatter aliases."""
    resolved_vault = VAULT_PATH.resolve()
    rel_paths: List[str] = []
    rel_paths_lower: Set[str] = set()
    rel_stems_lower: Set[str] = set()
    basenames: List[str] = []
    basenames_lower: Set[str] = set()
    stems_lower: Set[str] = set()
    aliases_lower: Set[str] = set()

    if not resolved_vault.exists():
        return {
            "rel_paths": rel_paths,
            "rel_paths_lower": rel_paths_lower,
            "rel_stems_lower": rel_stems_lower,
            "basenames": basenames,
            "basenames_lower": basenames_lower,
            "stems_lower": stems_lower,
            "aliases_lower": aliases_lower,
        }

    for root, dirs, files in os.walk(resolved_vault):
        # Prune ignored/non-Vault directories in-place so os.walk skips .git, .obsidian, etc.
        dirs[:] = [
            d for d in dirs
            if d not in IGNORE_DIRS
            and (Path(root) / d).resolve().is_relative_to(resolved_vault)
        ]
        for file in files:
            if file.startswith("."):
                continue
            filepath = (Path(root) / file).resolve()
            if not filepath.is_relative_to(resolved_vault):
                continue

            rel_str = str(filepath.relative_to(resolved_vault)).replace("\\", "/")
            rel_low = rel_str.lower()
            base_low = file.lower()
            rel_paths.append(rel_str)
            rel_paths_lower.add(rel_low)
            basenames.append(file)
            basenames_lower.add(base_low)

            if base_low.endswith(".md"):
                stems_lower.add(base_low[:-3])
                rel_stems_lower.add(rel_low[:-3])
                # Read only the leading 4 KB head to extract YAML frontmatter aliases without loading large note bodies.
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        head = f.read(4096)
                    for alias in _parse_frontmatter_aliases(head):
                        aliases_lower.add(alias.lower())
                except OSError:
                    pass

    return {
        "rel_paths": sorted(rel_paths),
        "rel_paths_lower": rel_paths_lower,
        "rel_stems_lower": rel_stems_lower,
        "basenames": sorted(set(basenames)),
        "basenames_lower": basenames_lower,
        "stems_lower": stems_lower,
        "aliases_lower": aliases_lower,
    }


# `note_path: str` is an unresolved Vault path or filename; `max_matches: int` caps fuzzy fallback suggestions.
# -> Dict[str, Any] returns nearest existing parent directory listing + closest matching filenames on disk.
def find_nearest_directory_and_matches(note_path: str, max_matches: int = 8) -> Dict[str, Any]:
    """Finds the nearest existing Vault parent directory listing and similar filenames for a missing path."""
    if not note_path or not note_path.strip():
        return {"nearest_dir": None, "directory_listing": None, "similar_files": []}

    clean = note_path.strip().replace("\\", "/")
    if (
        clean.startswith("/")
        or os.path.isabs(clean)
        or bool(re.match(r"^[a-zA-Z]:", clean))
        or Path(clean).is_absolute()
        or bool(Path(clean).drive)
    ):
        return {"nearest_dir": None, "directory_listing": None, "similar_files": []}

    if clean.startswith("Vault/"):
        clean = clean[6:]
    clean = clean.lstrip("/")

    resolved_vault = VAULT_PATH.resolve()
    candidate = (resolved_vault / clean).resolve()
    if not candidate.is_relative_to(resolved_vault):
        return {"nearest_dir": None, "directory_listing": None, "similar_files": []}

    # Walk upward from the target's parent until we hit an existing directory inside the Vault.
    nearest_dir: Optional[Path] = None
    probe = candidate.parent
    while probe != resolved_vault and probe.is_relative_to(resolved_vault):
        if probe.exists() and probe.is_dir():
            nearest_dir = probe
            break
        probe = probe.parent

    nearest_rel: Optional[str] = None
    directory_listing: Optional[str] = None
    if nearest_dir is not None and nearest_dir != resolved_vault:
        nearest_rel = str(nearest_dir.relative_to(resolved_vault)).replace("\\", "/")
        raw_tree = get_directory_tree(path=nearest_rel, show_files=True, max_depth=2)
        tree_lines = raw_tree.splitlines()
        if len(tree_lines) > 40:
            directory_listing = "\n".join(tree_lines[:40]) + f"\n... ({len(tree_lines) - 40} more entries omitted)"
        else:
            directory_listing = raw_tree

    # Rank Vault files by token overlap + difflib similarity against the requested filename stem.
    index = _build_vault_file_index()
    req_base = os.path.basename(clean)
    req_stem = req_base[:-3] if req_base.lower().endswith(".md") else os.path.splitext(req_base)[0]
    req_tokens = {t for t in re.split(r"[^a-z0-9]+", req_stem.lower()) if len(t) >= 2}

    scored: List[Tuple[float, str]] = []
    for rel_p in index["rel_paths"]:
        cand_base = os.path.basename(rel_p)
        cand_stem = cand_base[:-3] if cand_base.lower().endswith(".md") else os.path.splitext(cand_base)[0]
        cand_tokens = {t for t in re.split(r"[^a-z0-9]+", cand_stem.lower()) if len(t) >= 2}
        overlap = len(req_tokens & cand_tokens)
        seq_ratio = difflib.SequenceMatcher(None, req_stem.lower(), cand_stem.lower()).ratio()
        if overlap > 0 or seq_ratio >= 0.45:
            # Weight token overlap strongly so shared domain words (e.g. "Resume") surface canonical notes first.
            scored.append((overlap * 2.0 + seq_ratio, rel_p))

    scored.sort(key=lambda item: (-item[0], item[1]))
    similar_files = [item[1] for item in scored[:max_matches]]

    return {
        "nearest_dir": nearest_rel,
        "directory_listing": directory_listing,
        "similar_files": similar_files,
    }


_TEMPLATE_HINT_CHARS = set("*?<>{}")
_PROSE_LEAD_WORDS_RE = re.compile(
    r"^(?:use|read|see|check|open|edit|update|create|write|inspect|review|hydrate|"
    r"compare|using|via|from|with|and|or|to|in|for|on|at|into|against|including|"
    r"between|both|plus|then)\s+",
    re.IGNORECASE,
)


# `context_brief: str` is the Markdown handoff text passed to `spawn_conversation`.
# -> List[str] returns deduplicated broken `[[Wiki-Links]]` or `.md`/`.pdf`/`.docx` references not found on disk.
def verify_context_brief_paths(context_brief: str) -> List[str]:
    """Scans a conversation context brief for `[[Wiki-Links]]` and `.md`/`.pdf`/`.docx` paths absent from the Vault."""
    if not context_brief or not context_brief.strip():
        return []

    index = _build_vault_file_index()
    # Include explicit "Vault/<rel_path>" forms alongside "<rel_path>" and basenames, longest-first,
    # so wrong-folder paths like "2. Health/Resume - Master.md" never falsely match bare basenames after '/'.
    known_variants = (
        set(index["rel_paths"])
        | {f"Vault/{p}" for p in index["rel_paths"]}
        | set(index["basenames"])
    )
    known_suffixes = sorted(known_variants, key=len, reverse=True)
    known_suffixes_lower = [s.lower() for s in known_suffixes]

    def _should_ignore(raw: str) -> bool:
        val = raw.strip()
        if not val or val.startswith(("#", "http://", "https://", "mailto:", "file://")):
            return True
        if any(ch in _TEMPLATE_HINT_CHARS for ch in val):
            return True
        if "YYYY-MM-DD" in val or val.lower() in (".md", ".pdf", ".docx"):
            return True
        return False

    def _is_valid_ref(raw: str, allow_stem_or_alias: bool) -> bool:
        norm = raw.strip().strip("`\"'").replace("\\", "/").lstrip("./")
        if norm.startswith("Vault/"):
            norm = norm[6:]
        low = norm.lower()
        if "/" in low:
            if low in index["rel_paths_lower"]:
                return True
            return allow_stem_or_alias and (low in index["rel_stems_lower"])
        if low in index["basenames_lower"]:
            return True
        return allow_stem_or_alias and (low in index["stems_lower"] or low in index["aliases_lower"])

    missing: List[str] = []
    seen_missing_lower: Set[str] = set()

    def _record_missing(candidate: str) -> None:
        cleaned = candidate.strip().strip("`\"'")
        key = cleaned.lower()
        if cleaned and key not in seen_missing_lower:
            seen_missing_lower.add(key)
            missing.append(cleaned)

    # Mask URLs upfront so external web links ending in .md/.pdf/.docx are never treated as Vault filenames.
    scan_text = re.sub(r"https?://[^\s)\]>]+", lambda m: " " * len(m.group(0)), context_brief)

    # 1. Scan Obsidian [[Wiki-Links]] (stripping |Display Alias and #Heading Anchor)
    def _scan_wikilink(match: re.Match) -> str:
        inner = match.group(1)
        target = inner.split("|", 1)[0].split("#", 1)[0].strip()
        if not _should_ignore(target) and not _is_valid_ref(target, allow_stem_or_alias=True):
            _record_missing(target)
        return " " * len(match.group(0))

    scan_text = re.sub(r"\[\[([^\[\]\n]+?)\]\]", _scan_wikilink, scan_text)

    # 2. Scan Markdown links [label](target.ext)
    def _scan_md_link(match: re.Match) -> str:
        target = match.group(1).strip()
        if not _should_ignore(target) and not _is_valid_ref(target, allow_stem_or_alias=False):
            _record_missing(target)
        return " " * len(match.group(0))

    scan_text = re.sub(r"\[[^\]\n]*\]\(([^)\n]+?\.(?:md|pdf|docx))\)", _scan_md_link, scan_text, flags=re.IGNORECASE)

    # 3. Scan inline-code backticked references `path/to/file.ext`
    def _scan_backtick(match: re.Match) -> str:
        target = match.group(1).strip()
        if not _should_ignore(target) and not _is_valid_ref(target, allow_stem_or_alias=False):
            _record_missing(target)
        return " " * len(match.group(0))

    scan_text = re.sub(r"`([^`\n]+?\.(?:md|pdf|docx))`", _scan_backtick, scan_text, flags=re.IGNORECASE)

    # 4. Scan remaining unquoted prose lines for `.md` / `.pdf` / `.docx` filename references
    ext_re = re.compile(r"\.(?:md|pdf|docx)(?=$|[^A-Za-z0-9_])", re.IGNORECASE)
    hard_delim_re = re.compile(r'[\[\]()`"\'*;|\n<>]')
    prose_sep_re = re.compile(r"(?:^|[:;,]\s+)")

    for line in scan_text.splitlines():
        for ext_match in ext_re.finditer(line):
            prefix = line[: ext_match.end()]
            prefix_low = prefix.lower()

            # Fast path: if a known real Vault file ends right at this extension on a non-slash boundary, it exists on disk.
            matched_known = False
            for known_low in known_suffixes_lower:
                if prefix_low.endswith(known_low):
                    boundary_idx = len(prefix_low) - len(known_low)
                    if boundary_idx == 0 or prefix_low[boundary_idx - 1] in " \t:;,(\"'*":
                        matched_known = True
                        break
            if matched_known:
                continue

            # Extract the candidate filename/path backward up to the nearest punctuation/markdown delimiter.
            delim_matches = list(hard_delim_re.finditer(prefix))
            start_idx = delim_matches[-1].end() if delim_matches else 0
            cand = prefix[start_idx:]

            sep_matches = list(prose_sep_re.finditer(cand))
            if sep_matches:
                cand = cand[sep_matches[-1].end() :]

            cand = cand.lstrip(" -•\t")
            # Strip leading prose verbs/prepositions (e.g. "Use Resume - Fake.md" -> "Resume - Fake.md").
            while True:
                stripped_cand = _PROSE_LEAD_WORDS_RE.sub("", cand)
                if stripped_cand == cand:
                    break
                cand = stripped_cand

            cand = cand.strip()
            if not _should_ignore(cand) and not _is_valid_ref(cand, allow_stem_or_alias=False):
                _record_missing(cand)

    return missing


def search_within(keyword: str, root_path: Optional[str] = None, tags: Optional[List[str]] = None) -> str:
    """Searches notes in the vault for a keyword string."""
    search_root, err = _resolve_vault_dir(root_path)
    if err:
        return err

    resolved_vault = VAULT_PATH.resolve()
    results = []
    keyword_lower = keyword.lower()
    tags_lower = {t.lower() for t in tags} if tags else None
    
    for root, dirs, files in os.walk(search_root):
        dirs[:] = [
            d for d in dirs
            if d not in IGNORE_DIRS
            and (Path(root) / d).resolve().is_relative_to(resolved_vault)
        ]
        
        for file in files:
            if not file.endswith('.md'):
                continue
                
            filepath = (Path(root) / file).resolve()
            if not filepath.is_relative_to(resolved_vault):
                continue

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                if tags_lower:
                    note_tags = _parse_frontmatter_tags(content)
                    note_tags_lower = {t.lower() for t in note_tags}
                    if not tags_lower.intersection(note_tags_lower):
                        continue

                if keyword_lower in content.lower():
                    idx = content.lower().find(keyword_lower)
                    start = max(0, idx - 40)
                    end = min(len(content), idx + len(keyword) + 40)
                    snippet = content[start:end].replace('\n', ' ')
                    
                    rel_path = filepath.relative_to(resolved_vault)
                    results.append(f"- {rel_path}: \"...{snippet}...\"")
            except Exception:
                pass
                
    if not results:
        scope = f"in '{root_path}'" if root_path else "across the entire vault"
        tag_info = f" (filtered by tags: {', '.join(tags)})" if tags else ""
        return f"No results found for keyword: '{keyword}' {scope}{tag_info}."
        
    scope = f"in '{root_path}'" if root_path else "across the entire vault"
    output = f"Found '{keyword}' in {len(results)} files {scope}:\n"
    for r in results[:20]:
        output += f"{r}\n"
    if len(results) > 20:
        output += f"...and {len(results)-20} more files."
        
    return output


# Signature: `(raw_path: Optional[str]) -> str` strips any leading `Vault/` prefix and normalizes slashes for rel-path matching.
def _normalize_hitl_rel_path(raw_path: Optional[str]) -> str:
    clean = (raw_path or "").strip().replace("\\", "/").lstrip("/")
    if clean.startswith("Vault/"):
        return clean[len("Vault/"):]
    return clean


# Signature: `(cutoff_ts: float) -> Set[str]` queries `hitl.db` revisions to identify notes that pre-existed `cutoff_ts`.
def _find_preexisting_files_from_hitl(cutoff_ts: float) -> Set[str]:
    """Cross-checks the HITL `revisions` ledger so notes edited in-window are never misbadged as `[NEW]`.

    Older Windows commits via `os.replace` clobbered NTFS `CreationTime` (`st_ctime`) on existing notes;
    walking committed non-rolled-back revisions (`rolled_back = 0`) recovers ground-truth prior existence.
    """
    try:
        from nexus.core import hitl_queue
        db_path = Path(hitl_queue.DB_PATH)
    except Exception:
        db_path = Path(__file__).resolve().parent.parent / "hitl.db"

    if not db_path.exists():
        return set()

    # SQLite `CURRENT_TIMESTAMP` stores UTC `YYYY-MM-DD HH:MM:SS` strings; convert `cutoff_ts` to match lexicographically.
    cutoff_utc_str = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    preexisting: Set[str] = set()
    first_seen_in_window: Set[str] = set()
    conn: Optional[sqlite3.Connection] = None

    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT REPLACE(target_file, '\\', '/') AS src_file,
                   REPLACE(destination_file, '\\', '/') AS dst_file,
                   prior_content IS NOT NULL AS had_prior,
                   applied_content = '' AS is_delete,
                   created_at
            FROM revisions
            WHERE rolled_back = 0
            ORDER BY id ASC
            """
        )
        for src_raw, dst_raw, had_prior, is_delete, created_at in cursor.fetchall():
            src_rel = _normalize_hitl_rel_path(src_raw)
            dst_rel = _normalize_hitl_rel_path(dst_raw) if dst_raw else ""
            created_str = str(created_at or "")

            if created_str < cutoff_utc_str:
                # Reconstruct which files already existed before the requested time window began.
                if dst_rel:
                    preexisting.discard(src_rel)
                    preexisting.add(dst_rel)
                elif is_delete:
                    preexisting.discard(src_rel)
                elif src_rel:
                    preexisting.add(src_rel)
            else:
                # Within the window, only the first revision on a path settles whether it already existed (`had_prior`).
                eff_rel = dst_rel if dst_rel else src_rel
                if eff_rel and eff_rel not in first_seen_in_window:
                    first_seen_in_window.add(eff_rel)
                    if had_prior:
                        preexisting.add(eff_rel)
    except sqlite3.Error:
        return set()
    finally:
        if conn is not None:
            conn.close()

    return preexisting


# Optional[float] / Optional[str] allow callers to filter by rolling hours, specific date, or default to today (local midnight).
def get_recent_modifications(
    hours: Optional[float] = None,
    since_date: Optional[str] = None,
    root_path: Optional[str] = None,
    limit: int = 50,
    markdown_only: bool = False,
) -> str:
    """
    Returns a deterministic, newest-first summary of Vault documents modified within a time window.

    Args:
        hours: Optional rolling lookback window in hours (e.g. 6.0 for last 6 hours).
               If both `hours` and `since_date` are omitted, defaults to today since 00:00:00 local time.
        since_date: Optional ISO date string 'YYYY-MM-DD' to query modifications since 00:00:00 on that date.
        root_path: Optional relative folder path from Vault root to scope the scan to a specific section.
        limit: Maximum number of modified documents to return (default: 50).
        markdown_only: If True, only include `.md` notes; otherwise include all non-hidden Vault documents (excluding `.gitkeep`).
    """
    search_root, err = _resolve_vault_dir(root_path)
    if err:
        return err

    resolved_vault = VAULT_PATH.resolve()

    # Resolve the local cutoff datetime based on caller arguments (hours -> since_date -> today at midnight).
    now_local = datetime.now()
    if hours is not None:
        cutoff_dt = now_local - timedelta(hours=hours)
        window_label = f"last {hours:g} hour(s) (since {cutoff_dt.strftime('%Y-%m-%d %H:%M:%S')})"
    elif since_date:
        try:
            parsed_date = datetime.strptime(since_date.strip(), "%Y-%m-%d").date()
            cutoff_dt = datetime.combine(parsed_date, time.min)
            window_label = f"since {since_date} 00:00:00"
        except ValueError:
            return f"Error: Invalid since_date '{since_date}'. Expected format: YYYY-MM-DD."
    else:
        # datetime.combine(date, time.min) anchors the default cutoff to 00:00:00 local time today.
        cutoff_dt = datetime.combine(now_local.date(), time.min)
        window_label = f"today ({now_local.strftime('%Y-%m-%d')} since 00:00:00)"

    # Convert cutoff datetime to a POSIX float timestamp (seconds since epoch) for fast comparison against os.stat().
    cutoff_ts: float = cutoff_dt.timestamp()
    # Query committed HITL revisions once so edited pre-existing notes are never flagged `[NEW]` due to legacy `os.replace` ctime drift.
    preexisting_hitl_files = _find_preexisting_files_from_hitl(cutoff_ts)

    # Tuple holds: (mtime_ts, is_new_in_window, rel_path_str, size_bytes)
    matched_files: List[Tuple[float, bool, str, int]] = []

    for root, dirs, files in os.walk(search_root):
        # Mutating dirs[:] in-place prunes IGNORE_DIRS (e.g. .git, .obsidian, Audio) so os.walk never descends into them.
        dirs[:] = [
            d for d in dirs
            if d not in IGNORE_DIRS
            and (Path(root) / d).resolve().is_relative_to(resolved_vault)
        ]

        for file in files:
            # Skip hidden dotfiles (e.g. .gitkeep, .DS_Store) that carry no user content.
            if file.startswith("."):
                continue
            if markdown_only and not file.endswith(".md"):
                continue

            filepath = (Path(root) / file).resolve()
            if not filepath.is_relative_to(resolved_vault):
                continue

            try:
                stat_info = filepath.stat()
            except OSError:
                # Ignore transient lock/permission errors on individual files during walk.
                continue

            if stat_info.st_mtime >= cutoff_ts:
                # Forward-slash relative path keeps output uniform across Windows and POSIX platforms.
                rel_path = str(filepath.relative_to(resolved_vault)).replace("\\", "/")
                # Compare filesystem birth/creation timestamp against `cutoff_ts` AND cross-check HITL pre-existence history.
                birthtime_ts = getattr(stat_info, "st_birthtime", stat_info.st_ctime)
                is_new = (birthtime_ts >= cutoff_ts) and (rel_path not in preexisting_hitl_files)
                matched_files.append((stat_info.st_mtime, is_new, rel_path, stat_info.st_size))

    scope_label = f"in '{root_path}'" if root_path else "across the Vault"
    if not matched_files:
        return f"No documents modified {window_label} {scope_label}."

    # Sort descending by modification timestamp (x[0]) so the most recently touched files appear at the top.
    matched_files.sort(key=lambda x: x[0], reverse=True)

    total_count = len(matched_files)
    displayed = matched_files[: max(1, limit)]

    lines: List[str] = [
        f"Modified documents {window_label} {scope_label} ({total_count} found):"
    ]
    for mtime_ts, is_new, rel_path, size_bytes in displayed:
        mtime_str = datetime.fromtimestamp(mtime_ts).strftime("%Y-%m-%d %H:%M:%S")
        action_badge = "NEW" if is_new else "EDITED"
        lines.append(f"- [{mtime_str}] [{action_badge}] {rel_path} ({size_bytes:,} bytes)")

    if total_count > len(displayed):
        lines.append(f"...and {total_count - len(displayed)} older modification(s) omitted (limit={limit}).")

    return "\n".join(lines)


if __name__ == "__main__":
    # Force UTF-8 stdout on Windows consoles so box-drawing characters and em-dashes do not raise UnicodeEncodeError.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="python -m nexus.shared_tools.vault_reader",
        description="Deterministic Vault filesystem inspector: query documents edited today, browse folder trees, read notes, or grep content.",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="List all Vault documents modified today (since 00:00:00 local time). Default action when no mode flag is passed.",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=None,
        help="List Vault documents modified within the last N hours (e.g. --hours 6).",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="List Vault documents modified since YYYY-MM-DD 00:00:00 (e.g. --since 2026-10-18).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of modified documents to display (default: 50).",
    )
    parser.add_argument(
        "--md-only",
        action="store_true",
        help="Only include .md files in recent modification queries.",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Optional Vault-relative folder path to scope queries (e.g. '3. Operations/3.1. Career Strategy & Revenue').",
    )
    parser.add_argument(
        "--tree",
        action="store_true",
        help="Print the Vault directory tree instead of recent modifications.",
    )
    parser.add_argument(
        "--files",
        action="store_true",
        help="Include file names when printing --tree.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Maximum folder depth to expand when printing --tree.",
    )
    parser.add_argument(
        "--read",
        type=str,
        default=None,
        metavar="NOTE",
        help="Read a specific note by name or Vault-relative path.",
    )
    parser.add_argument(
        "--search",
        type=str,
        default=None,
        metavar="KEYWORD",
        help="Search notes for a keyword string (optionally scoped by --path).",
    )

    args = parser.parse_args()

    if args.read:
        print(read_note_content(args.read, domain_path=args.path))
    elif args.search:
        print(search_within(args.search, root_path=args.path))
    elif args.tree:
        print(get_directory_tree(path=args.path, show_files=args.files or (args.path is not None), max_depth=args.depth))
    else:
        # Default to get_recent_modifications (--today if neither --hours nor --since is provided).
        print(
            get_recent_modifications(
                hours=args.hours,
                since_date=args.since,
                root_path=args.path,
                limit=args.limit,
                markdown_only=args.md_only,
            )
        )
