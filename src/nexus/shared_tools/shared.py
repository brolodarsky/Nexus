"""
shared.py — Shared @tool wrappers for cross-agent infrastructure.
Any domain agent can import these tools into their tool array.
"""
from langchain_core.tools import tool
from nexus.core.constants import VAULT_PATH

@tool
def ask_librarian_escalation(query: str) -> str:
    """Escalate a cross-domain question to the Librarian Agent.

    Use this when you need information OUTSIDE your specific domain — for example,
    checking the user's current learning targets, health constraints, or project status.
    The Librarian has global read access to the entire Vault.

    Args:
        query: A natural language question to ask the Librarian.
    """
    from nexus.agents.librarian.api import ask_librarian as _ask_librarian
    return _ask_librarian(query)


def get_propose_write_tool(agent_name: str, domain_path: str = None):
    """
    Factory function to create a propose_write tool scoped to a specific agent.
    
    Args:
        agent_name: The name of the agent proposing the write (e.g. "career_agent").
        domain_path: The Vault-relative path to the agent's primary domain folder.
    """
    @tool
    def propose_write(target_file: str, proposed_content: str, reasoning: str) -> str:
        """Propose a write operation to the HITL (Human-In-The-Loop) queue for review.

        You NEVER write to the Vault directly. All modifications must go through HITL approval.

        Args:
            target_file: The file path. If it starts with '/' it is treated as an absolute Vault path.
                         Otherwise, it is treated as relative to your domain folder.
            proposed_content: The content to write (full or partial, depending on action_type).
            reasoning: A clear explanation of WHY this change should be made.
        """
        from nexus.core.hitl_queue import add_transaction

        # Handle path resolution based on domain
        clean_target = target_file.strip().replace('\\', '/')
        
        if clean_target.startswith('/'):
            # Absolute from Vault root
            vault_relative = clean_target.lstrip('/')
        elif domain_path:
            # Relative to domain
            clean_domain = domain_path.strip('/').replace('\\', '/')
            if clean_target.startswith(clean_domain):
                # LLM already included the domain path
                vault_relative = clean_target
            else:
                vault_relative = f"{clean_domain}/{clean_target}"
        else:
            # Fallback if no domain
            vault_relative = clean_target

        # hitl.py resolves paths against PROJECT_ROOT, so we must prepend "Vault/" 
        # to ensure the HITL queue writes to the correct location and not the engine directory.
        hitl_target_file = f"Vault/{vault_relative}"

        # Read the original content if the file exists
        original = None
        full_path = VAULT_PATH / vault_relative
        if full_path.exists():
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    original = f.read()
            except Exception:
                pass

        tx_id = add_transaction(
            agent_name=agent_name,
            action_type="modify" if original else "create",
            target_file=hitl_target_file,
            proposed_content=proposed_content,
            original_content=original,
            reasoning=reasoning,
        )

        return f"✅ Write proposed to HITL queue (Transaction #{tx_id}). Awaiting human approval."
        
    return propose_write
