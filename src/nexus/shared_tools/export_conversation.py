"""
export_conversation.py — Universal JSON/JSONL conversation transcript exporter.

Converts conversation logs from JSON Lines (.jsonl), JSON files (.json), or
agent/IDE conversation stores into clean, human-readable Markdown or Obsidian notes.

Supported Input Formats:
  - JSON Lines (.jsonl) with one message/step per line
  - JSON file (.json) containing an array of messages: [{"role": "user", "content": "..."}, ...]
  - JSON file (.json) with nested structure: {"messages": [...]}, {"steps": [...]}, {"history": [...]}
  - ChatGPT export JSON (mapping-based tree)
  - Antigravity IDE brain transcripts (auto-resolved by ID or --latest / --list)
  - Stdin stream (using '-' as the file path)
"""
import argparse
import datetime
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class ChatMessage:
    role: str  # 'user', 'assistant', 'system', 'tool'
    content: str
    timestamp: str = ""
    thinking: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


def clean_text_content(raw: Any) -> str:
    """Normalize and clean string content, stripping IDE framing tags if present."""
    if raw is None:
        return ""
    if isinstance(raw, list):
        # Handle list of content parts (OpenAI / Anthropic format)
        parts = []
        for p in raw:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict):
                if p.get("type") == "text" and "text" in p:
                    parts.append(p["text"])
                elif "content" in p:
                    parts.append(str(p["content"]))
        raw_str = "\n".join(parts)
    elif isinstance(raw, dict):
        raw_str = raw.get("text") or raw.get("content") or json.dumps(raw, indent=2)
    else:
        raw_str = str(raw)

    # Strip Antigravity IDE wrappers if present
    match = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw_str, re.DOTALL)
    if match:
        return match.group(1).strip()

    cleaned = re.sub(
        r"<(ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>.*?</\1>",
        "",
        raw_str,
        flags=re.DOTALL,
    )
    return cleaned.strip()


def normalize_role(role_raw: str, source_raw: str = "", type_raw: str = "") -> str:
    """Map arbitrary schema role/source/type fields to standard roles."""
    val = f"{role_raw} {source_raw} {type_raw}".lower()

    if any(k in val for k in ("user", "human", "user_explicit", "user_input")):
        return "user"
    if any(k in val for k in ("assistant", "model", "ai", "bot", "planner_response", "assistant_response")):
        return "assistant"
    if any(k in val for k in ("system", "developer", "instruction", "checkpoint")):
        return "system"
    if any(k in val for k in ("tool", "function", "tool_response")):
        return "tool"
    return "assistant" if "planner" in val else "user"


def parse_record_to_message(record: Dict[str, Any]) -> Optional[ChatMessage]:
    """Extract standard ChatMessage from arbitrary JSON record/dict."""
    if not isinstance(record, dict):
        return None

    role_raw = record.get("role") or record.get("speaker") or record.get("author") or record.get("from") or ""
    source_raw = record.get("source") or ""
    type_raw = record.get("type") or record.get("step_type") or ""

    # Content extraction
    content_raw = (
        record.get("content")
        or record.get("text")
        or record.get("message")
        or record.get("prompt")
        or record.get("response")
        or record.get("body")
        or record.get("val")
    )

    # ChatGPT mapping node structure
    if not content_raw and "message" in record and isinstance(record["message"], dict):
        msg_dict = record["message"]
        author = msg_dict.get("author", {})
        role_raw = author.get("role", role_raw)
        msg_content = msg_dict.get("content", {})
        if isinstance(msg_content, dict) and "parts" in msg_content:
            content_raw = "\n".join(str(p) for p in msg_content["parts"])
        timestamp = msg_dict.get("create_time") or ""

    clean_content = clean_text_content(content_raw)
    role = normalize_role(str(role_raw), str(source_raw), str(type_raw))

    # Timestamp
    timestamp = (
        record.get("created_at")
        or record.get("timestamp")
        or record.get("time")
        or record.get("date")
        or ""
    )
    if isinstance(timestamp, (int, float)):
        try:
            timestamp = datetime.datetime.fromtimestamp(timestamp).isoformat()
        except Exception:
            timestamp = str(timestamp)

    # Thinking & Tools
    thinking = str(record.get("thinking") or record.get("thoughts") or record.get("reasoning") or "")
    tool_calls = record.get("tool_calls") or record.get("function_call") or record.get("actions") or []
    if isinstance(tool_calls, dict):
        tool_calls = [tool_calls]

    # Ignore purely empty non-tool system steps
    if not clean_content and not thinking and not tool_calls:
        return None

    return ChatMessage(
        role=role,
        content=clean_content,
        timestamp=str(timestamp),
        thinking=thinking,
        tool_calls=tool_calls if isinstance(tool_calls, list) else [],
    )


