"""summarizer.py — Shared LangGraph node that compresses long chat history into a summary and archives pruned messages."""
import time
from pathlib import Path
from langchain_core.messages import RemoveMessage, HumanMessage, AIMessage, ToolMessage

def summarize_conversation(
    state: dict, 
    llm, 
    archive_path: Path, 
    max_messages: int = 30, 
    keep_messages: int = 10
) -> dict:
    """
    Shared LangGraph node function for compressing conversation history.
    - state: The current LangGraph state, containing "messages" and optionally "summary"
    - llm: A chat model instance used to generate the summary
    - archive_path: Path to append the archived messages to
    - max_messages: The threshold at which pruning triggers
    - keep_messages: The number of recent messages to retain
    
    Returns a dict with state updates if pruning occurred, otherwise an empty dict.
    """
    messages = state.get("messages", [])
    if len(messages) <= max_messages:
        return {}
    
    # Prune oldest messages while snapping the cut point to a HumanMessage boundary so the retained
    # slice never starts mid-turn with an orphaned ToolMessage or AIMessage(tool_calls).
    target_cut = len(messages) - keep_messages
    cut_idx = target_cut
    # Walk forward from target_cut to find the next HumanMessage boundary
    while cut_idx < len(messages) and not isinstance(messages[cut_idx], HumanMessage):
        cut_idx += 1
    # If no HumanMessage was found after target_cut (e.g. a single massive 30-step turn), walk backward
    # to the start of the current turn's HumanMessage so we keep the active turn intact.
    if cut_idx >= len(messages):
        cut_idx = target_cut
        while cut_idx > 0 and not isinstance(messages[cut_idx], HumanMessage):
            cut_idx -= 1
    if cut_idx <= 0:
        return {}

    messages_to_prune = messages[:cut_idx]
    
    # Format messages for the archive
    archive_lines = []
    for m in messages_to_prune:
        if isinstance(m, HumanMessage):
            role = "Human"
        elif isinstance(m, AIMessage):
            role = "AI"
        elif isinstance(m, ToolMessage):
            role = f"Tool ({m.name})"
        else:
            role = type(m).__name__
            
        content = m.text if hasattr(m, "text") and isinstance(m.text, str) else (m.content if isinstance(m.content, str) else str(m.content))
        archive_lines.append(f"**{role}**: {content}")
        
    archive_text = "\n\n".join(archive_lines)
    
    # Append to the markdown archive
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(archive_path, "a", encoding="utf-8") as f:
        f.write(f"\n\n## Archive at {timestamp}\n\n{archive_text}\n")
        
    # Generate new summary
    existing_summary = state.get("summary", "")
    prompt = (
        "Summarize the following conversation history. "
        "Focus on key decisions, files modified, tools used, and user preferences expressed. "
        "Be extremely concise and prioritize token density. "
    )
    if existing_summary:
        prompt += f"\n\nExisting Summary to incorporate:\n{existing_summary}"
        
    prompt += f"\n\nConversation to summarize:\n{archive_text}"
    
    response = llm.invoke([HumanMessage(content=prompt)])
    new_summary = response.text if hasattr(response, "text") and isinstance(response.text, str) else str(response.content)
    
    return {
        "summary": new_summary,
        "messages": [RemoveMessage(id=m.id) for m in messages_to_prune if m.id]
    }
