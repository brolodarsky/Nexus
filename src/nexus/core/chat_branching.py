"""
chat_branching.py — Universal Conversation Branching & Subroutine Merge Engine.

Implements conversation branching as an engine-level session primitive (analogous to an OS stack frame):
  Parent Thread ──(fork: tangent | full clone)──► Child Branch (Isolated ALU) ──(distill & merge)──► Parent Thread

Supports two fork modes:
  1. `tangent` (Default — Context-Sliced ALU): Compresses prior parent turns before the branch point into a
     proportional `Parent Context Brief` (scaling from a few bullets/paragraphs for quick tangents up to
     comprehensive multi-section pages for deep technical work) + preserves the focal turn verbatim.
  2. `fork` (Full History Clone): Clones all parent messages up to the branch point verbatim into the child thread.

And supports `distill_and_merge_branch`:
  Synthesizes the child branch's work at a depth proportional to its complexity and injects the resulting
  distillation directly into the parent conversation's `chats.db` log and LangGraph `memory.sqlite` state.
"""

from typing import Any, Optional
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from nexus.agent.graph import extract_message_text
from nexus.core.chats_db import (
    append_thread_lc_messages,
    create_branch_conversation,
    create_conversation,
    get_chat_history,
    get_conversation,
    log_message,
    mark_branch_merged,
    replace_thread_lc_messages,
)
from nexus.core.constants import get_chat_model, resolve_model_config
from nexus.core.conversation_cache import format_captures_manifest, inherit_captures


def _format_transcript_for_synthesis(messages: list[dict]) -> str:
    """
    Formats a sequence of `chats.db` message dicts into a clean readable transcript string for LLM synthesis.

    Parameters:
      messages: Ordered list of message dictionaries (`role`, `content`, `agent`).

    Returns:
      Formatted multi-turn transcript text.
    """
    blocks: list[str] = []
    for idx, msg in enumerate(messages, start=1):
        role_label = "User" if msg.get("role") == "user" else f"Assistant ({msg.get('agent') or 'nexus'})"
        content = (msg.get("content") or "").strip()
        if content:
            blocks.append(f"--- Turn Message #{idx} [{role_label}] ---\n{content}")
    return "\n\n".join(blocks)


def _derive_branch_title(parent_title: str, focal_messages: list[dict], explicit_title: Optional[str] = None) -> str:
    """
    Derives a clean, readable title for a newly spawned branch conversation.

    Parameters:
      parent_title: Title of the parent conversation thread.
      focal_messages: The message(s) at the branch point.
      explicit_title: Optional user-provided custom branch title.

    Returns:
      A concise title string prefixed with `🌿 `.
    """
    if explicit_title and explicit_title.strip():
        cleaned = explicit_title.strip()
        return cleaned if cleaned.startswith("🌿") else f"🌿 {cleaned}"

    # Extract a short snippet from the user prompt or focal message at the branch point
    for msg in focal_messages:
        text = (msg.get("content") or "").strip()
        if text:
            # Strip markdown headers and take the first non-empty line
            first_line = next((line.lstrip("#*- >").strip() for line in text.splitlines() if line.strip()), "")
            if first_line:
                snippet = first_line[:48].rstrip()
                if len(first_line) > 48:
                    snippet += "…"
                return f"🌿 {snippet}"

    base_parent = (parent_title or "Chat").lstrip("🌿 ").strip()
    return f"🌿 Branch: {base_parent[:40]}"