def parse_jsonl_stream(lines: Iterator[str]) -> List[ChatMessage]:
    """Parse line-by-line JSONL stream into list of ChatMessages."""
    messages = []
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        try:
            record = json.loads(line_str)
            msg = parse_record_to_message(record)
            if msg:
                messages.append(msg)
        except json.JSONDecodeError:
            continue
    return messages


def parse_json_data(data: Any) -> List[ChatMessage]:
    """Parse top-level JSON data (list, dict, tree) into list of ChatMessages."""
    messages = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                msg = parse_record_to_message(item)
                if msg:
                    messages.append(msg)
    elif isinstance(data, dict):
        # 1. ChatGPT export tree
        if "mapping" in data and isinstance(data["mapping"], dict):
            for node_id, node in data["mapping"].items():
                if isinstance(node, dict) and node.get("message"):
                    msg = parse_record_to_message(node)
                    if msg:
                        messages.append(msg)
        # 2. Wrapped messages array: {"messages": [...]} or {"steps": [...]} or {"history": [...]}
        else:
            for key in ("messages", "steps", "history", "chat_history", "data", "records", "conversation"):
                if key in data and isinstance(data[key], list):
                    return parse_json_data(data[key])
            # Single object message fallback
            msg = parse_record_to_message(data)
            if msg:
                messages.append(msg)

    return messages


def load_conversation_source(source_path_or_id: Optional[str] = None) -> Tuple[str, List[ChatMessage], str]:
    """
    Load conversation messages from a file path, JSON/JSONL stream, or conversation ID.
    Returns: (title_or_id, messages, source_description)
    """
    brain_dir = Path.home() / ".gemini" / "antigravity-ide" / "brain"

    # Stdin stream
    if source_path_or_id == "-":
        lines = sys.stdin.readlines()
        raw_text = "".join(lines).strip()
        if raw_text.startswith("{") and not raw_text.startswith("{\n") and "\n" not in raw_text:
            data = json.loads(raw_text)
            messages = parse_json_data(data)
        elif raw_text.startswith("["):
            data = json.loads(raw_text)
            messages = parse_json_data(data)
        else:
            messages = parse_jsonl_stream(iter(lines))
        return "stdin_stream", messages, "stdin"

    # File or Directory path passed
    if source_path_or_id:
        p = Path(source_path_or_id).expanduser()
        if p.is_file():
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read().strip()
            if p.suffix.lower() == ".jsonl":
                messages = parse_jsonl_stream(iter(content.splitlines()))
            else:
                try:
                    data = json.loads(content)
                    messages = parse_json_data(data)
                except json.JSONDecodeError:
                    messages = parse_jsonl_stream(iter(content.splitlines()))
            return p.stem, messages, str(p.resolve())

        if p.is_dir():
            full = p / ".system_generated" / "logs" / "transcript_full.jsonl"
            compact = p / ".system_generated" / "logs" / "transcript.jsonl"
            target = full if full.exists() else (compact if compact.exists() else None)
            if target:
                with open(target, "r", encoding="utf-8", errors="ignore") as f:
                    messages = parse_jsonl_stream(f)
                return p.name, messages, str(target.resolve())

    # Fallback to Antigravity Brain resolver if UUID, prefix, or latest
    if brain_dir.exists():
        target_dir: Optional[Path] = None
        convo_id = "latest"

        if not source_path_or_id or source_path_or_id.lower() == "latest":
            candidates = []
            for entry in brain_dir.iterdir():
                if not entry.is_dir():
                    continue
                log_full = entry / ".system_generated" / "logs" / "transcript_full.jsonl"
                log_compact = entry / ".system_generated" / "logs" / "transcript.jsonl"
                target_log = log_full if log_full.exists() else (log_compact if log_compact.exists() else None)
                if target_log:
                    candidates.append((target_log.stat().st_mtime, entry.name, target_log))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                convo_id, target_file = candidates[0][1], candidates[0][2]
                with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                    messages = parse_jsonl_stream(f)
                return convo_id, messages, str(target_file.resolve())

        elif source_path_or_id:
            # Exact UUID
            exact = brain_dir / source_path_or_id
            if exact.is_dir():
                full = exact / ".system_generated" / "logs" / "transcript_full.jsonl"
                compact = exact / ".system_generated" / "logs" / "transcript.jsonl"
                target_log = full if full.exists() else (compact if compact.exists() else None)
                if target_log:
                    with open(target_log, "r", encoding="utf-8", errors="ignore") as f:
                        messages = parse_jsonl_stream(f)
                    return source_path_or_id, messages, str(target_log.resolve())

            # Prefix match
            matches = []
            for entry in brain_dir.iterdir():
                if entry.is_dir() and entry.name.startswith(source_path_or_id):
                    log_full = entry / ".system_generated" / "logs" / "transcript_full.jsonl"
                    log_compact = entry / ".system_generated" / "logs" / "transcript.jsonl"
                    target_log = log_full if log_full.exists() else (log_compact if log_compact.exists() else None)
                    if target_log:
                        matches.append((entry.name, target_log))
            if len(matches) == 1:
                convo_id, target_file = matches[0][0], matches[0][1]
                with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                    messages = parse_jsonl_stream(f)
                return convo_id, messages, str(target_file.resolve())
            elif len(matches) > 1:
                raise ValueError(f"Ambiguous ID prefix '{source_path_or_id}'. Matches: {[m[0] for m in matches[:5]]}")

    raise FileNotFoundError(f"Could not find or resolve conversation source: '{source_path_or_id}'")


