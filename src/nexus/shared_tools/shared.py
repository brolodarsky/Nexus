"""
shared.py — Shared @tool wrappers for the Universal NexusAgent and spawned subagents.
Provides high-leverage, zero-drift tools for Vault navigation, reading, surgical file editing
(exact Target/Replacement patching routed through HITL), new note creation, recent modification
queries, email/calendar access, and on-demand CLI tool execution.
"""
import json
import subprocess
import sys
from typing import List, Optional

from langchain_core.tools import tool

from nexus.core.constants import PROJECT_ROOT, VAULT_PATH


# ── 1. Vault Directory & Navigation Tools ────────────────────────────────────

# Optional[str] (str | None) allows calling with no path to inspect the Vault root, or a section path to see notes.
@tool
def get_directory_structure(path: Optional[str] = None) -> str:
    """Browse the Vault's directory tree. Acts as an 'agentic ls' for navigating sections and listing files.

    - Called with NO path (or path=None): returns ALL folders recursively (no files).
      Use this to orient yourself and identify which sections to drill into.
    - Called WITH a specific folder path: returns folders AND files within that subtree.
      Use this to see `Section Instructions.md`, `Protocol - *.md`, and living/standard notes in a section.

    Args:
        path: Optional relative path from Vault root (e.g. "3. Operations/3.1. Career Strategy & Revenue").
              If omitted, returns the full folder tree from the Vault root.
    """
    from nexus.shared_tools.vault_reader import get_directory_tree

    # If path is omitted, show folders only for fast orientation; when drilling into a section, show files too.
    show_files = path is not None
    return get_directory_tree(path=path, show_files=show_files)


# Keep `get_vault_structure` as a tool alias so existing prompts/instructions referencing either name work identically.
@tool
def get_vault_structure(path: Optional[str] = None) -> str:
    """Browse the Vault's directory tree (alias for `get_directory_structure`).

    - Called with NO path: returns all folders recursively.
    - Called WITH a folder path: returns folders and files within that section.

    Args:
        path: Optional relative path from Vault root (e.g. "2. Health/2.2. Medical").
    """
    from nexus.shared_tools.vault_reader import get_directory_tree

    show_files = path is not None
    return get_directory_tree(path=path, show_files=show_files)


# ── 2. Vault File Reading & Search Tools ─────────────────────────────────────

