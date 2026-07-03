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
    
    # Prune oldest messages
    num_to_remove = len(messages) - keep_messages
    messages_to_prune = messages[:num_to_remove]
    
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
            
        content = m.content if isinstance(m.content, str) else str(m.content)
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
    new_summary = response.content
    
    return {
        "summary": new_summary,
        "messages": [RemoveMessage(id=m.id) for m in messages_to_prune if m.id]
    }