def seed_langgraph_thread_from_messages(conversation_id: str, messages: list[dict]) -> None:
    """
    Seeds the canonical `thread_messages` history in `chats.db` for `conversation_id` with initial messages.

    Why this exists:
      When a child branch is created in `chats.db`, it has no `thread_messages` rows yet. Seeding the
      canonical `HumanMessage` / `AIMessage` history ensures Turn 1 in the child branch has full context
      without relying on a separate `memory.sqlite` checkpointer.

    Parameters:
      conversation_id: UUID of the target conversation thread.
      messages: Chronological list of `chats.db` message dicts to seed into canonical state.
    """
    if not conversation_id or not messages:
        return

    lc_messages: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        else:
            lc_messages.append(AIMessage(content=content))

    # If the seeded slice starts with an AIMessage (e.g., a Parent Context Brief), prepend a lightweight
    # HumanMessage anchor so strict turn-alternating LLM providers (Gemini/Anthropic) never reject Message #0.
    # Also remind the child agent that domain Section Instructions and living notes are NOT yet hydrated.
    if lc_messages and isinstance(lc_messages[0], AIMessage):
        lc_messages.insert(
            0,
            HumanMessage(
                content=(
                    "[Session initialized from parent conversation branch context — Note: Section Instructions "
                    "and living notes are NOT yet loaded in this thread. Hydrate target section files from disk "
                    "before mutating state or delegating.]"
                )
            ),
        )

    try:
        replace_thread_lc_messages(conversation_id, lc_messages, turn_id="branch_seed")
    except Exception:
        # Non-fatal guard: if seeding fails, `load_thread_lc_messages` still falls back to `messages`
        pass


def append_message_to_langgraph_thread(conversation_id: str, role: str, content: str) -> None:
    """
    Appends a single message (such as a Distilled Branch Merge) into an existing thread's canonical `thread_messages` state.

    Parameters:
      conversation_id: UUID of the target parent conversation thread.
      role: Either `'user'` or `'assistant'`.
      content: Markdown body to append into the thread's active context window.
    """
    if not conversation_id or not content:
        return

    lc_msg: BaseMessage = HumanMessage(content=content) if role == "user" else AIMessage(content=content)
    try:
        append_thread_lc_messages(conversation_id, [lc_msg], turn_id="branch_merge")
    except Exception:
        pass


def synthesize_parent_context_brief(
    parent_title: str,
    prior_messages: list[dict],
    focal_messages: list[dict],
    model_tier: str = "low",
) -> str:
    """
    Synthesizes a proportional Parent Context Brief from turns preceding the branch point (`tangent` mode).

    Proportional Depth Standard:
      Does NOT artificially cap output at 3 short bullets. Scales proportionally to the depth and complexity
      of the parent conversation: a few high-signal bullets/paragraphs for short threads, up to a comprehensive,
      multi-section brief (even a page or more) for complex architectural, engineering, or domain work.

    Parameters:
      parent_title: Title of the parent conversation thread.
      prior_messages: Messages in the parent conversation *before* the focal branch turn.
      focal_messages: The focal turn message(s) at the branch point.
      model_tier: Model tier to execute synthesis (`'low'`, `'medium'`, `'strong'`).

    Returns:
      Markdown string containing the synthesized Parent Context Brief.
    """
    if not prior_messages:
        return ""

    prior_transcript = _format_transcript_for_synthesis(prior_messages)
    focal_transcript = _format_transcript_for_synthesis(focal_messages)

    system_prompt = (
        "You are the Context Slicing Engine for Nexus Universal Conversation Branching.\n"
        "A user is branching off from a parent conversation into an isolated child thread to explore a sub-topic or tangent.\n"
        "Your job is to synthesize the PRIOR parent conversation history (leading up to the branch point) into a "
        "clear, high-signal **Parent Context Brief** so the child thread starts with complete situational awareness "
        "without carrying raw conversational clutter.\n\n"
        "### Proportional Depth Directive:\n"
        "- Do NOT artificially restrict yourself to 3 tiny bullets.\n"
        "- Scale your brief proportionally to the complexity and volume of the prior work:\n"
        "  - For short, simple discussions: write a concise summary paragraph and a few bullets.\n"
        "  - For deep engineering, architectural, clinical, or strategic discussions: write a thorough, "
        "multi-paragraph / multi-section brief (up to a full page or more if needed) that preserves all critical "
        "constraints, decisions, file paths, schemas, code snippets, formulas, and open questions.\n"
        "- Output clean GitHub-Flavored Markdown directly (no introductory meta-chatter)."
    )

    user_prompt = (
        f"**Parent Thread Title:** {parent_title}\n\n"
        f"### Prior Conversation History (to synthesize into the Parent Context Brief):\n"
        f"{prior_transcript}\n\n"
        f"### Focal Branch Point (kept verbatim immediately after your brief—use this to know what matters most):\n"
        f"{focal_transcript}\n\n"
        "Produce the **Parent Context Brief** now:"
    )

    try:
        resolved = resolve_model_config(model_tier or "low")
        llm = get_chat_model(tier=resolved["tier"], temperature=0.2)
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        synthesized = extract_message_text(response).strip()
        if synthesized:
            return synthesized
    except Exception:
        pass

    # Deterministic fallback if LLM provider is unreachable (e.g., offline mode or unit tests)
    fallback_lines = [f"- **{m.get('role', 'turn').capitalize()}:** {(m.get('content') or '')[:300]}" for m in prior_messages[-6:]]
    return "Prior context summary:\n" + "\n".join(fallback_lines)


