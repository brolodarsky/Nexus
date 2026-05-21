"""
vault_tools.py — Local filesystem LangChain tools for Vault navigation.
Provides tools for reading the Table of Contents, browsing vault structure,
reading notes, and performing targeted keyword searches.
"""
import os
import re
import sys
from pathlib import Path
from typing import Optional, List
from langchain_core.tools import tool

from core.constants import IGNORE_DIRS

# Determine Vault root path dynamically
ENGINE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ENGINE_DIR.parent
VAULT_ROOT = PROJECT_ROOT / "Vault"

@tool
def read_toc() -> str:
    """Reads the Table of Contents.md file to understand the folder structure of the Vault."""
    toc_path = VAULT_ROOT / "Table of Contents.md"
    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading Table of Contents: {str(e)}"

@tool
def get_vault_structure(path: Optional[str] = None) -> str:
    """Browse the vault's directory tree. Acts as an 'agentic ls' for navigating the vault.

    - Called with NO path (or path=None): returns ALL folders recursively (no files).
      Use this first to orient yourself and identify which sections to drill into.
    - Called WITH a specific folder path: returns folders AND files within that subtree.
      Use this to see exactly what notes exist in a target area.

    Args:
        path: Optional relative path from Vault root (e.g. "2. Health/2.2. Medical").
              If omitted, returns the full folder tree from the vault root.

    Returns:
        An indented directory tree string.
    """
    if path:
        start_path = VAULT_ROOT / path
        if not start_path.exists() or not start_path.is_dir():
            return (
                f"Error: Path '{path}' does not exist or is not a directory. "
                f"Call get_vault_structure() with no arguments to see available folders."
            )
        show_files = True
    else:
        start_path = VAULT_ROOT
        show_files = False

    lines = []
    _build_tree(start_path, lines, prefix="", show_files=show_files)

    if not lines:
        return f"No contents found at '{path or 'Vault root'}'."

    header = f"{path}/" if path else "Vault/"
    return header + "\n" + "\n".join(lines)


def _build_tree(directory: Path, lines: list, prefix: str, show_files: bool):
    """Recursively build an indented tree representation of a directory.

    Args:
        directory: The directory to scan.
        lines: Accumulator list for output lines.
        prefix: Indentation prefix for the current depth level.
        show_files: If True, include files in the output alongside folders.
    """
    try:
        entries = sorted(directory.iterdir(), key=lambda e: e.name)
    except PermissionError:
        return

    # Separate dirs and files
    dirs = [e for e in entries if e.is_dir() and e.name not in IGNORE_DIRS]
    files = [e for e in entries if e.is_file()] if show_files else []

    for d in dirs:
        lines.append(f"{prefix}  {d.name}/")
        _build_tree(d, lines, prefix=prefix + "  ", show_files=show_files)

    for f in files:
        lines.append(f"{prefix}  {f.name}")


def _parse_frontmatter_tags(content: str) -> list:
    """Extract tags from YAML frontmatter using lightweight regex parsing.
    Handles both list-style and inline-style YAML tags:
      tags: [a, b, c]
      tags:
        - a
        - b
    """
    # Match the frontmatter block between --- delimiters
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
    list_match = re.search(r'tags:\s*\n((?:\s+-\s+.*\n?)+)', frontmatter)
    if list_match:
        raw_lines = list_match.group(1).strip().split('\n')
        tags = []
        for line in raw_lines:
            line = line.strip()
            if line.startswith('- '):
                tags.append(line[2:].strip().strip('"').strip("'"))
        return tags

    return []


@tool
def read_note(note_path: str) -> str:
    """Reads the contents of a specific note or file in the Vault. Provide the relative path from the Vault root, or just the note name if it's unique."""
    if os.path.isabs(note_path):
        target_path = Path(note_path)
    else:
        target_path = VAULT_ROOT / note_path
        if not target_path.exists():
            if not target_path.name.endswith('.md'):
                target_path = target_path.with_suffix('.md')
            
    if target_path.exists() and target_path.is_file():
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                try:
                    rel_path = target_path.relative_to(VAULT_ROOT)
                except ValueError:
                    rel_path = target_path
                return f"--- File: {rel_path} ---\n\n" + f.read()
        except Exception as e:
            return f"Error reading file {note_path}: {str(e)}"
    
    # If not found directly, try to search for the file in the Vault by note name
    base_name = os.path.basename(note_path)
    if not base_name.endswith('.md'):
        base_name += '.md'
        
    found_paths = []
    for root, dirs, files in os.walk(VAULT_ROOT):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
        for file in files:
            if file == base_name or file == os.path.basename(note_path):
                found_paths.append(Path(root) / file)
                
    if not found_paths:
        return f"File not found: {note_path}. Try using search_vault or get_vault_structure to find the correct path."
    elif len(found_paths) == 1:
        try:
            with open(found_paths[0], 'r', encoding='utf-8') as f:
                rel_path = found_paths[0].relative_to(VAULT_ROOT)
                return f"--- File: {rel_path} ---\n\n" + f.read()
        except Exception as e:
            return f"Error reading file {found_paths[0]}: {str(e)}"
    else:
        rel_paths = [str(p.relative_to(VAULT_ROOT)) for p in found_paths]
        return f"Multiple files found for {note_path}. Please be more specific. Matches:\n" + "\n".join(rel_paths)

@tool
def search_vault(keyword: str, path: Optional[str] = None, tags: Optional[List[str]] = None) -> str:
    """Searches notes in the vault for a keyword string. Returns matching file paths with context snippets.

    IMPORTANT: Prefer targeted searches over full-vault searches. Use get_vault_structure()
    first to identify the right section, then pass its path here.

    Args:
        keyword: The search term to look for (case-insensitive).
        path: Optional relative folder path from Vault root to limit the search scope
              (e.g. "3. Operations & Wealth/3.1. Career Strategy & Revenue").
              If omitted, searches the entire vault (expensive — use as last resort).
        tags: Optional list of tags to filter by. Only notes whose YAML frontmatter
              contains at least one of these tags will be searched.
              Example: ["medical", "career"]

    Returns:
        Matching file paths with surrounding context snippets, or "No results found".
    """
    if path:
        search_root = VAULT_ROOT / path
        if not search_root.exists() or not search_root.is_dir():
            return (
                f"Error: Path '{path}' does not exist or is not a directory. "
                f"Call get_vault_structure() to see available folders."
            )
    else:
        search_root = VAULT_ROOT

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

                # Apply tag filter if specified
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
                    
                    rel_path = filepath.relative_to(VAULT_ROOT)
                    results.append(f"- {rel_path}: \"...{snippet}...\"")
            except Exception:
                pass
                
    if not results:
        scope = f"in '{path}'" if path else "across the entire vault"
        tag_info = f" (filtered by tags: {', '.join(tags)})" if tags else ""
        return f"No results found for keyword: '{keyword}' {scope}{tag_info}."
        
    scope = f"in '{path}'" if path else "across the entire vault"
    output = f"Found '{keyword}' in {len(results)} files {scope}:\n"
    for r in results[:20]:
        output += f"{r}\n"
    if len(results) > 20:
        output += f"...and {len(results)-20} more files."
        
    return output
