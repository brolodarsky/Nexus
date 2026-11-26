"""
context_telemetry.py — Content-addressed context manifest builders for `agent_start` and `llm_call`.

Why this exists:
  `agent_start` previously logged only the raw user query or subagent `task_prompt`, hiding the
  31.4 KB `Master Instructions.md`, bound tool schemas, pre-hydrated `# Pre-Hydrated Disk Context`
  notes, auto-discovered `Section Instructions.md`, prior thread history, and wire-level per-turn
  transformations (e.g. signature stripping or budget soft-landing notices).

  Instead of duplicating megabytes of text into every trace event, this module hashes each immutable
  block via `store_trace_blob()` (SHA-256 after secret scrubbing) and attaches a lightweight ordered
  `context_manifest` + `context_summary` (`total_chars`, `approx_tokens`, counts) so UI drawers can
  display sizes immediately, lazy-load sections on expand, or summon the full stitched context on demand.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from nexus.core.chats_db import store_trace_blob
from nexus.core.secret_scrubber import approx_token_count

# Process-local cache mapping tuple of tool names -> (serialized_json_str, tool_names_list)
# Because `TOOLS` and `CORE_TOOLS` are static module definitions, caching avoids re-serializing 22-23 schemas per call.
_TOOL_SCHEMA_CACHE_LOCK = threading.Lock()
_TOOL_SCHEMA_CACHE: dict[tuple[str, ...], tuple[str, list[str]]] = {}


def get_serialized_tool_schemas(tools: Sequence[Any]) -> tuple[str, list[str]]:
    """Serialize LangChain `@tool` objects into canonical OpenAI JSON schema text (memoized per tool tuple)."""
    if not tools:
        return "[]", []
    names = [str(getattr(t, "name", None) or getattr(t, "__name__", "tool")) for t in tools]
    cache_key = tuple(names)
    with _TOOL_SCHEMA_CACHE_LOCK:
        cached = _TOOL_SCHEMA_CACHE.get(cache_key)
        if cached is not None:
            return cached

    schemas: list[dict[str, Any]] = []
    for t in tools:
        try:
            schemas.append(convert_to_openai_tool(t))
        except Exception:
            schemas.append({
                "type": "function",
                "function": {
                    "name": str(getattr(t, "name", "unknown")),
                    "description": str(getattr(t, "description", "")),
                },
            })
    serialized = json.dumps(schemas, indent=2, ensure_ascii=False)
    with _TOOL_SCHEMA_CACHE_LOCK:
        _TOOL_SCHEMA_CACHE[cache_key] = (serialized, names)
    return serialized, names


def _extract_plain_text(msg: BaseMessage) -> str:
    """Extract readable plain text from a LangChain message without mutating original state."""
    raw_content = getattr(msg, "content", "")
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        parts: list[str] = []
        for block in raw_content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                btype = block.get("type")
                if btype == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif btype == "image_url":
                    img_obj = block.get("image_url") if isinstance(block.get("image_url"), dict) else {}
                    url = str(img_obj.get("url") or "")
                    if url.startswith("data:"):
                        mime_prefix = url.split(";", 1)[0]
                        parts.append(f"[Attached Image ({mime_prefix})]")
                    else:
                        parts.append(f"[Attached Image: {url}]")
                elif btype == "nexus_image_ref":
                    parts.append(f"[Attached Image: {block.get('url', '')}]")
        return "\n".join(parts)
    return str(raw_content)


def _extract_thinking_blocks(msg: BaseMessage) -> str:
    """Extract natural-language thinking/reasoning blocks from an `AIMessage`."""
    parts: list[str] = []
    raw_content = getattr(msg, "content", None)
    if isinstance(raw_content, list):
        for block in raw_content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "thinking":
                val = block.get("thinking") or block.get("text")
                if isinstance(val, str) and val.strip():
                    parts.append(val.strip())
            elif btype in ("reasoning", "reasoning_content"):
                for key in ("reasoning", "reasoning_content", "text"):
                    val = block.get(key)
                    if isinstance(val, str) and val.strip():
                        parts.append(val.strip())
                        break
                summary = block.get("summary")
                if isinstance(summary, list):
                    for item in summary:
                        if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                            parts.append(item["text"].strip())
    if not parts:
        ak = getattr(msg, "additional_kwargs", None) or {}
        if isinstance(ak, dict) and isinstance(ak.get("reasoning_content"), str) and ak["reasoning_content"].strip():
            parts.append(ak["reasoning_content"].strip())
    return "\n\n".join(parts)


def _has_thought_signature(msg: BaseMessage) -> bool:
    """Detect whether an `AIMessage` carries cryptographic provider thought signatures or cache hints."""
    if not isinstance(msg, AIMessage):
        return False
    ak = getattr(msg, "additional_kwargs", None) or {}
    if "__gemini_function_call_thought_signatures__" in ak or "thought_signature" in ak:
        return True
    if isinstance(msg.content, list):
        for block in msg.content:
            if not isinstance(block, dict):
                continue
            if any(k in block for k in ("signature", "thought_signature", "cache_control")):
                return True
            extras = block.get("extras")
            if isinstance(extras, dict) and ("signature" in extras or "thought_signature" in extras):
                return True
    return False


# `msg: BaseMessage` is any LangChain message in conversation or subagent history.
# `-> tuple[str, str, str]` returns `(blob_kind, role_label, formatted_text)` with zero base64 image bloat.
def format_lc_message_for_blob(
    msg: BaseMessage,
    image_refs: Optional[list[str]] = None,
) -> tuple[str, str, str]:
    """Render a LangChain `BaseMessage` into readable, lossless audit text for SHA-256 `trace_blobs` storage."""
    if isinstance(msg, SystemMessage):
        text = _extract_plain_text(msg)
        has_ephemeral_cache = isinstance(msg.content, list) and any(
            isinstance(b, dict) and "cache_control" in b for b in msg.content
        )
        suffix = "\n[Anthropic cache_control: ephemeral]" if has_ephemeral_cache else ""
        return "system_prompt", "SYSTEM", f"{text}{suffix}"

    if isinstance(msg, HumanMessage):
        text = _extract_plain_text(msg)
        if image_refs:
            refs_line = "\n".join(f"[Image Attachment Ref: {ref}]" for ref in image_refs)
            text = f"{text}\n\n{refs_line}".strip()
        return "history_message", "USER", text

    if isinstance(msg, AIMessage):
        sections: list[str] = []
        thinking = _extract_thinking_blocks(msg)
        if thinking:
            sections.append(f"[THINKING]\n{thinking}\n[/THINKING]")
        if _has_thought_signature(msg):
            sections.append("[Cryptographic Thought Signature Attached]")
        body = _extract_plain_text(msg).strip()
        if body:
            sections.append(body)
        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls:
            sections.append(
                "[TOOL CALLS]\n" + json.dumps(tool_calls, indent=2, ensure_ascii=False, default=str)
            )
        return "history_message", "ASSISTANT", "\n\n".join(sections) if sections else "(empty assistant message)"

    if isinstance(msg, ToolMessage):
        t_name = getattr(msg, "name", None) or "tool"
        tc_id = getattr(msg, "tool_call_id", None) or "unknown"
        status = getattr(msg, "status", None) or "success"
        body = _extract_plain_text(msg)
        return "history_message", f"TOOL ({t_name})", f"[Tool: {t_name} | call_id: {tc_id} | status: {status}]\n{body}"

    return "history_message", str(getattr(msg, "type", "MESSAGE")).upper(), _extract_plain_text(msg)


def _summarize_manifest(
    manifest: list[dict[str, Any]],
    *,
    prior_messages_count: int = 0,
    tool_count: int = 0,
) -> dict[str, Any]:
    """Compute lightweight totals (`total_chars`, `approx_tokens`, counts) from a context manifest."""
    total_chars = sum(int(entry.get("chars", 0) or 0) for entry in manifest)
    return {
        "total_chars": total_chars,
        "approx_tokens": approx_token_count(total_chars),
        "section_count": len(manifest),
        "prior_messages_count": prior_messages_count,
        "tool_count": tool_count,
    }


def build_head_agent_start_manifest(
    *,
    system_prompt: str,
    tools: Sequence[Any],
    prior_messages: Sequence[BaseMessage],
    user_prompt: str,
    images: Optional[list[str]] = None,
    run_id: Optional[str] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build and deduplicate the full Head Agent boot context manifest for `agent_start`."""
    manifest: list[dict[str, Any]] = []

    sys_blob = store_trace_blob(system_prompt, kind="system_prompt", run_id=run_id)
    manifest.append({
        "role": "system",
        "label": "System Prompt (Master Instructions)",
        **sys_blob,
    })

    tools_json, tool_names = get_serialized_tool_schemas(tools)
    tools_blob = store_trace_blob(tools_json, kind="tool_schemas", run_id=run_id)
    manifest.append({
        "role": "tools",
        "label": f"Bound Tool Schemas ({len(tool_names)} tools)",
        "tool_names": tool_names,
        **tools_blob,
    })

    for idx, msg in enumerate(prior_messages, start=1):
        kind, role_label, text = format_lc_message_for_blob(msg)
        msg_blob = store_trace_blob(text, kind=kind, run_id=run_id)
        manifest.append({
            "role": "history",
            "label": f"Prior Message #{idx} · {role_label}",
            **msg_blob,
        })

    wrapped_user = user_prompt
    if images:
        refs = "\n".join(f"[Image Attachment Ref: {img}]" for img in images)
        wrapped_user = f"{user_prompt}\n\n{refs}".strip()
    user_blob = store_trace_blob(wrapped_user, kind="user_prompt", run_id=run_id)
    manifest.append({
        "role": "prompt",
        "label": "Current User Message (Timestamped)",
        **user_blob,
    })

    summary = _summarize_manifest(
        manifest,
        prior_messages_count=len(prior_messages),
        tool_count=len(tool_names),
    )
    return manifest, summary