def format_to_markdown(
    title_or_id: str,
    messages: List[ChatMessage],
    source_desc: str = "",
    include_thinking: bool = False,
    include_tools: bool = True,
    vault_format: bool = False,
) -> str:
    """Render a list of normalized ChatMessages to Markdown."""
    lines = []
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"Chat - {title_or_id[:12]}"

    first_user_prompt = ""
    for m in messages:
        if m.role == "user" and m.content:
            first_user_prompt = m.content[:40].replace("\n", " ").strip()
            break

    if vault_format:
        lines.append("---")
        lines.append(f'aliases: ["{title}", "Convo {title_or_id[:8]}"]')
        lines.append("tags: [ai, chat, conversation, logs, capture]")
        lines.append("type: capture")
        lines.append(f"source_id: {title_or_id}")
        lines.append(f"exported_at: {now_str}")
        lines.append("---\n")

    lines.append(f"# Conversation: `{title_or_id}`\n")
    if source_desc:
        lines.append(f"> **Source:** `{source_desc}`  ")
    lines.append(f"> **Total Messages:** {len(messages)}  \n")
    lines.append("---\n")

    for msg in messages:
        time_tag = f" `({msg.timestamp})`" if msg.timestamp else ""

        if msg.role == "user":
            lines.append(f"## 👤 User{time_tag}\n")
            lines.append(f"{msg.content}\n\n---\n")

        elif msg.role == "assistant":
            lines.append(f"## 🤖 Assistant{time_tag}\n")
            if include_thinking and msg.thinking:
                lines.append("<details><summary><b>Thought Process</b></summary>\n")
                lines.append(f"\n{msg.thinking}\n")
                lines.append("</details>\n")

            if msg.content:
                lines.append(f"{msg.content}\n")

            if include_tools and msg.tool_calls:
                lines.append("\n<details><summary><b>Tool Executions</b></summary>\n")
                for tc in msg.tool_calls:
                    name = tc.get("name", tc.get("tool", "tool"))
                    args = tc.get("args") or tc.get("arguments") or {}
                    lines.append(f"- **`{name}`**")
                    if isinstance(args, dict) and args:
                        arg_summary = ", ".join(f"`{k}`: {json.dumps(v)[:50]}" for k, v in list(args.items())[:3])
                        lines.append(f"  - Arguments: {arg_summary}")
                lines.append("\n</details>\n")

            lines.append("\n---\n")

        elif msg.role == "system":
            lines.append(f"## ⚙️ System{time_tag}\n")
            lines.append(f"{msg.content}\n\n---\n")

        elif msg.role == "tool":
            lines.append(f"## 🛠️ Tool Result{time_tag}\n")
            lines.append(f"```text\n{msg.content}\n```\n\n---\n")

    return "\n".join(lines)


