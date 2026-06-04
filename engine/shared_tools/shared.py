"""
shared.py — Shared @tool wrappers for cross-agent infrastructure.
Any domain agent can import these tools into their tool array.
"""
from langchain_core.tools import tool
from core.constants import VAULT_PATH

@tool
def ask_librarian_escalation(query: str) -> str:
    """Escalate a cross-domain question to the Librarian Agent.

    Use this when you need information OUTSIDE your specific domain — for example,
    checking the user's current learning targets, health constraints, or project status.
    The Librarian has global read access to the entire Vault.

    Args:
        query: A natural language question to ask the Librarian.
    """
    from agents.librarian.api import ask_librarian as _ask_librarian
    return _ask_librarian(query)


def get_propose_write_tool(agent_name: str):
    """
    Factory function to create a propose_write tool scoped to a specific agent.
    
    Args:
        agent_name: The name of the agent proposing the write (e.g. "career_agent").
    """
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
            agent_name=agent_name,
            action_type="modify" if original else "create",
            target_file=target_file,
            proposed_content=proposed_content,
            original_content=original,
            reasoning=reasoning,
        )

        return f"✅ Write proposed to HITL queue (Transaction #{tx_id}). Awaiting human approval."
        
    return propose_write
