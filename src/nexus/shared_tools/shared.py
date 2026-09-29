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

def get_read_note_tool(agent_name: str, domain_path: str = None):
    """
    Factory function to create a read_note tool scoped to a specific agent's domain.
    
    Args:
        agent_name: The name of the agent reading the note (e.g. "Career Agent").
        domain_path: The Vault-relative path to the agent's primary domain folder. If None, gives global access.
    """
    from nexus.shared_tools.vault_reader import read_note_content
    
    @tool
    def read_note(note_path: str) -> str:
        """Read a specific note. You can provide the file name or relative path."""
        # The vault_reader handles the robust domain boundary check and fuzzy finding natively
        result = read_note_content(note_path, domain_path=domain_path)
        
        # Inject the agent's name into the boundary error message if it hit one
        if result.startswith("Error: Cannot read") and "Restricted to" in result:
            result = result.replace("Restricted to", f"{agent_name} is restricted to")
            
        return result
            
    return read_note


# ── Google Calendar Agentic Tool Wrappers ────────────────────────────────────

@tool
def get_calendar_schedule(days_ahead: int = 1) -> str:
    """Fetch live schedule from Google Calendar for today (and optionally upcoming days).

    Use this tool to inspect the user's real-time schedule, detect shifted time blocks,
    and ground daily planning or evening reviews without guessing.

    Args:
        days_ahead: Number of days forward to inspect (default: 1 for today only).
    """
    from datetime import datetime, time, timedelta
    from nexus.shared_tools.calendar_engine import list_events, format_events_as_markdown

    now_local = datetime.now().astimezone()
    start_dt = datetime.combine(now_local.date(), time.min).astimezone()
    end_dt = datetime.combine(now_local.date() + timedelta(days=days_ahead - 1), time.max).astimezone()

    events = list_events(start_iso=start_dt.isoformat(), end_iso=end_dt.isoformat())
    return format_events_as_markdown(events, title=f"Schedule ({start_dt.strftime('%A, %b %d')})")


@tool
def create_calendar_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    location: str = "",
) -> str:
    """Create a new event on Google Calendar.

    Args:
        summary: Event title (e.g. 'Deep Work: Resume Engine', 'Gym: Push Day').
        start_iso: RFC3339 datetime string (e.g. '2026-09-29T16:00:00-04:00') or date 'YYYY-MM-DD'.
        end_iso: RFC3339 datetime string (e.g. '2026-09-29T17:30:00-04:00') or date 'YYYY-MM-DD'.
        description: Optional notes, exercise target sets, or agenda.
        location: Optional location string or video meeting link.
    """
    from nexus.shared_tools.calendar_engine import create_event
    res = create_event(
        summary=summary,
        start_iso=start_iso,
        end_iso=end_iso,
        description=description,
        location=location,
    )
    return f"✅ Event created: '{res.get('summary')}' (ID: {res.get('id')}) from {res.get('start')} to {res.get('end')}."


@tool
def update_calendar_event(
    event_id: str,
    summary: str = "",
    start_iso: str = "",
    end_iso: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """Update or reschedule an existing event on Google Calendar.

    Args:
        event_id: The unique Google Calendar event ID.
        summary: New event title (leave empty to keep unchanged).
        start_iso: New start time in RFC3339 format (leave empty to keep unchanged).
        end_iso: New end time in RFC3339 format (leave empty to keep unchanged).
        description: New description (leave empty to keep unchanged).
        location: New location (leave empty to keep unchanged).
    """
    from nexus.shared_tools.calendar_engine import update_event
    res = update_event(
        event_id=event_id,
        summary=summary or None,
        start_iso=start_iso or None,
        end_iso=end_iso or None,
        description=description or None,
        location=location or None,
    )
    return f"✅ Event updated: '{res.get('summary')}' (ID: {res.get('id')})."