def list_conversations(limit: int = 15) -> List[Dict[str, Any]]:
    """Helper to list known conversation logs from local brain storage."""
    brain_dir = Path.home() / ".gemini" / "antigravity-ide" / "brain"
    if not brain_dir.exists():
        return []

    results = []
    for entry in brain_dir.iterdir():
        if not entry.is_dir():
            continue
        log_file = entry / ".system_generated" / "logs" / "transcript.jsonl"
        if not log_file.exists():
            log_file = entry / ".system_generated" / "logs" / "transcript_full.jsonl"
        if not log_file.exists():
            continue

        mtime = log_file.stat().st_mtime
        preview = ""
        msg_count = 0
        created_at = ""

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        msg_count += 1
                        if not preview and normalize_role(data.get("role", ""), data.get("source", ""), data.get("type", "")) == "user":
                            preview = clean_text_content(data.get("content", ""))[:90].replace("\n", " ")
                        if not created_at and data.get("created_at"):
                            created_at = data.get("created_at")
                    except Exception:
                        continue
        except Exception:
            continue

        results.append({
            "id": entry.name,
            "mtime": mtime,
            "created_at": created_at or datetime.datetime.fromtimestamp(mtime).isoformat(),
            "messages": msg_count,
            "preview": preview or "(no user prompt found)",
            "path": str(log_file),
        })

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results[:limit]


def export_conversation_cli() -> None:
    parser = argparse.ArgumentParser(
        description="Universal JSON / JSONL conversation transcript exporter and Markdown formatter."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Path to .json / .jsonl file, '-' for stdin, conversation UUID / prefix, or omit for latest.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Export the most recent conversation transcript.",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available local conversation transcripts.",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output Markdown file path (defaults to transcript_<id>.md).",
    )
    parser.add_argument(
        "--vault-inbox", "-v",
        action="store_true",
        help="Save directly into Vault/0. Inbox/ with Obsidian YAML frontmatter.",
    )
    parser.add_argument(
        "--include-thinking", "-t",
        action="store_true",
        help="Include model thinking / internal thought traces in an accordion block.",
    )
    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Omit tool execution logs.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print rendered markdown directly to stdout instead of saving to disk.",
    )

    args = parser.parse_args()

    if args.list:
        recents = list_conversations(15)
        print(f"\n{'=' * 80}")
        print(f"LOCAL CONVERSATION TRANSCRIPTS ({len(recents)} found)")
        print(f"{'=' * 80}")
        for r in recents:
            print(f"ID:       {r['id']}")
            print(f"Time:     {r['created_at']} ({r['messages']} steps)")
            print(f"Preview:  {r['preview']}")
            print(f"{'-' * 80}")
        return

    target = "latest" if args.latest else (args.source or "latest")

    try:
        title_or_id, messages, source_desc = load_conversation_source(target)
        rendered = format_to_markdown(
            title_or_id=title_or_id,
            messages=messages,
            source_desc=source_desc,
            include_thinking=args.include_thinking,
            include_tools=not args.no_tools,
            vault_format=args.vault_inbox,
        )

        if args.stdout:
            print(rendered)
            return

        if args.output:
            out_file = Path(args.output)
        elif args.vault_inbox:
            safe_title = re.sub(r'[\\/*?:"<>|]', "", title_or_id[:20]).strip()
            out_file = Path("Vault") / "0. Inbox" / f"Chat - {safe_title}.md"
        else:
            out_file = Path(f"transcript_{title_or_id[:8]}.md")

        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(rendered)

        print(f"Successfully exported {len(messages)} messages to: {out_file.resolve()}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    export_conversation_cli()