def build_subagent_start_manifest(
    *,
    root_instructions: str,
    subagent_protocol: str,
    tools: Sequence[Any],
    prehydrated_block: str,
    task_prompt: str,
    context_files: Optional[list[str]] = None,
    run_id: Optional[str] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build and deduplicate the full Subagent boot context manifest for `agent_start`."""
    manifest: list[dict[str, Any]] = []

    # Uses identical `kind="system_prompt"` & text so root instructions deduplicate 1:1 with Head Agent
    sys_blob = store_trace_blob(root_instructions, kind="system_prompt", run_id=run_id)
    manifest.append({
        "role": "system",
        "label": "Root System Prompt (Master Instructions)",
        **sys_blob,
    })

    proto_blob = store_trace_blob(subagent_protocol, kind="subagent_protocol", run_id=run_id)
    manifest.append({
        "role": "protocol",
        "label": "Subagent Execution Protocol",
        **proto_blob,
    })

    tools_json, tool_names = get_serialized_tool_schemas(tools)
    tools_blob = store_trace_blob(tools_json, kind="tool_schemas", run_id=run_id)
    manifest.append({
        "role": "tools",
        "label": f"Bound Tool Schemas ({len(tool_names)} tools)",
        "tool_names": tool_names,
        **tools_blob,
    })

    if prehydrated_block and prehydrated_block.strip():
        pre_blob = store_trace_blob(prehydrated_block, kind="prehydrated_context", run_id=run_id)
        manifest.append({
            "role": "prehydrated",
            "label": "Pre-Hydrated Disk & Cache Context (incl. Section Instructions)",
            "context_files": list(context_files) if context_files else [],
            **pre_blob,
        })

    task_blob = store_trace_blob(task_prompt, kind="task_prompt", run_id=run_id)
    manifest.append({
        "role": "prompt",
        "label": "Assigned Subagent Task Prompt",
        **task_blob,
    })

    summary = _summarize_manifest(
        manifest,
        prior_messages_count=0,
        tool_count=len(tool_names),
    )
    return manifest, summary


def build_llm_call_manifest(
    *,
    messages: Sequence[BaseMessage],
    tools: Optional[Sequence[Any]] = None,
    run_id: Optional[str] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Capture the exact wire-level outgoing messages + bound tool schemas for an `llm_call` step."""
    manifest: list[dict[str, Any]] = []
    tool_count = 0

    for idx, msg in enumerate(messages):
        if isinstance(msg, SystemMessage):
            kind, role_label, text = format_lc_message_for_blob(msg)
            blob = store_trace_blob(text, kind=kind, run_id=run_id)
            manifest.append({
                "role": "system",
                "label": f"Message #{idx + 1} · {role_label}",
                **blob,
            })
        else:
            kind, role_label, text = format_lc_message_for_blob(msg)
            blob = store_trace_blob(text, kind=kind, run_id=run_id)
            manifest.append({
                "role": "history" if idx < len(messages) - 1 else "prompt",
                "label": f"Message #{idx + 1} · {role_label}",
                **blob,
            })

    if tools:
        tools_json, tool_names = get_serialized_tool_schemas(tools)
        tool_count = len(tool_names)
        tools_blob = store_trace_blob(tools_json, kind="tool_schemas", run_id=run_id)
        manifest.append({
            "role": "tools",
            "label": f"Bound Tool Schemas ({tool_count} tools)",
            "tool_names": tool_names,
            **tools_blob,
        })

    summary = _summarize_manifest(
        manifest,
        prior_messages_count=max(0, len(messages) - 1),
        tool_count=tool_count,
    )
    return manifest, summary