def synthesize_branch_distillation(
    branch_title: str,
    parent_title: str,
    branch_messages: list[dict],
    user_guidance: Optional[str] = None,
    model_tier: str = "low",
) -> str:
    """
    Distills a child branch conversation into a structured takeaway block to merge back into the parent thread.

    Proportional Depth Standard:
      Scales output length and detail proportionally to the substance of the branch—from a few crisp bullets
      or paragraphs for quick tangents, up to a comprehensive multi-section synthesis (including code blocks,
      schemas, file paths, and rationale—even a page or more) for deep technical or analytical branches.

    Parameters:
      branch_title: Title of the child branch being merged.
      parent_title: Title of the parent thread receiving the merge.
      branch_messages: Chronological list of messages in the child branch.
      user_guidance: Optional user instructions specifying what to emphasize in the distillation.
      model_tier: Model tier to execute distillation (`'low'`, `'medium'`, `'strong'`).

    Returns:
      Markdown string containing the distilled branch takeaways.
    """
    # Filter out the initial synthetic `branch_context` brief so we focus on the actual work done in the branch
    substantive_msgs = [m for m in branch_messages if m.get("agent") != "branch_context"]
    if not substantive_msgs:
        substantive_msgs = branch_messages

    transcript = _format_transcript_for_synthesis(substantive_msgs)

    system_prompt = (
        "You are the Subroutine Return & Distillation Engine for Nexus Universal Conversation Branching.\n"
        "The user branched off from a parent conversation into an isolated child thread, completed exploration/work "
        "in that branch, and is now merging the distilled takeaways back into the parent thread.\n\n"
        "### Proportional Depth Directive:\n"
        "- Do NOT artificially limit the distillation to 3 short bullets.\n"
        "- Match the depth of your distillation to the complexity and volume of the branch work:\n"
        "  - For quick side questions or minor tangents: provide a few clear bullets or a short summary paragraph.\n"
        "  - For complex engineering, architecture, debugging, research, or planning branches: provide a comprehensive, "
        "structured multi-section distillation (multiple paragraphs, detailed bullet hierarchies, preserved code snippets, "
        "schemas, file paths, trade-offs, and concrete conclusions—up to a full page or more when warranted) so the "
        "parent conversation receives 100% of the substantive value without needing the raw back-and-forth turns.\n"
        "- Output clean GitHub-Flavored Markdown directly (no introductory meta-chatter)."
    )

    guidance_block = f"\n\n### User Merge Guidance / Focus:\n{user_guidance.strip()}\n" if user_guidance and user_guidance.strip() else ""

    user_prompt = (
        f"**Parent Thread:** {parent_title}\n"
        f"**Child Branch:** {branch_title}"
        f"{guidance_block}\n\n"
        f"### Child Branch Transcript:\n{transcript}\n\n"
        "Produce the distilled merge summary to inject back into the parent thread:"
    )

    try:
        resolved = resolve_model_config(model_tier or "low")
        llm = get_chat_model(tier=resolved["tier"], temperature=0.2)
        response = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        distilled = extract_message_text(response).strip()
        if distilled:
            return distilled
    except Exception:
        pass

    # Deterministic fallback if LLM provider is unreachable (e.g., offline mode or unit tests)
    fallback_items = [
        f"- **{m.get('role', 'turn').capitalize()}:** {(m.get('content') or '')[:400]}"
        for m in substantive_msgs[-6:]
    ]
    return "Key branch takeaways:\n" + "\n".join(fallback_items)


