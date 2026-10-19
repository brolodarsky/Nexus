"""
tools.py — Librarian Agent tools.
LangChain @tool wrappers around pure Python vault_reader functions.
The Librarian has global scope (no path prefix constraints).
"""
from typing import Optional, List
from langchain_core.tools import tool

from nexus.shared_tools.vault_reader import (
    read_toc_content,
    read_note_content,
    search_within
)
# Standardize on shared tool implementations for vault structure and modification queries across all agents
from nexus.shared_tools.shared import get_vault_structure, get_recent_modifications

@tool
def read_toc() -> str:
    """Reads the Table of Contents.md file to understand the folder structure of the Vault."""
    return read_toc_content()

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
