"""
tools.py — Core tools for the Nexus Engine's Career Agent.
Provides functions to read notes, search the career domain, check the master resume,
ask the librarian for cross-domain queries, and propose writes to the HITL queue.
"""
import os
import sys
from pathlib import Path
from langchain_core.tools import tool

# ── Path Setup (allows direct execution from any working directory) ──────────
ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from core.constants import VAULT_PATH, IGNORE_DIRS

# ── Constants ────────────────────────────────────────────────────────────────
CAREER_DOMAIN_PATH = VAULT_PATH / "3. Operations & Wealth" / "3.1. Career Strategy & Revenue"
RESUMES_PATH = CAREER_DOMAIN_PATH / "3.1.3. Professional Portfolio & Evidence" / "Resumes"
MASTER_RESUME_PATH = RESUMES_PATH / "Resume - Master.md"


@tool
def read_note(note_path: str) -> str:
    """Read a specific note from the career domain. Provide the relative path from the Vault root."""
    target = VAULT_PATH / note_path
    if not target.exists():
        # Try adding .md extension
        if not target.suffix:
            target = target.with_suffix(".md")
    if not target.exists():
        return f"File not found: {note_path}"
    try:
        with open(target, "r", encoding="utf-8") as f:
            return f"--- File: {note_path} ---\n\n{f.read()}"
    except Exception as e:
        return f"Error reading {note_path}: {e}"


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
    results = []
    keyword_lower = keyword.lower()

    for root, dirs, files in os.walk(CAREER_DOMAIN_PATH):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            if not file.endswith(".md"):
                continue
            filepath = Path(root) / file
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                if keyword_lower in content.lower():
                    idx = content.lower().find(keyword_lower)
                    start = max(0, idx - 50)
                    end = min(len(content), idx + len(keyword) + 50)
                    snippet = content[start:end].replace("\n", " ")
                    rel_path = filepath.relative_to(VAULT_PATH)
                    results.append(f'- {rel_path}: "...{snippet}..."')
            except Exception:
                pass

    if not results:
        return f"No results found for '{keyword}' in career domain."

    output = f"Found '{keyword}' in {len(results)} career files:\n"
    for r in results[:15]:
        output += f"{r}\n"
    return output


@tool
def ask_librarian(query: str) -> str:
    """Escalate a cross-domain question to the Librarian Agent.

    Use this when you need information OUTSIDE the career domain — for example,
    checking the user's current learning targets, health constraints, or project status.
    The Librarian has global read access to the entire Vault.

    Args:
        query: A natural language question to ask the Librarian.
    """
    from agents.librarian.agent import ask_librarian as _ask_librarian
    return _ask_librarian(query)


@tool
def propose_write(target_file: str, proposed_content: str, reasoning: str) -> str:
    """Propose a write operation to the HITL (Human-In-The-Loop) queue for review.

    You NEVER write to the Vault directly. All modifications must go through HITL approval.

    Args:
        target_file: Relative path from Vault root to the file to modify.
        proposed_content: The content to write (full or partial, depending on action_type).
        reasoning: A clear explanation of WHY this change should be made.
    """
    from core.hitl_queue import add_transaction

    # Read the original content if the file exists
    original = None
    full_path = VAULT_PATH / target_file
    if full_path.exists():
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                original = f.read()
        except Exception:
            pass

    tx_id = add_transaction(
        agent_name="career_agent",
        action_type="modify" if original else "create",
        target_file=target_file,
        proposed_content=proposed_content,
        original_content=original,
        reasoning=reasoning,
    )

    return f"✅ Write proposed to HITL queue (Transaction #{tx_id}). Awaiting human approval."
