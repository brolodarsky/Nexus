"""
tools.py — Core tools for the Nexus Engine's Career Agent.
Provides functions to read notes, search the career domain, check the master resume,
ask the librarian for cross-domain queries, and propose writes to the HITL queue.
"""
from pathlib import Path
from langchain_core.tools import tool

from nexus.core.constants import VAULT_PATH
from nexus.shared_tools.vault_reader import read_note_content, search_within
from nexus.shared_tools.shared import ask_librarian_escalation, get_propose_write_tool

# ── Constants ────────────────────────────────────────────────────────────────
CAREER_DOMAIN_PATH = VAULT_PATH / "3. Operations & Wealth" / "3.1. Career Strategy & Revenue"
RESUMES_PATH = CAREER_DOMAIN_PATH / "3.1.3. Professional Portfolio & Evidence" / "Resumes"
MASTER_RESUME_PATH = RESUMES_PATH / "Resume - Master.md"

# ── Shared Infrastructure ────────────────────────────────────────────────────
ask_librarian = ask_librarian_escalation
propose_write = get_propose_write_tool("career_agent")


# ── Domain-Scoped Tools ──────────────────────────────────────────────────────

@tool
def read_note(note_path: str) -> str:
    """Read a specific note from the career domain. Provide the relative path from the Vault root."""
    target = VAULT_PATH / note_path
    if not target.exists() and not target.suffix:
        target = target.with_suffix(".md")
        
    try:
        resolved_target = target.resolve()
        resolved_career = CAREER_DOMAIN_PATH.resolve()
        if not resolved_target.is_relative_to(resolved_career):
            return f"Error: Cannot read {note_path}. Career Agent is restricted to the Career Strategy domain."
    except Exception:
        pass

    return read_note_content(note_path)


@tool
def get_master_resume() -> str:
    """Read the master resume (Resume - Master.md) and return its full content.

    Use this when you need to tailor a resume for a specific job description.
    Read the master resume first, then craft a tailored version and propose it
    via propose_write.
    """
    if not MASTER_RESUME_PATH.exists():
        return "(Resume - Master.md not found)"
    try:
        with open(MASTER_RESUME_PATH, "r", encoding="utf-8") as f:
            return f"--- Resume - Master.md ---\n\n{f.read()}"
    except Exception as e:
        return f"Error reading master resume: {e}"


@tool
def search_career_domain(keyword: str) -> str:
    """Search for a keyword within the career domain files only. Returns matching file paths with context snippets."""
    relative_career_path = str(CAREER_DOMAIN_PATH.relative_to(VAULT_PATH)).replace('\\', '/')
    return search_within(keyword, root_path=relative_career_path)
