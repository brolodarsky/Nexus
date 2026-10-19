"""
vault_reader.py — Pure Python filesystem operations for Vault navigation and recent modification queries (`--today`, `--hours`, `--tree`, `--search`).
No LangChain @tool decorators here. These functions can be used by any agent, CLI call, or HTTP route.
"""
import argparse
from datetime import datetime, time, timedelta
import os
import re
import sys
from pathlib import Path
from typing import Optional, List, Tuple

from nexus.core.constants import IGNORE_DIRS, VAULT_PATH

def read_toc_content() -> str:
    """Reads the Table of Contents.md file to understand the folder structure of the Vault."""
    toc_path = VAULT_PATH / "Table of Contents.md"
    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading Table of Contents: {str(e)}"


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
    if path:
        # The `/` operator on a pathlib.Path object joins path segments cleanly across OS platforms.
        start_path = VAULT_PATH / path
        if not start_path.exists() or not start_path.is_dir():
            return (
                f"Error: Path '{path}' does not exist or is not a directory. "
                f"Call with no arguments to see available folders."
            )
    else:
        start_path = VAULT_PATH

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

    header = f"{path}/" if path else "Vault/"
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

    # List comprehensions filter entries into directories (excluding IGNORE_DIRS like .git) and files.
    dirs = [e for e in entries if e.is_dir() and e.name not in IGNORE_DIRS]
    files = [e for e in entries if e.is_file()] if show_files else []

    for d in dirs:
        # When max_depth is reached, collapse immediate child folders inline (e.g. `dir/ [sub1, sub2]`) to save vertical lines.
        if max_depth is not None and current_depth >= max_depth:
            try:
                sub_dirs = sorted(
                    e.name for e in d.iterdir() if e.is_dir() and e.name not in IGNORE_DIRS
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


def read_note_content(note_path: str, domain_path: Optional[str] = None) -> str:
    """Reads the contents of a specific note or file in the Vault.
    
    Args:
        note_path: The file name or relative path.
        domain_path: Optional path relative to Vault to restrict search and resolution.
    """
    search_root = (VAULT_PATH / domain_path) if domain_path else VAULT_PATH
    
    if os.path.isabs(note_path):
        target_path = Path(note_path)
    else:
        # If domain_path is provided, try relative to domain first
        target_path = search_root / note_path
        if not target_path.exists() and not target_path.with_suffix('.md').exists() and domain_path:
            # Fall back to relative to VAULT_PATH in case agent gave vault-relative path
            vault_target = VAULT_PATH / note_path
            if vault_target.exists() or vault_target.with_suffix('.md').exists():
                target_path = vault_target

        if not target_path.exists():
            if not target_path.name.endswith('.md'):
                target_path = target_path.with_suffix('.md')
            
    if target_path.exists() and target_path.is_file():
        # Boundary check if domain_path is provided
        if domain_path:
            try:
                resolved_target = target_path.resolve()
                resolved_domain = search_root.resolve()
                if not resolved_target.is_relative_to(resolved_domain):
                    return f"Error: Cannot read {note_path}. Restricted to the {domain_path} domain."
            except Exception:
                pass
                
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                try:
                    rel_path = target_path.relative_to(VAULT_PATH)
                except ValueError:
                    rel_path = target_path
                return f"--- File: {rel_path} ---\n\n" + f.read()
        except Exception as e:
            return f"Error reading file {note_path}: {str(e)}"
    
    base_name = os.path.basename(note_path)
    if not base_name.endswith('.md'):
        base_name += '.md'
        
    found_paths = []
    for root, dirs, files in os.walk(search_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
        for file in files:
            if file == base_name or file == os.path.basename(note_path):
                found_paths.append(Path(root) / file)
                
    if not found_paths:
        scope = f" in {domain_path}" if domain_path else ""
        return f"File not found{scope}: {note_path}. Try using search to find the correct path."
    elif len(found_paths) == 1:
        try:
            with open(found_paths[0], 'r', encoding='utf-8') as f:
                rel_path = found_paths[0].relative_to(VAULT_PATH)
                return f"--- File: {rel_path} ---\n\n" + f.read()
        except Exception as e:
            return f"Error reading file {found_paths[0]}: {str(e)}"
    else:
        rel_paths = [str(p.relative_to(VAULT_PATH)) for p in found_paths]
        scope = f" in {domain_path}" if domain_path else ""
        return f"Multiple files found for {note_path}{scope}. Please be more specific. Matches:\n" + "\n".join(rel_paths)


def search_within(keyword: str, root_path: Optional[str] = None, tags: Optional[List[str]] = None) -> str:
    """Searches notes in the vault for a keyword string."""
    if root_path:
        search_root = VAULT_PATH / root_path
        if not search_root.exists() or not search_root.is_dir():
            return (
                f"Error: Path '{root_path}' does not exist or is not a directory. "
                f"Call get_directory_tree() to see available folders."
            )
    else:
        search_root = VAULT_PATH

    results = []
    keyword_lower = keyword.lower()
    tags_lower = {t.lower() for t in tags} if tags else None
    
    for root, dirs, files in os.walk(search_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            if not file.endswith('.md'):
                continue
                
            filepath = Path(root) / file
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
                    
                    rel_path = filepath.relative_to(VAULT_PATH)
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
    if root_path:
        search_root = VAULT_PATH / root_path
        if not search_root.exists() or not search_root.is_dir():
            return (
                f"Error: Path '{root_path}' does not exist or is not a directory. "
                f"Call get_directory_tree() to see available folders."
            )
    else:
        search_root = VAULT_PATH

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

    # Tuple holds: (mtime_ts, is_new_in_window, rel_path_str, size_bytes)
    matched_files: List[Tuple[float, bool, str, int]] = []

    for root, dirs, files in os.walk(search_root):
        # Mutating dirs[:] in-place prunes IGNORE_DIRS (e.g. .git, .obsidian, Audio) so os.walk never descends into them.
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            # Skip hidden dotfiles (e.g. .gitkeep, .DS_Store) that carry no user content.
            if file.startswith("."):
                continue
            if markdown_only and not file.endswith(".md"):
                continue

            filepath = Path(root) / file
            try:
                stat_info = filepath.stat()
            except OSError:
                # Ignore transient lock/permission errors on individual files during walk.
                continue

            if stat_info.st_mtime >= cutoff_ts:
                # Forward-slash relative path keeps output uniform across Windows and POSIX platforms.
                rel_path = str(filepath.relative_to(VAULT_PATH)).replace("\\", "/")
                # Compare creation timestamp (st_ctime) against cutoff_ts to distinguish newly created vs. edited notes.
                is_new = stat_info.st_ctime >= cutoff_ts
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