def fork_conversation(
    parent_conversation_id: str,
    parent_message_id: Optional[int] = None,
    parent_message_index: Optional[int] = None,
    branch_mode: str = "tangent",
    title: Optional[str] = None,
    model_tier: str = "low",
) -> dict[str, Any]:
    """
    Forks a parent conversation at a specific message turn into a new child branch conversation.

    Parameters:
      parent_conversation_id: UUID of the parent conversation thread.
      parent_message_id: Optional SQLite `messages.id` where the branch occurs.
      parent_message_index: Optional 0-based message index fallback if `parent_message_id` is omitted.
      branch_mode: `'tangent'` (context-sliced Parent Context Brief + focal turn) or `'fork'` (full clone up to turn).
      title: Optional explicit title for the new branch.
      model_tier: Model tier used when synthesizing the Parent Context Brief in `'tangent'` mode.

    Returns:
      Dictionary containing `conversation_id`, `conversation` record, and seeded `messages`.
    """
    parent_conv = get_conversation(parent_conversation_id)
    if not parent_conv:
        raise ValueError(f"Parent conversation '{parent_conversation_id}' not found.")

    parent_history = get_chat_history(parent_conversation_id)
    if not parent_history:
        raise ValueError(f"Parent conversation '{parent_conversation_id}' has no messages to branch from.")

    # Resolve the slice end index `slice_idx` (inclusive) in `parent_history`
    slice_idx = len(parent_history) - 1
    if parent_message_id is not None:
        for i, msg in enumerate(parent_history):
            if msg.get("id") == parent_message_id:
                slice_idx = i
                break
    elif parent_message_index is not None and 0 <= parent_message_index < len(parent_history):
        slice_idx = parent_message_index

    sliced_history = parent_history[: slice_idx + 1]
    resolved_fork_msg_id = sliced_history[-1].get("id")
    effective_mode = "fork" if branch_mode == "fork" else "tangent"

    # Identify the focal turn at the branch point:
    # If the user branched on an assistant reply preceded by a user prompt, keep both as the focal turn pair.
    if len(sliced_history) >= 2 and sliced_history[-1].get("role") == "assistant" and sliced_history[-2].get("role") == "user":
        focal_messages = sliced_history[-2:]
        prior_messages = sliced_history[:-2]
    else:
        focal_messages = sliced_history[-1:]
        prior_messages = sliced_history[:-1]

    branch_title = _derive_branch_title(parent_conv.get("title") or "Chat", focal_messages, explicit_title=title)
    # Mark explicit user-supplied titles as "manual" so background auto-titling never overwrites them
    branch_title_source = "manual" if (title and title.strip()) else "placeholder"

    # Inherit the newest executed model from the forked slice (falling back to parent conversation metadata)
    # so switching into the child branch preserves prompt-cache and model continuity
    inherited_tier: Optional[str] = None
    inherited_name: Optional[str] = None
    for msg in reversed(sliced_history):
        if msg.get("model_name") or msg.get("model_tier"):
            inherited_tier = msg.get("model_tier")
            inherited_name = msg.get("model_name")
            break
    if not inherited_tier and not inherited_name:
        inherited_tier = parent_conv.get("last_model_tier")
        inherited_name = parent_conv.get("last_model_name")

    child_conv_id = create_branch_conversation(
        title=branch_title,
        parent_conversation_id=parent_conversation_id,
        parent_message_id=resolved_fork_msg_id,
        branch_mode=effective_mode,
        title_source=branch_title_source,
        last_model_tier=inherited_tier,
        last_model_name=inherited_name,
    )
    # Snapshot parent's external capture cache into the child branch so cache:// refs remain resolvable
    inherit_captures(parent_conversation_id, child_conv_id)

    if effective_mode == "fork" or not prior_messages:
        # Full clone mode (or branching on the very first turn where no prior history exists):
        # Copy all messages up to the branch point verbatim into the child conversation.
        for msg in sliced_history:
            log_message(
                role=msg["role"],
                content=msg["content"],
                agent=msg.get("agent"),
                domain=msg.get("domain"),
                confidence=msg.get("confidence"),
                trace=msg.get("trace"),
                conversation_id=child_conv_id,
                images=msg.get("images"),
                model_tier=msg.get("model_tier"),
                model_name=msg.get("model_name"),
                cost_usd=msg.get("cost_usd"),
            )
    else:
        # Tangent mode (Context-Sliced ALU):
        # 1. Synthesize proportional Parent Context Brief from `prior_messages`
        brief_body = synthesize_parent_context_brief(
            parent_title=parent_conv.get("title") or "Parent Chat",
            prior_messages=prior_messages,
            focal_messages=focal_messages,
            model_tier=model_tier,
        )
        brief_header = (
            f"### 🌿 Parent Context Brief *(from \"{parent_conv.get('title') or 'Parent Chat'}\")*\n\n"
            f"{brief_body}"
        )
        log_message(
            role="assistant",
            content=brief_header,
            agent="branch_context",
            domain=None,
            confidence=1.0,
            trace=[],
            conversation_id=child_conv_id,
        )
        # 2. Copy the focal turn message(s) verbatim so the exact branched prompt/response is intact
        for msg in focal_messages:
            log_message(
                role=msg["role"],
                content=msg["content"],
                agent=msg.get("agent"),
                domain=msg.get("domain"),
                confidence=msg.get("confidence"),
                trace=msg.get("trace"),
                conversation_id=child_conv_id,
                images=msg.get("images"),
                model_tier=msg.get("model_tier"),
                model_name=msg.get("model_name"),
                cost_usd=msg.get("cost_usd"),
            )

    child_history = get_chat_history(child_conv_id)
    seed_langgraph_thread_from_messages(child_conv_id, child_history)
    child_conv = get_conversation(child_conv_id)

    return {
        "conversation_id": child_conv_id,
        "conversation": child_conv,
        "messages": child_history,
        "parent_conversation_id": parent_conversation_id,
        "parent_message_id": resolved_fork_msg_id,
        "branch_mode": effective_mode,
    }


