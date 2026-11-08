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

from nexus.agent.graph import extract_message_text, nexus_graph
from nexus.core.chats_db import (
    create_branch_conversation,
    get_chat_history,
    get_conversation,
    log_message,
    mark_branch_merged,
)
from nexus.core.constants import get_chat_model, resolve_model_config


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
    Seeds the LangGraph SQLite checkpointer (`memory.sqlite`) for `conversation_id` with initial messages.

    Why this exists:
      When a child branch is created in `chats.db`, LangGraph's `SqliteSaver` has no checkpoint for the new
      `conversation_id` yet. Calling `nexus_graph.update_state` writes an initial checkpoint containing the
      seeded `HumanMessage` / `AIMessage` history so the very first turn in the child branch has full context.

    Parameters:
      conversation_id: UUID of the target conversation thread.
      messages: Chronological list of `chats.db` message dicts to seed into LangGraph state.
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
    if lc_messages and isinstance(lc_messages[0], AIMessage):
        lc_messages.insert(
            0,
            HumanMessage(content="[Session initialized from parent conversation branch context]"),
        )

    config = {"configurable": {"thread_id": conversation_id, "conversation_id": conversation_id}}
    try:
        nexus_graph.update_state(config, {"messages": lc_messages})
    except Exception:
        # Non-fatal guard: if checkpointer state update fails, chat history in chats.db remains authoritative
        pass


def append_message_to_langgraph_thread(conversation_id: str, role: str, content: str) -> None:
    """
    Appends a single message (such as a Distilled Branch Merge) into an existing thread's LangGraph state.

    Parameters:
      conversation_id: UUID of the target parent conversation thread.
      role: Either `'user'` or `'assistant'`.
      content: Markdown body to append into the thread's active context window.
    """
    if not conversation_id or not content:
        return

    lc_msg: BaseMessage = HumanMessage(content=content) if role == "user" else AIMessage(content=content)
    config = {"configurable": {"thread_id": conversation_id, "conversation_id": conversation_id}}
    try:
        nexus_graph.update_state(config, {"messages": [lc_msg]})
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

    child_conv_id = create_branch_conversation(
        title=branch_title,
        parent_conversation_id=parent_conversation_id,
        parent_message_id=resolved_fork_msg_id,
        branch_mode=effective_mode,
    )

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