# Optional[int] parameters let the agent inspect specific line ranges of large logs or TOC files without blowing token budget.
@tool
def read_file(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    """Read the contents of a note or file in the Vault (automatically reflects any pending staged HITL edits).

    You can pass a full Vault-relative path (e.g. "3. Operations/3.1. Career Strategy & Revenue/Job Hunt War Room.md")
    or a unique note title (e.g. "Job Hunt War Room" or "Health Summary.md").
    Optionally pass `start_line` and `end_line` (1-indexed, inclusive) to inspect a slice of a large file.

    Args:
        file_path: Relative path from Vault root or unique note filename.
        start_line: Optional 1-indexed starting line number (inclusive).
        end_line: Optional 1-indexed ending line number (inclusive).
    """
    from nexus.core.hitl_queue import get_pending_for_file
    from nexus.shared_tools.vault_reader import read_note_content, resolve_vault_note_path

    # 1. Check if this file has a pending transaction in the HITL queue (`hitl.db`).
    # First resolve on disk if it exists so short filenames ("Plan.md") map to their canonical `Vault/...` path.
    resolved_path, _ = resolve_vault_note_path(file_path)
    lookup_target = (
        f"Vault/{str(resolved_path.relative_to(VAULT_PATH)).replace(chr(92), '/')}"
        if resolved_path is not None
        else file_path
    )
    pending_tx = get_pending_for_file(lookup_target)
    if pending_tx and pending_tx.get("proposed_content") is not None:
        staged_text: str = pending_tx["proposed_content"]
        tx_id = pending_tx.get("id")
        target_name = pending_tx.get("target_file", lookup_target)
        banner = (
            f"[STAGED IN HITL QUEUE (Tx #{tx_id} on `{target_name}`) — "
            f"Showing cumulative pending content awaiting human approval]\n\n"
        )
        if start_line is not None or end_line is not None:
            lines = staged_text.splitlines()
            s_idx = max(0, (start_line or 1) - 1)
            e_idx = min(len(lines), end_line or len(lines))
            sliced = "\n".join(f"{i + 1}: {lines[i]}" for i in range(s_idx, e_idx))
            return f"{banner}--- {target_name} (Lines {s_idx + 1}-{e_idx} of {len(lines)}) ---\n{sliced}"
        return f"{banner}--- {target_name} ---\n{staged_text}"

    # 2. Otherwise read directly from disk
    return read_note_content(
        note_path=file_path,
        domain_path=None,
        start_line=start_line,
        end_line=end_line,
    )


@tool
def search_vault(
    keyword: str,
    path: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """Search notes in the Vault for a keyword string. Returns matching file paths with context snippets.

    Prefer passing `path` to scope the search to a target section when known.

    Args:
        keyword: Case-insensitive search term.
        path: Optional relative folder path from Vault root to scope the search
              (e.g. "3. Operations/3.1. Career Strategy & Revenue").
        tags: Optional list of YAML frontmatter tags to filter by (e.g. ["career", "medical"]).
    """
    from nexus.shared_tools.vault_reader import search_within

    return search_within(keyword=keyword, root_path=path, tags=tags)


@tool
def get_recent_modifications(
    hours: Optional[float] = None,
    since_date: Optional[str] = None,
    path: Optional[str] = None,
    limit: int = 50,
) -> str:
    """List Vault documents modified today (default) or within a specified time window, sorted newest-first.

    Use this tool during daily plan reconciliations, session boundary flushes, or status audits
    to deterministically see what documents were actually created or edited without guessing.

    Args:
        hours: Optional rolling lookback window in hours (e.g. 6.0 for the last 6 hours).
               Leave omitted to list all documents modified today since 00:00:00 local time.
        since_date: Optional ISO date 'YYYY-MM-DD' to list modifications since 00:00:00 on that date.
        path: Optional relative folder path from Vault root to scope the query to a specific section.
        limit: Maximum number of modified documents to return (default: 50).
    """
    from nexus.shared_tools.vault_reader import get_recent_modifications as _get_recent_modifications

    return _get_recent_modifications(
        hours=hours,
        since_date=since_date,
        root_path=path,
        limit=limit,
    )


# ── 3. Surgical File Modification & Creation Tools (HITL Two-Phase Commit) ──

def _normalize_line_endings(text: str) -> str:
    """Normalizes CRLF (`\\r\\n`) to LF (`\\n`) so multi-line string matching works across Windows and Unix files."""
    return text.replace("\r\n", "\n")


def _apply_surgical_replacement(source_text: str, target: str, replacement: str) -> Optional[str]:
    """Applies exact `target -> replacement` matching (with CRLF/LF normalization fallback). Returns None if not found."""
    if target in source_text:
        return source_text.replace(target, replacement)
    norm_source = _normalize_line_endings(source_text)
    norm_target = _normalize_line_endings(target)
    norm_replacement = _normalize_line_endings(replacement)
    if norm_target in norm_source:
        uses_crlf = "\r\n" in source_text
        patched_lf = norm_source.replace(norm_target, norm_replacement)
        return patched_lf.replace("\n", "\r\n") if uses_crlf else patched_lf
    return None


@tool
def modify_file(
    file_path: str,
    target: str,
    replacement: str,
    reasoning: str,
) -> str:
    """Surgically modify an existing (or pending staged) Vault note by replacing an exact `target` block with `replacement`.

    CUMULATIVE OVERLAY STACKING: If this note already has a pending transaction in the HITL queue (`hitl.db`),
    `modify_file` automatically applies your `target -> replacement` edit on top of the pending `proposed_content`
    and updates the single HITL card in place (preserving the true on-disk baseline and appending your reasoning).

    NEVER regenerate an entire existing file just to edit a section or bullet. Instead:
    1. Call `read_file` first so you know the exact current text (including any staged pending edits).
    2. Set `target` to the exact contiguous character sequence (including whitespace/indentation) you want to replace.
    3. Set `replacement` to the drop-in replacement text (or empty string "" to delete `target`).
    4. Python patches only that block into the file and stages/updates the single cumulative diff in `hitl.db`.

    Args:
        file_path: Vault-relative path or unique filename of the note to edit.
        target: The exact contiguous string in the file to be replaced (must match current/staged text).
        replacement: The new text to substitute in place of `target`.
        reasoning: Concise explanation of WHY this edit is being proposed for human HITL review.
    """
    from nexus.core.hitl_queue import add_transaction, get_file_mutation_lock, get_pending_for_file
    from nexus.shared_tools.vault_reader import resolve_vault_note_path

    if not target:
        return "Error: `target` cannot be empty in `modify_file`. Read the file first and pass the exact text block to replace, or use `create_file` for new files."

    resolved_path, err = resolve_vault_note_path(file_path)
    if resolved_path is not None:
        rel_vault_path = str(resolved_path.relative_to(VAULT_PATH)).replace("\\", "/")
        hitl_target_file = f"Vault/{rel_vault_path}"
    else:
        # File may not exist on disk yet because it was staged via `create_file` earlier in this session!
        pending_new = get_pending_for_file(file_path)
        if pending_new is None:
            return err or f"Error: Could not resolve existing or pending staged file '{file_path}'."
        hitl_target_file = pending_new["target_file"]

    # Critical Section: Serialize concurrent tool calls (e.g. parallel LangChain ToolNode worker threads)
    # targeting the same note so they cleanly inspect, stack, and coalesce edits instead of racing.
    with get_file_mutation_lock(hitl_target_file):
        if resolved_path is not None:
            try:
                disk_content: Optional[str] = resolved_path.read_text(encoding="utf-8")
            except Exception as e:
                return f"Error reading existing file '{file_path}': {e}"
        else:
            pending_new = get_pending_for_file(file_path)
            disk_content = pending_new.get("original_content") if pending_new else None

        # Check if there is already a pending HITL edit for this file so we stack on top of `proposed_content`
        pending_tx = get_pending_for_file(hitl_target_file)
        working_base = (
            pending_tx["proposed_content"]
            if (pending_tx and pending_tx.get("proposed_content") is not None)
            else (disk_content or "")
        )
        baseline_original = (
            pending_tx.get("original_content")
            if (pending_tx and pending_tx.get("original_content") is not None)
            else disk_content
        )
        action_type = (
            "create"
            if (pending_tx and pending_tx.get("action_type") == "create" and baseline_original is None)
            else "modify"
        )

        # Apply replacement onto the active working base (staged content first; fallback to disk if agent matched pre-stage text)
        proposed_content = _apply_surgical_replacement(working_base, target, replacement)
        if proposed_content is None and disk_content is not None and working_base != disk_content:
            # Agent matched against raw disk text; apply to disk_content only if `target` is also patched into `working_base`
            return (
                f"Error: `target` text was not found in the active staged version of `{hitl_target_file}` "
                f"(Pending HITL Tx #{pending_tx['id']}). Call `read_file(\"{file_path}\")` to see the current staged text "
                f"and apply your surgical edit on top of it."
            )
        if proposed_content is None:
            return (
                f"Error: `target` text was not found in `{hitl_target_file}`. "
                f"Call `read_file` to inspect the exact current lines and whitespace before calling `modify_file`."
            )

        tx_id = add_transaction(
            agent_name="nexus_agent",
            action_type=action_type,
            target_file=hitl_target_file,
            proposed_content=proposed_content,
            original_content=baseline_original,
            reasoning=reasoning,
        )
        if pending_tx:
            return (
                f"✅ Surgical modification stacked onto existing pending HITL Transaction #{tx_id} on `{hitl_target_file}` "
                f"(cumulative diff updated in place). Awaiting human approval."
            )
        return (
            f"✅ Surgical modification staged to HITL queue (Transaction #{tx_id} on `{hitl_target_file}`). "
            f"Awaiting human approval."
        )


@tool
def create_file(
    file_path: str,
    content: str,
    reasoning: str,
    overwrite: bool = False,
) -> str:
    """Propose creating a brand-new note in the Vault (staged to the HITL review queue).

    Fails if the file already exists unless `overwrite=True` (for existing files, always prefer `modify_file`).
    Ensure new notes include standard YAML frontmatter (`aliases`, `tags`, `type`) and a `**Back to:**` header bar.

    Args:
        file_path: Vault-relative path for the new file (e.g. "3. Operations/3.1. Career Strategy & Revenue/Missions/Acme Corp.md").
        content: Full Markdown content for the new file.
        reasoning: Concise explanation of WHY this file is being created.
        overwrite: Set True only if intentionally replacing an entire existing file (default: False).
    """
    from nexus.core.hitl_queue import add_transaction, get_file_mutation_lock

    clean_rel = file_path.strip().replace("\\", "/").lstrip("/")
    if clean_rel.startswith("Vault/"):
        clean_rel = clean_rel[len("Vault/"):]
    if not clean_rel.endswith(".md") and "." not in clean_rel.split("/")[-1]:
        clean_rel += ".md"

    hitl_target_file = f"Vault/{clean_rel}"
    with get_file_mutation_lock(hitl_target_file):
        full_path = VAULT_PATH / clean_rel
        original_content: Optional[str] = None

        if full_path.exists():
            if not overwrite:
                return (
                    f"Error: File 'Vault/{clean_rel}' already exists. "
                    f"Use `modify_file(file_path, target, replacement, reasoning)` to surgically edit existing files, "
                    f"or pass `overwrite=True` if you intentionally need a full-file replacement."
                )
            try:
                original_content = full_path.read_text(encoding="utf-8")
            except Exception:
                original_content = None

        tx_id = add_transaction(
            agent_name="nexus_agent",
            action_type="modify" if original_content is not None else "create",
            target_file=hitl_target_file,
            proposed_content=content,
            original_content=original_content,
            reasoning=reasoning,
        )
        return (
            f"✅ File {'overwrite' if original_content is not None else 'creation'} staged to HITL queue "
            f"(Transaction #{tx_id} on `{hitl_target_file}`). Awaiting human approval."
        )


# ── 4. External Communication & Schedule Tools (Gmail & Calendar) ────────────

# Cap each email body so a long newsletter cannot blow the context window
_BODY_CHAR_LIMIT = 4000


@tool
def fetch_emails(query: str = "in:inbox", count: int = 5, account: str = "all") -> str:
    """Search and fetch emails from Gmail using native Gmail search syntax across accounts.

    Read-only operation. Use this when the user asks to check their email, find recruiter outreach,
    or look up a message thread. Supports multi-account Gmail ('all' to aggregate across all connected
    inboxes, or a specific account alias like 'default' or 'work').

    Args:
        query: Gmail search syntax (e.g. 'in:inbox', 'from:recruiter newer_than:7d', 'subject:interview').
        count: Maximum number of emails to return (default: 5).
        account: Account alias ('all' for all configured accounts, 'default', or custom name).
    """
    from nexus.shared_tools import gmail_engine

    try:
        summaries = gmail_engine.list_messages(query=query, max_results=count, account=account)
        emails = []
        for s in summaries:
            msg_acc = s.get("account", account if account != "all" else "default")
            msg = gmail_engine.get_message(s["id"], account=msg_acc)
            emails.append({
                "id": msg["id"],
                "account": msg.get("account", msg_acc),
                "thread_id": msg["thread_id"],
                "subject": msg["subject"],
                "sender": msg["sender"],
                "date": msg["date"],
                "body": msg["body"][:_BODY_CHAR_LIMIT],
            })
        return json.dumps(emails, ensure_ascii=False)
    except Exception as exc:
        return json.dumps([{"error": f"fetch_emails failed: {exc}"}])


@tool
def get_calendar_schedule(days_ahead: int = 1, days_back: int = 0) -> str:
    """Fetch live schedule from Google Calendar for today, past days, and/or upcoming days.

    Use this tool to inspect the user's real-time schedule, audit yesterday's completed blocks
    for daily event receipts (`days_back=1`), detect shifted time blocks, and ground daily planning.

    Args:
        days_ahead: Number of days forward to inspect (default: 1 for today; set to 0 when only inspecting past days).
        days_back: Number of days backward to include (default: 0; pass `days_back=1` to inspect yesterday's calendar).
    """
    from datetime import datetime, time, timedelta
    from nexus.shared_tools.calendar_engine import format_events_as_markdown, list_events

    now_local = datetime.now().astimezone()
    start_dt = datetime.combine(now_local.date() - timedelta(days=max(0, days_back)), time.min).astimezone()
    end_offset = max(-days_back, days_ahead - 1)
    end_dt = datetime.combine(now_local.date() + timedelta(days=end_offset), time.max).astimezone()

    events = list_events(start_iso=start_dt.isoformat(), end_iso=end_dt.isoformat())
    if start_dt.date() == end_dt.date():
        title = f"Schedule ({start_dt.strftime('%A, %b %d')})"
    else:
        title = f"Schedule ({start_dt.strftime('%a, %b %d')} – {end_dt.strftime('%a, %b %d')})"
    return format_events_as_markdown(events, title=title)


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
        start_iso: RFC3339 datetime string (e.g. '2026-10-21T16:00:00-04:00') or date 'YYYY-MM-DD'.
        end_iso: RFC3339 datetime string (e.g. '2026-10-21T17:30:00-04:00') or date 'YYYY-MM-DD'.
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


# ── 5. On-Demand Shared CLI Tool Runner ──────────────────────────────────────

@tool
def run_shared_tool_cli(module: str, cli_args: Optional[List[str]] = None) -> str:
    """Invoke any `[CLI]` module listed in the `Shared Tools` catalog on demand via `.venv` Python.

    Use this for specialized tools not bound as primary tools (e.g. `nexus.shared_tools.read_webpage`,
    `nexus.shared_tools.youtube_transcript`, `nexus.shared_tools.generate_podcast`,
    `nexus.shared_tools.resume_engine.render_docx`, `nexus.shared_tools.gmail_engine`).
    Pass `cli_args=["--help"]` first if you need to inspect a module's CLI flags.

    Args:
        module: Dotted Python module path starting with `nexus.shared_tools.` (e.g. "nexus.shared_tools.read_webpage").
        cli_args: Optional list of CLI argument strings (e.g. ["https://example.com"] or ["--help"]).
    """
    clean_mod = module.strip()
    # Security boundary: restrict execution strictly to modules inside `nexus.shared_tools.`
    if not clean_mod.startswith("nexus.shared_tools."):
        return "Error: Only `nexus.shared_tools.<module>` modules may be invoked via `run_shared_tool_cli`."

    cmd = [sys.executable, "-m", clean_mod] + (cli_args or [])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        output = output.strip()
        if len(output) > 8000:
            output = output[:8000] + "\n... [output truncated at 8000 chars]"
        return output or f"(exit code {proc.returncode}, no output)"
    except Exception as e:
        return f"Error running `{clean_mod}`: {e}"


# ── 6. Shared Inter-Agent Blackboard / Message Board Tools ───────────────────

@tool
def post_to_board(
    title: str,
    content: str,
    channel: str = "general",
    author: str = "Subagent",
    pinned: bool = False,
) -> str:
    """Post a structured situational bulletin onto the Shared Agent Blackboard (`blackboard.db`).

    Use this tool in subagents and multi-step missions to broadcast distilled findings
    (e.g. Gmail inbox sweep takeaways, Google Calendar schedule audits, Vault status discoveries,
    or mission progress) so the primary orchestrator (`NexusAgent` / Astra), peer subagents,
    and the GUI Bulletin Feed have live shared situational awareness without redundant API sweeps.

    Args:
        title: Concise headline for the bulletin (e.g. "Oct 22 Multi-Inbox Gmail Triage" or "Wed Oct 21 Calendar Audit").
        content: Markdown summary of findings, actionable items, and key metadata.
        channel: Board channel tag — one of `"email"`, `"calendar"`, `"vault"`, `"mission"`, or `"general"`.
        author: Identifier for the agent posting (e.g. `"Flash: Gmail Sweep"`, `"Flash: Calendar Audit"`, `"Astra"`).
        pinned: Set True to pin high-priority standing bulletins to the top of the board.
    """
    from nexus.core.blackboard import post_bulletin

    bulletin_id = post_bulletin(
        author=author,
        title=title,
        content=content,
        channel=channel,
        pinned=pinned,
    )
    return f"📋 Bulletin #{bulletin_id} posted to Shared Blackboard [`{channel}`]: '{title}'."


@tool
def read_board(
    channel: Optional[str] = None,
    limit: int = 12,
) -> str:
    """Read recent bulletins from the Shared Agent Blackboard (`blackboard.db`).

    Call this to inspect recent findings already gathered by Flash subagents (`email`, `calendar`,
    `vault`, `mission`) before launching duplicate external API sweeps.

    Args:
        channel: Optional channel filter (`"email"`, `"calendar"`, `"vault"`, `"mission"`, `"general"`).
                 Leave omitted or pass `"all"` to view bulletins across all channels.
        limit: Maximum number of recent bulletins to return (default: 12).
    """
    from nexus.core.blackboard import format_board_digest

    return format_board_digest(channel=channel, limit=limit)


# ── Backward-Compatible Factories (for any legacy callers) ───────────────────

def get_read_note_tool(agent_name: str = "NexusAgent", domain_path: Optional[str] = None):
    """Returns the universal `read_file` tool (legacy factory shim)."""
    return read_file


def get_propose_write_tool(agent_name: str = "nexus_agent", domain_path: Optional[str] = None):
    """Returns the surgical `modify_file` tool (legacy factory shim)."""
    return modify_file