# `title: str` is the human-readable sidebar label for the new conversation.
# `context_brief: str` is the Markdown handoff brief seeded as the opening context of the fresh thread.
# `parent_conversation_id: Optional[str]` identifies the active conversation spawning this thread (None if headless/root).
# `nest_under_parent: bool` nests the thread as a child branch under `parent_conversation_id` when True, or creates a root thread when False.
# `parent_message_id: Optional[int]` optionally pins the branch to a specific parent message row ID; falls back to the latest parent message.
# `target_section: Optional[str]` optionally appends a live `get_directory_tree(..., show_files=True)` snapshot to the seeded brief.
# `source_cache_conversation_id: Optional[str]` optional cache source ID (e.g. `"nexus_primary"` in CLI/eval mode when `parent_conversation_id` is None).
# `-> dict[str, Any]` returns the created conversation UUID, metadata row, seeded messages list, and path/cache verification metadata.
def spawn_seeded_conversation(
    title: str,
    context_brief: str,
    parent_conversation_id: Optional[str] = None,
    nest_under_parent: bool = True,
    parent_message_id: Optional[int] = None,
    target_section: Optional[str] = None,
    source_cache_conversation_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Creates and seeds a brand-new conversation thread ready for an independent discussion ("seed & wait").

    Unlike `fork_conversation`, which copies or summarizes an existing thread turn, this helper is called
    directly by agents (Head Agent or `spawn_subagent` workers) to spin up fresh, focused context windows
    (e.g., splitting a multi-category email sweep into dedicated per-topic conversations) without executing
    an immediate LLM turn.

    Persistence guarantees:
      1. Writes the conversation row to `chats.db` with `title_source="manual"` so Turn-1 auto-titling never
         overwrites the agent-curated category title.
      2. Appends an optional live `target_section` directory tree snapshot and runs a deterministic path/wiki-link
         lint pass (`verify_context_brief_paths`), appending `[SYSTEM WARNING: ...]` if any phantom files appear.
      3. Logs the seeded brief with `agent="branch_context"` so future `Distill & Merge` or auto-titling
         treats it identically to a Context Brief rather than an ordinary assistant turn.
      4. Seeds LangGraph's `SqliteSaver` (`memory.sqlite`) via `seed_langgraph_thread_from_messages` so the
         user's first prompt inside the new conversation has full context immediately.
    """
    from nexus.shared_tools.vault_reader import get_directory_tree, verify_context_brief_paths

    cleaned_brief = (context_brief or "").strip()
    if not cleaned_brief:
        raise ValueError("context_brief cannot be empty when spawning a conversation.")

    cleaned_title = (title or "").strip() or "New Discussion"

    # Run deterministic filesystem verification on the caller-authored brief before appending directory snapshots.
    missing_files = verify_context_brief_paths(cleaned_brief)
    warning_block: Optional[str] = None
    if missing_files:
        warning_block = (
            f"[SYSTEM WARNING: The following files referenced in this brief do not exist on disk: "
            f"{', '.join(missing_files)}. Verify actual files via get_directory_structure before proceeding.]"
        )

    # Optionally snapshot a target Vault section's live file tree so Turn 1 sees exact on-disk filenames immediately.
    clean_section: Optional[str] = None
    section_block: Optional[str] = None
    section_warning: Optional[str] = None
    if target_section and target_section.strip():
        raw_section = target_section.strip().replace("\\", "/")
        if raw_section.startswith("Vault/"):
            raw_section = raw_section[len("Vault/"):]
        clean_section = raw_section.rstrip("/") or None
        if clean_section:
            tree_output = get_directory_tree(path=clean_section, show_files=True)
            if tree_output.startswith("Error:"):
                section_warning = (
                    f"[SYSTEM WARNING: Could not snapshot target_section '{target_section}': {tree_output}]"
                )
                section_block = section_warning
            else:
                section_block = (
                    f"### 📁 Target Section Directory Snapshot (`{clean_section}`)\n"
                    f"```\n{tree_output}\n```"
                )

    # Resolve whether this new conversation should nest as a child branch in `ChatSidebar` or start at root level
    parent_conv = get_conversation(parent_conversation_id) if (nest_under_parent and parent_conversation_id) else None

    if parent_conv is not None and parent_conversation_id:
        display_title = cleaned_title if cleaned_title.startswith("🌿") else f"🌿 {cleaned_title}"
        # Anchor the child branch to the caller's latest committed message if no explicit message ID was supplied
        resolved_parent_msg_id = parent_message_id
        if resolved_parent_msg_id is None:
            parent_history = get_chat_history(parent_conversation_id)
            if parent_history:
                resolved_parent_msg_id = parent_history[-1].get("id")

        effective_parent_id: Optional[str] = parent_conversation_id
        effective_branch_mode: Optional[str] = "tangent"
        new_conv_id = create_branch_conversation(
            title=display_title,
            parent_conversation_id=parent_conversation_id,
            parent_message_id=resolved_parent_msg_id,
            branch_mode=effective_branch_mode,
            # Mark agent-curated category names as `"manual"` so Turn-1 auto-titling preserves them
            title_source="manual",
            # Inherit parent conversation's remembered model for seamless cache/provider continuity
            last_model_tier=parent_conv.get("last_model_tier"),
            last_model_name=parent_conv.get("last_model_name"),
        )
        parent_label = parent_conv.get("title") or "Parent Chat"
        formatted_brief = (
            cleaned_brief
            if cleaned_brief.startswith("### ")
            else f"### 🌿 Context Brief *(spawned from \"{parent_label}\")*\n\n{cleaned_brief}"
        )
    else:
        display_title = cleaned_title
        effective_parent_id = None
        resolved_parent_msg_id = None
        effective_branch_mode = None
        new_conv_id = create_conversation(
            title=display_title,
            # Preserve the explicit topic title across subsequent user turns
            title_source="manual",
        )
        formatted_brief = (
            cleaned_brief
            if cleaned_brief.startswith("### ")
            else f"### 📋 Context Brief — *{display_title}*\n\n{cleaned_brief}"
        )

    if section_block:
        formatted_brief = f"{formatted_brief}\n\n{section_block}"

    # Inherit external captures from the spawning conversation (including CLI/eval `"nexus_primary"` runs)
    # BEFORE logging the seeded brief so Turn 1 receives a lightweight manifest of inherited `cache://` handles.
    cache_source_id = (source_cache_conversation_id or parent_conversation_id or "").strip() or None
    inherited_captures = inherit_captures(cache_source_id, new_conv_id) if cache_source_id else 0
    if inherited_captures > 0:
        cache_block = (
            f"### 📦 Inherited External Captures ({inherited_captures})\n"
            f"{format_captures_manifest(new_conv_id)}"
        )
        formatted_brief = f"{formatted_brief}\n\n{cache_block}"

    if warning_block:
        formatted_brief = f"{formatted_brief}\n\n{warning_block}"

    # Persist the brief as a synthetic `branch_context` entry in `chats.db` so UI displays it cleanly on open
    log_message(
        role="assistant",
        content=formatted_brief,
        agent="branch_context",
        domain=None,
        confidence=1.0,
        trace=[],
        conversation_id=new_conv_id,
    )

    # Read back persisted history and hydrate LangGraph `memory.sqlite` checkpointer for immediate Turn-1 continuity
    seeded_history = get_chat_history(new_conv_id)
    seed_langgraph_thread_from_messages(new_conv_id, seeded_history)
    new_conv = get_conversation(new_conv_id)

    return {
        "conversation_id": new_conv_id,
        "title": display_title,
        "conversation": new_conv,
        "messages": seeded_history,
        "parent_conversation_id": effective_parent_id,
        "parent_message_id": resolved_parent_msg_id,
        "branch_mode": effective_branch_mode,
        "target_section": clean_section,
        "section_warning": section_warning,
        "missing_files": missing_files,
        "warning_block": warning_block,
        "inherited_captures": inherited_captures,
    }


def distill_and_merge_branch(
    branch_conversation_id: str,
    user_guidance: Optional[str] = None,
    model_tier: str = "low",
) -> dict[str, Any]:
    """
    Distills a child branch conversation and merges its synthesized findings back into the parent conversation.

    Parameters:
      branch_conversation_id: UUID of the child branch conversation to distill.
      user_guidance: Optional user instructions for what to highlight or preserve in the merge.
      model_tier: Model tier used to synthesize the distillation (`'low'`, `'medium'`, `'strong'`).

    Returns:
      Dictionary with merge metadata, `parent_conversation_id`, `merged_message_id`, and `distilled_content`.
    """
    branch_conv = get_conversation(branch_conversation_id)
    if not branch_conv:
        raise ValueError(f"Branch conversation '{branch_conversation_id}' not found.")

    parent_id = branch_conv.get("parent_conversation_id")
    if not parent_id:
        raise ValueError(f"Conversation '{branch_conversation_id}' is a root conversation and has no parent to merge into.")

    parent_conv = get_conversation(parent_id)
    if not parent_conv:
        raise ValueError(f"Parent conversation '{parent_id}' no longer exists.")

    branch_history = get_chat_history(branch_conversation_id)
    if not branch_history:
        raise ValueError(f"Branch conversation '{branch_conversation_id}' has no messages to distill.")

    branch_title = branch_conv.get("title") or "Branch"
    parent_title = parent_conv.get("title") or "Parent Chat"

    distilled_body = synthesize_branch_distillation(
        branch_title=branch_title,
        parent_title=parent_title,
        branch_messages=branch_history,
        user_guidance=user_guidance,
        model_tier=model_tier,
    )

    merged_markdown = (
        f"### 🌿 Distilled Merge from Branch: *{branch_title}*\n\n"
        f"{distilled_body}"
    )

    # 1. Append the distilled merge message into the parent conversation in `chats.db`
    merged_msg_id = log_message(
        role="assistant",
        content=merged_markdown,
        agent="branch_merge",
        domain=None,
        confidence=1.0,
        trace=[],
        conversation_id=parent_id,
    )

    # 2. Synchronize the parent conversation's LangGraph checkpointer (`memory.sqlite`)
    append_message_to_langgraph_thread(parent_id, role="assistant", content=merged_markdown)

    # 3. Record `merged_at` timestamp on the child branch conversation row
    merged_at = mark_branch_merged(branch_conversation_id)

    return {
        "status": "merged",
        "branch_conversation_id": branch_conversation_id,
        "parent_conversation_id": parent_id,
        "merged_at": merged_at,
        "merged_message_id": merged_msg_id,
        "distilled_content": merged_markdown,
    }

