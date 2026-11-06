"""
export_conversation.py — Universal Agent Conversation Exporter & Obsidian Note Generator.

========================================================================================
ARCHITECTURAL OVERVIEW & WHY TURN COALESCING IS REQUIRED
========================================================================================
Autonomous agentic coding harnesses (such as Antigravity, Claude Code, OpenAI Codex, or
NexusAgent) record granular step-by-step telemetry in JSON Lines (.jsonl). In these raw
trajectories, every atomic sub-action is serialized as an independent line:
  1. USER_INPUT (Prompt from user)
  2. PLANNER_RESPONSE (Model deciding to call a tool, content is often empty, tool_calls populated)
  3. GENERIC / TOOL_RESPONSE (Tool stdout, file reads, terminal outputs, sometimes thousands of lines)
  4. PLANNER_RESPONSE (Model deciding next action)
  ...
  N. PLANNER_RESPONSE (Final synthesis delivered to the user)

NAIVE PARSING FAILURE MODE (TRANSCRIPT BLOAT):
If an exporter naively treats every "source: MODEL" or "type: PLANNER_RESPONSE" entry as an
independent assistant message, a 3-turn user conversation involving 100 tool calls will generate
over 200 fragmented "## 🤖 Assistant" headers, dumping raw terminal outputs (like 500-line diffs
and directory listings) directly into the reading stream. The resulting markdown file inflates to
over 500 KB, drowning the human in repetitive noise and destroying readability in knowledge vaults.

THE SOLUTION — TURN COALESCING:
This module implements deterministic "Turn Coalescing":
  1. Aggregation: Groups all intermediate tool invocations, environment feedbacks, and thought
     traces between two User prompts into a single logical "Conversation Turn".
  2. Semantic Role Resolution: Distinguishes actual tool execution results (`type: GENERIC`)
     from conversational model utterances, preventing tool stdout from masquerading as assistant text.
  3. Action Summarization: Condenses dozens or hundreds of tool calls into an expandable,
     ergonomic `<details><summary>🛠️ Tool Executions (N actions)</summary>` block with clean,
     informative one-liners (e.g. `run_command` with summary, `read_file` with line range).
  4. Dialogue Clarity: Surfaces the user's actual prompt (unwrapped from IDE context wrappers)
     and the assistant's final synthesized response prominently for rapid comprehension.
  5. Raw Escape Hatch: Provides `--raw` mode when low-level, step-by-step diagnostic forensics
     are specifically needed.
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

# Ensure UTF-8 output on Windows terminals to prevent charmap codec crashes on emojis
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class ChatMessage:
    """Represents an atomic step or message extracted from any conversation source."""

    role: str  # 'user', 'assistant', 'system', 'tool'
    content: str
    timestamp: str = ""
    thinking: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    raw_type: str = ""
    raw_source: str = ""


@dataclass
class ConversationTurn:
    """
    Represents a coalesced, human-centric conversation turn consisting of:
    - Exactly one user prompt (or session initiation)
    - The assistant's conversational response(s)
    - All intermediate tool actions executed during the turn
    - Thinking traces and system annotations
    """

    turn_index: int
    user_prompt: str = ""
    user_timestamp: str = ""
    assistant_response: str = ""
    assistant_timestamp: str = ""
    thinking_traces: List[str] = field(default_factory=list)
    tool_actions: List[str] = field(default_factory=list)
    system_notes: List[str] = field(default_factory=list)


def clean_text_content(raw: Any) -> str:
    """
    Normalize and clean string content, stripping IDE framing tags, context summaries,
    and metadata wrappers while preserving the user's actual prompt text.
    """
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

    # 1. Extract inner user request if wrapped in Antigravity <USER_REQUEST> tags
    match = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw_str, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 2. Strip IDE framing artifacts if <USER_REQUEST> tags were omitted
    cleaned = raw_str
    cleaned = re.sub(r"<CONTEXT_SUMMARY>.*?</CONTEXT_SUMMARY>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<(ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>.*?</\1>", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<(identity|guidelines|user_rules|slash_commands|skills)>.*?</\1>", "", cleaned, flags=re.DOTALL)

    return cleaned.strip()


def normalize_role(role_raw: str, source_raw: str = "", type_raw: str = "") -> str:
    """
    Map arbitrary schema role/source/type fields to canonical roles:
    'user', 'assistant', 'system', 'tool'.

    RESOLUTION PRECEDENCE:
    1. User signals: USER_INPUT, USER_EXPLICIT, role 'user', 'human'
    2. Tool result signals: GENERIC (Antigravity tool stdout), TOOL_RESPONSE, role 'tool', 'function'
    3. System signals: SYSTEM_MESSAGE, CHECKPOINT, role 'system', 'developer'
    4. Assistant signals: PLANNER_RESPONSE, ASSISTANT_RESPONSE, role 'assistant', 'model'
    """
    role = (role_raw or "").strip().lower()
    source = (source_raw or "").strip().lower()
    msg_type = (type_raw or "").strip().lower()
    combined = f"{role} {source} {msg_type}"

    # 1. User check (highest precedence)
    if (
        msg_type == "user_input"
        or source == "user_explicit"
        or role in ("user", "human")
        or any(k in combined for k in ("user_input", "user_explicit"))
    ):
        return "user"

    # 2. Tool result check: In Antigravity logs, tool results have type='GENERIC', source='MODEL'
    if (
        msg_type in ("generic", "tool_response", "tool_output", "tool_result")
        or role in ("tool", "function")
        or "tool" in combined
    ):
        return "tool"

    # 3. System check: system instructions, checkpoints, or notifications
    if (
        msg_type in ("system_message", "checkpoint", "system_prompt")
        or role in ("system", "developer")
        or source in ("system", "developer")
    ):
        return "system"

    # 4. Assistant check: planner response, assistant role, model source
    if (
        msg_type in ("planner_response", "assistant_response")
        or role in ("assistant", "model", "ai", "bot")
        or source in ("model", "assistant")
    ):
        return "assistant"

    return "assistant" if "planner" in combined else "user"


def format_tool_action(tc: Dict[str, Any]) -> str:
    """
    Format a single tool invocation into a clean, human-readable bullet item.
    Handles Antigravity, OpenAI function calls, and LangChain tool schemas.
    """
    if not isinstance(tc, dict):
        return f"- `{str(tc)}`"

    name = tc.get("name")
    if not name and "function" in tc and isinstance(tc["function"], dict):
        name = tc["function"].get("name")
    name = str(name or "tool")

    raw_args = tc.get("args") or tc.get("arguments") or {}
    if not raw_args and "function" in tc and isinstance(tc["function"], dict):
        raw_args = tc["function"].get("arguments") or {}

    args = raw_args
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args)
        except Exception:
            args = {"raw": raw_args}

    # Clean unescaped quotes if args came in as quoted strings (common in some JSONL engines)
    if isinstance(args, dict):
        cleaned_args = {}
        for k, v in args.items():
            if isinstance(v, str) and v.startswith('"') and v.endswith('"') and len(v) >= 2:
                v = v[1:-1]
            cleaned_args[k] = v
        args = cleaned_args
    else:
        args = {"raw": str(args)}

    # Ergonomic formatters for common tools across Antigravity and Nexus
    if name == "run_command":
        summary = args.get("toolSummary")
        cmd = args.get("CommandLine", "").strip()
        if summary and cmd:
            return f"- **`run_command`** — {summary} (`{cmd}`)"
        elif cmd:
            return f"- **`run_command`** — `{cmd}`"
        elif summary:
            return f"- **`run_command`** — {summary}"

    elif name in ("read_file", "edit_file", "write_file"):
        path = args.get("Path") or args.get("path") or ""
        short_path = path
        # Shorten path to relative or recognizable segment if excessively long
        parts = re.split(r"[\\/]", path)
        if "Nexus" in parts:
            idx = parts.index("Nexus")
            short_path = "/".join(parts[idx + 1 :])
        elif len(parts) > 4:
            short_path = "/".join(parts[-4:])

        line_info = ""
        if "StartLine" in args and "EndLine" in args:
            line_info = f" (Lines {args['StartLine']}–{args['EndLine']})"
        elif "StartLine" in args:
            line_info = f" (Line {args['StartLine']}+)"

        return f"- **`{name}`** — `{short_path}`{line_info}"

    elif name == "search_web":
        query = args.get("query") or args.get("q") or ""
        return f'- **`search_web`** — *"{query}"*'

    elif name == "search_marketplace":
        q = args.get("queries") or args.get("query") or ""
        return f'- **`search_marketplace`** — *"{q}"*'

    elif name == "manage_task":
        action = args.get("Action") or args.get("action") or ""
        task_id = args.get("TaskId") or args.get("task_id") or ""
        return f"- **`manage_task`** — `{action}` {task_id}".strip()

    elif name == "invoke_subagent":
        role = args.get("Role") or args.get("role") or ""
        type_name = args.get("TypeName") or args.get("type_name") or ""
        return f"- **`invoke_subagent`** — `{type_name}` ({role})"

    # Generic fallback: summarize up to 3 non-empty arguments
    if isinstance(args, dict) and args:
        summary_items = []
        for k, v in list(args.items())[:3]:
            str_v = json.dumps(v, ensure_ascii=False)
            if len(str_v) > 40:
                str_v = str_v[:37] + "..."
            summary_items.append(f"`{k}`: {str_v}")
        return f"- **`{name}`** ({', '.join(summary_items)})"

    return f"- **`{name}`**"


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

    # Timestamp extraction & normalization
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
    if not clean_content and not thinking and not tool_calls and role != "tool":
        return None

    return ChatMessage(
        role=role,
        content=clean_content,
        timestamp=str(timestamp),
        thinking=thinking,
        tool_calls=tool_calls if isinstance(tool_calls, list) else [],
        raw_type=str(type_raw),
        raw_source=str(source_raw),
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
        # 2. Wrapped messages array
        else:
            for key in ("messages", "steps", "history", "chat_history", "data", "records", "conversation"):
                if key in data and isinstance(data[key], list):
                    return parse_json_data(data[key])
            # Single object message fallback
            msg = parse_record_to_message(data)
            if msg:
                messages.append(msg)

    return messages


def coalesce_conversation_turns(messages: List[ChatMessage]) -> List[ConversationTurn]:
    """
    Coalesce raw step messages into clean, high-level ConversationTurns.

    INVARIANTS:
    - Every 'user' message initializes a new ConversationTurn.
    - Subsequent 'assistant' steps contribute:
      * Thinking traces to `turn.thinking_traces`
      * Tool invocations to `turn.tool_actions` (formatted cleanly)
      * Conversational text to `turn.assistant_response` (concatenated or preserved)
    - Subsequent 'tool' steps (stdout/results) are grouped under the active turn's execution context
      rather than spawning new assistant messages.
    """
    turns: List[ConversationTurn] = []
    current_turn: Optional[ConversationTurn] = None

    for msg in messages:
        if msg.role == "user":
            # If an existing turn is active, close and record it
            if current_turn is not None:
                turns.append(current_turn)

            current_turn = ConversationTurn(
                turn_index=len(turns) + 1,
                user_prompt=msg.content,
                user_timestamp=msg.timestamp,
            )

        elif msg.role == "assistant":
            if current_turn is None:
                # Initial greeting or assistant-initiated turn
                current_turn = ConversationTurn(
                    turn_index=len(turns) + 1,
                    user_prompt="",
                    user_timestamp="",
                )

            if not current_turn.assistant_timestamp and msg.timestamp:
                current_turn.assistant_timestamp = msg.timestamp

            if msg.thinking:
                current_turn.thinking_traces.append(msg.thinking)

            # Record and format all tool calls executed in this assistant step
            for tc in msg.tool_calls:
                formatted_tc = format_tool_action(tc)
                current_turn.tool_actions.append(formatted_tc)

            # Accumulate conversational text (ignore purely empty tool-calling frames)
            if msg.content and msg.content.strip():
                if current_turn.assistant_response:
                    current_turn.assistant_response += "\n\n" + msg.content.strip()
                else:
                    current_turn.assistant_response = msg.content.strip()

        elif msg.role == "system":
            if current_turn is not None and msg.content:
                current_turn.system_notes.append(msg.content)

        elif msg.role == "tool":
            # Tool result stdout is absorbed silently into the active turn
            pass

    if current_turn is not None:
        turns.append(current_turn)

    return turns


def format_turns_to_markdown(
    title_or_id: str,
    turns: List[ConversationTurn],
    source_desc: str = "",
    include_thinking: bool = False,
    include_tools: bool = True,
    max_tool_actions: Optional[int] = None,
    vault_format: bool = False,
) -> str:
    """Render a list of coalesced ConversationTurns to clean, Obsidian-compatible Markdown."""
    lines = []
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"Chat - {title_or_id[:12]}"
    total_tools = sum(len(t.tool_actions) for t in turns)

    if vault_format:
        lines.append("---")
        lines.append(f'aliases: ["{title}", "Convo {title_or_id[:8]}"]')
        lines.append("tags: [engineering, transcript, session-log, autopoiesis, ai, chat]")
        lines.append("type: transcript")
        lines.append(f"conversation_id: {title_or_id}")
        lines.append(f"exported_at: {now_str}")
        lines.append("---\n")

    lines.append(f"# Conversation: `{title_or_id}`\n")
    if source_desc:
        lines.append(f"> **Source:** `{source_desc}`  ")
    lines.append(f"> **Total Turns:** {len(turns)}  ")
    lines.append(f"> **Total Tool Actions:** {total_tools}  \n")
    lines.append("---\n")

    for turn in turns:
        u_time = f" `({turn.user_timestamp})`" if turn.user_timestamp else ""
        a_time = f" `({turn.assistant_timestamp})`" if turn.assistant_timestamp else ""

        # Derive a concise turn subject from user prompt
        prompt_snippet = turn.user_prompt.splitlines()[0] if turn.user_prompt else "Direct Interaction"
        if len(prompt_snippet) > 60:
            prompt_snippet = prompt_snippet[:57] + "..."

        lines.append(f"### Turn {turn.turn_index}: {prompt_snippet}\n")

        if turn.user_prompt:
            lines.append(f"**User**{u_time}:\n")
            # Format user prompt with blockquote for crisp visual hierarchy
            quoted_prompt = "\n".join(f"> {line}" if line else ">" for line in turn.user_prompt.splitlines())
            lines.append(f"{quoted_prompt}\n")

        if turn.assistant_response or turn.tool_actions:
            lines.append(f"**Assistant**{a_time}:\n")

            if include_thinking and turn.thinking_traces:
                lines.append("<details><summary><b>Thought Process</b></summary>\n")
                for trace in turn.thinking_traces:
                    lines.append(f"\n{trace}\n")
                lines.append("</details>\n")

            if turn.assistant_response:
                lines.append(f"{turn.assistant_response}\n")

            if include_tools and turn.tool_actions:
                count = len(turn.tool_actions)
                lines.append(f"\n<details><summary>🛠️ <b>Tool Executions ({count} actions)</b></summary>\n")
                tool_list = turn.tool_actions
                if max_tool_actions and len(tool_list) > max_tool_actions:
                    tool_list = tool_list[:max_tool_actions]
                    lines.extend(tool_list)
                    lines.append(f"- *... and {count - max_tool_actions} more actions omitted for brevity*")
                else:
                    lines.extend(tool_list)
                lines.append("\n</details>\n")

        lines.append("\n---\n")

    return "\n".join(lines)


def format_raw_steps_to_markdown(
    title_or_id: str,
    messages: List[ChatMessage],
    source_desc: str = "",
    include_thinking: bool = False,
    include_tools: bool = True,
    vault_format: bool = False,
) -> str:
    """Render uncoalesced atomic steps to Markdown (raw forensic debugging mode)."""
    lines = []
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"Chat - {title_or_id[:12]} (Raw Steps)"

    if vault_format:
        lines.append("---")
        lines.append(f'aliases: ["{title}", "Convo {title_or_id[:8]} Raw"]')
        lines.append("tags: [ai, chat, raw-steps, forensics]")
        lines.append("type: debug-log")
        lines.append(f"source_id: {title_or_id}")
        lines.append(f"exported_at: {now_str}")
        lines.append("---\n")

    lines.append(f"# Conversation Steps: `{title_or_id}`\n")
    if source_desc:
        lines.append(f"> **Source:** `{source_desc}`  ")
    lines.append(f"> **Total Atomic Steps:** {len(messages)}  \n")
    lines.append("---\n")

    for i, msg in enumerate(messages, 1):
        time_tag = f" `({msg.timestamp})`" if msg.timestamp else ""

        if msg.role == "user":
            lines.append(f"## [{i}] 👤 User{time_tag}\n")
            lines.append(f"{msg.content}\n\n---\n")

        elif msg.role == "assistant":
            lines.append(f"## [{i}] 🤖 Assistant{time_tag}\n")
            if include_thinking and msg.thinking:
                lines.append("<details><summary><b>Thought Process</b></summary>\n")
                lines.append(f"\n{msg.thinking}\n")
                lines.append("</details>\n")

            if msg.content:
                lines.append(f"{msg.content}\n")

            if include_tools and msg.tool_calls:
                lines.append("\n<details><summary><b>Tool Invocations</b></summary>\n")
                for tc in msg.tool_calls:
                    lines.append(format_tool_action(tc))
                lines.append("\n</details>\n")

            lines.append("\n---\n")

        elif msg.role == "system":
            lines.append(f"## [{i}] ⚙️ System{time_tag}\n")
            lines.append(f"{msg.content}\n\n---\n")

        elif msg.role == "tool":
            lines.append(f"## [{i}] 🛠️ Tool Result{time_tag}\n")
            lines.append(f"```text\n{msg.content}\n```\n\n---\n")

    return "\n".join(lines)


def get_brain_dirs() -> List[Path]:
    """Returns existing Antigravity brain directory roots across both current and legacy naming conventions."""
    home = Path.home()
    candidates = [
        home / ".gemini" / "antigravity" / "brain",
        home / ".gemini" / "antigravity-ide" / "brain",
    ]
    return [d for d in candidates if d.exists()]


def load_conversation_source(source_path_or_id: Optional[str] = None) -> Tuple[str, List[ChatMessage], str]:
    """
    Load conversation messages from a file path, JSON/JSONL stream, or conversation ID.
    Returns: (title_or_id, messages, source_description)
    """
    brain_dirs = get_brain_dirs()

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
            compact = p / ".system_generated" / "logs" / "transcript.jsonl"
            full = p / ".system_generated" / "logs" / "transcript_full.jsonl"
            target = compact if compact.exists() else (full if full.exists() else None)
            if target:
                with open(target, "r", encoding="utf-8", errors="ignore") as f:
                    messages = parse_jsonl_stream(f)
                return p.name, messages, str(target.resolve())

    # Fallback to Antigravity Brain resolver if UUID, prefix, or latest
    if brain_dirs:
        if not source_path_or_id or source_path_or_id.lower() == "latest":
            candidates = []
            for bdir in brain_dirs:
                for entry in bdir.iterdir():
                    if not entry.is_dir():
                        continue
                    log_compact = entry / ".system_generated" / "logs" / "transcript.jsonl"
                    log_full = entry / ".system_generated" / "logs" / "transcript_full.jsonl"
                    target_log = log_compact if log_compact.exists() else (log_full if log_full.exists() else None)
                    if target_log:
                        candidates.append((target_log.stat().st_mtime, entry.name, target_log))
            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                convo_id, target_file = candidates[0][1], candidates[0][2]
                with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                    messages = parse_jsonl_stream(f)
                return convo_id, messages, str(target_file.resolve())

        elif source_path_or_id:
            # Exact UUID search across brain dirs
            for bdir in brain_dirs:
                exact = bdir / source_path_or_id
                if exact.is_dir():
                    log_compact = exact / ".system_generated" / "logs" / "transcript.jsonl"
                    log_full = exact / ".system_generated" / "logs" / "transcript_full.jsonl"
                    target_log = log_compact if log_compact.exists() else (log_full if log_full.exists() else None)
                    if target_log:
                        with open(target_log, "r", encoding="utf-8", errors="ignore") as f:
                            messages = parse_jsonl_stream(f)
                        return source_path_or_id, messages, str(target_log.resolve())

            # Prefix match search across brain dirs
            matches = []
            for bdir in brain_dirs:
                for entry in bdir.iterdir():
                    if entry.is_dir() and entry.name.startswith(source_path_or_id):
                        log_compact = entry / ".system_generated" / "logs" / "transcript.jsonl"
                        log_full = entry / ".system_generated" / "logs" / "transcript_full.jsonl"
                        target_log = log_compact if log_compact.exists() else (log_full if log_full.exists() else None)
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


def list_conversations(limit: int = 15) -> List[Dict[str, Any]]:
    """Helper to list known conversation logs from local brain storage across all discovered roots."""
    brain_dirs = get_brain_dirs()
    if not brain_dirs:
        return []

    results = []
    seen_ids = set()
    for bdir in brain_dirs:
        for entry in bdir.iterdir():
            if not entry.is_dir() or entry.name in seen_ids:
                continue
            log_file = entry / ".system_generated" / "logs" / "transcript.jsonl"
            if not log_file.exists():
                log_file = entry / ".system_generated" / "logs" / "transcript_full.jsonl"
            if not log_file.exists():
                continue

            seen_ids.add(entry.name)
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
                            role = normalize_role(
                                data.get("role", ""),
                                data.get("source", ""),
                                data.get("type", ""),
                            )
                            if not preview and role == "user":
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
        description="Universal JSON / JSONL conversation transcript exporter and Markdown formatter with Turn Coalescing."
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
        help="Omit tool execution logs entirely.",
    )
    parser.add_argument(
        "--max-tools",
        type=int,
        default=None,
        help="Maximum tool actions to show per turn before truncating with count.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Export raw step-by-step stream instead of coalescing into human dialogue turns.",
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

        if args.raw:
            rendered = format_raw_steps_to_markdown(
                title_or_id=title_or_id,
                messages=messages,
                source_desc=source_desc,
                include_thinking=args.include_thinking,
                include_tools=not args.no_tools,
                vault_format=args.vault_inbox,
            )
        else:
            turns = coalesce_conversation_turns(messages)
            rendered = format_turns_to_markdown(
                title_or_id=title_or_id,
                turns=turns,
                source_desc=source_desc,
                include_thinking=args.include_thinking,
                include_tools=not args.no_tools,
                max_tool_actions=args.max_tools,
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

        mode_str = "raw steps" if args.raw else "coalesced turns"
        print(f"Successfully exported {len(messages)} steps ({mode_str}) to: {out_file.resolve()}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    export_conversation_cli()
