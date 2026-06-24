"""
api.py — Public entry points for the Librarian Agent.
"""
import re
import json
import sys
from pathlib import Path
from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage

from nexus.agents.librarian.graph import app, librarian_tracer, _build_system_prompt

def log_query_run(query: str, final_state=None, error=None):
    """
    Logs the query execution details to engine/logs/run_logs.jsonl.
    """
    timestamp = datetime.utcnow().isoformat() + "Z"
    error_str = str(error) if error else None

    if error:
        status = "error"
    elif final_state and "messages" in final_state:
        last_content = final_state["messages"][-1].content if final_state["messages"] else ""
        status = "not_found" if "[Not Found]" in last_content else "success"
    else:
        status = "error"

    cited_sources = []
    tool_calls = []

    if final_state and "messages" in final_state:
        messages = final_state["messages"]
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    t_call = {
                        "tool": tc.get("name"),
                        "args": tc.get("args")
                    }
                    tool_calls.append(t_call)

                    if tc.get("name") == "read_note":
                        note_path = tc.get("args", {}).get("note_path")
                        if note_path:
                            cited_sources.append(note_path)
                    elif tc.get("name") == "read_toc":
                        cited_sources.append("Table of Contents.md")
                    elif tc.get("name") == "get_vault_structure":
                        vs_path = tc.get("args", {}).get("path")
                        cited_sources.append(f"[structure] {vs_path or 'root'}")

        if messages:
            last_msg = messages[-1]
            if last_msg and hasattr(last_msg, 'content') and last_msg.content:
                content = last_msg.content
                sources_match = re.search(r'(?:\[Sources\]|Sources:)(.*)', content, re.IGNORECASE | re.DOTALL)
                if sources_match:
                    sources_text = sources_match.group(1)
                    lines = sources_text.strip().split('\n')
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        if line.lower() == '(none)':
                            continue
                        line = re.sub(r'^[\-\*\+\d\.\s]+', '', line).strip()
                        wiki_match = re.search(r'\[\[(.*?)\]\]', line)
                        if wiki_match:
                            cited_sources.append(wiki_match.group(1))
                        else:
                            link_match = re.search(r'\[.*?\]\((.*?)\)', line)
                            if link_match:
                                cited_sources.append(link_match.group(1))
                            else:
                                if line:
                                    cited_sources.append(line)

    unique_sources = []
    seen = set()
    for src in cited_sources:
        src_clean = src.strip().strip('`"\'').replace('\\', '/')
        if src_clean and src_clean not in seen:
            seen.add(src_clean)
            unique_sources.append(src_clean)

    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if final_state and "messages" in final_state:
        for msg in final_state["messages"]:
            usage = getattr(msg, 'usage_metadata', None)
            if usage:
                token_usage["prompt_tokens"] += usage.get("input_tokens", 0)
                token_usage["completion_tokens"] += usage.get("output_tokens", 0)
                token_usage["total_tokens"] += usage.get("total_tokens", 0)

    log_entry = {
        "timestamp": timestamp,
        "query": query,
        "status": status,
        "cited_sources": unique_sources,
        "token_usage": token_usage,
        "errors": error_str,
        "tool_calls": tool_calls
    }

    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "run_logs.jsonl"

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        sys.stderr.write(f"Failed to write query log: {e}\n")


def ask_librarian(query: str, filters: dict = None, thread_id: str = "librarian_primary") -> str:
    """
    Entry point for the vault reader agent. Returns a string response.
    """
    librarian_tracer.agent_start(f"Query: {query[:80]}")
    try:
        final_state = execute_vault_query(query, thread_id=thread_id)
        last_message = final_state["messages"][-1]
        librarian_tracer.agent_end()
        return last_message.content
    except Exception as e:
        librarian_tracer.info(f"❌ Error: {e}")
        return f"❌ Agent encountered an error: {e}"


def execute_vault_query(query: str, thread_id: str = None):
    """
    Executes a query against the vault reader agent and returns the final state.
    This is designed to be called by programmatic interfaces like the Telegram bot.
    """
    system_prompt = _build_system_prompt()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query)
    ]
    
    config = {}
    if thread_id:
        config = {"configurable": {"thread_id": thread_id}}
        
    try:
        final_state = app.invoke({"messages": messages}, config=config)
        log_query_run(query, final_state=final_state)
        return final_state
    except Exception as e:
        log_query_run(query, error=e)
        raise e
