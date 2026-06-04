"""
tools.py — Librarian Agent tools.
LangChain @tool wrappers around pure Python vault_reader functions.
The Librarian has global scope (no path prefix constraints).
"""
from typing import Optional, List
from langchain_core.tools import tool

from shared_tools.vault_reader import (
    read_toc_content,
    get_directory_tree,
    read_note_content,
    search_within
)

@tool
def read_toc() -> str:
    """Reads the Table of Contents.md file to understand the folder structure of the Vault."""
    return read_toc_content()

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
    """
    # If path is omitted, show folders only. If provided, show files too.
    show_files = path is not None
    return get_directory_tree(path=path, show_files=show_files)

@tool
def read_note(note_path: str) -> str:
    """Reads the contents of a specific note or file in the Vault. Provide the relative path from the Vault root, or just the note name if it's unique."""
    return read_note_content(note_path)

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
    """
    return search_within(keyword, root_path=path, tags=tags)
