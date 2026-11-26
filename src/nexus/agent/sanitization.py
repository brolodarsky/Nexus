"""
sanitization.py — Message Extraction & Cross-Provider History Sanitization for NexusAgent.

Pure leaf module (zero `nexus.*` imports) so `runtime.py`, `subagent.py`, `graph.py`,
`api.py`, and `nexus.core.*` helpers can import message extractors and cross-provider
sanitizers without circular dependencies.
"""
# Sequence: Immutable ordered sequence of LangChain `BaseMessage` objects
from typing import Any, Optional, Sequence

# LangChain message primitives:
# - AIMessage: Assistant responses (either conversational text or tool call requests)
# - BaseMessage: Abstract parent class for all chat messages
# - HumanMessage: User inputs or subagent task prompts
# - ToolMessage: Output returned from executing a `@tool` function
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


# ── Helper: Telemetry & Structured Content Block Text Extraction ─────────────

def extract_message_text(msg: BaseMessage | None) -> str:
    """Extracts plain-text markdown from a LangChain BaseMessage across both string and Gemini block-list formats.

    Gemini 3+ thinking models return structured content blocks (`[{'type': 'text', 'text': '...', 'extras': {'signature': '...'}}]`)
    to preserve reasoning signatures in checkpointer state. This helper extracts the clean text string for UI/CLI display
    without mutating the underlying message's signature blocks.
    """
    if msg is None:
        return ""
    if hasattr(msg, "text") and isinstance(msg.text, str):
        return msg.text
    raw_content = getattr(msg, "content", "")
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        parts: list[str] = []
        for block in raw_content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(raw_content)


# `msg: BaseMessage | None` is a LangChain message (typically an `AIMessage` returned by Gemini or Anthropic).
# `-> str` returns concatenated readable thinking/reasoning summaries without mutating `msg` or its signatures.
def extract_message_thinking(msg: BaseMessage | None) -> str:
    """Extract readable model thinking/reasoning text from an `AIMessage` without mutating persisted state.

    Supports:
    - Anthropic & Gemini structured content blocks (`{'type': 'thinking', 'thinking': '...'}`).
    - Reasoning/summary blocks (`{'type': 'reasoning'|'reasoning_content', 'reasoning'|'summary'|'text': ...}`).
    - Legacy provider `additional_kwargs['reasoning_content']` strings.

    Never mutates `msg.content` or strips cryptographic signatures so `SqliteSaver` and KV caches stay intact.
    """
    if msg is None:
        return ""
    parts: list[str] = []
    raw_content = getattr(msg, "content", None)

    if isinstance(raw_content, list):
        for block in raw_content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "thinking":
                thought_val = block.get("thinking")
                if not isinstance(thought_val, str) or not thought_val.strip():
                    thought_val = block.get("text")
                if isinstance(thought_val, str) and thought_val.strip():
                    parts.append(thought_val.strip())
            elif btype in ("reasoning", "reasoning_content"):
                # Inspect flat string fields first, then OpenAI-style `summary` lists
                for key in ("reasoning", "reasoning_content", "text"):
                    val = block.get(key)
                    if isinstance(val, str) and val.strip():
                        parts.append(val.strip())
                        break
                summary_items = block.get("summary")
                if isinstance(summary_items, list):
                    for item in summary_items:
                        if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                            parts.append(item["text"].strip())

    if not parts:
        ak = getattr(msg, "additional_kwargs", None) or {}
        if isinstance(ak, dict):
            rc = ak.get("reasoning_content")
            if isinstance(rc, str) and rc.strip():
                parts.append(rc.strip())

    return "\n\n".join(parts)


# ── Helper: Cross-Provider Thought & Signature Isolation ─────────────────────

# frozenset: Immutable set of provider-specific content block types that carry thinking payloads, cryptographic
# signatures, or Anthropic-native tool envelopes (`tool_use`) which must not leak across provider families.
_FOREIGN_BLOCK_TYPES = frozenset({
    "thinking",
    "redacted_thinking",
    "reasoning",
    "reasoning_content",
    "tool_use",
    "server_tool_use",
    "mcp_tool_use",
})


# `provider: Optional[str]` is a raw provider identifier from `AIMessage.response_metadata["model_provider"]` or config.
# `-> Optional[str]` maps LangChain provider strings to canonical Nexus keys (`"gemini"`, `"anthropic"`, `"openai"`).
def _normalize_provider_name(provider: Optional[str]) -> Optional[str]:
    """Normalize provider metadata strings across LangChain integrations into canonical provider keys."""
    if not provider:
        return None
    norm = str(provider).strip().lower()
    if norm in ("google_genai", "google_vertexai", "google", "gemini"):
        return "gemini"
    if norm == "anthropic":
        return "anthropic"
    if norm == "openai":
        return "openai"
    return None


# `msg: BaseMessage` is any message in LangGraph conversation history.
# `-> Optional[str]` infers the originating provider (`"gemini"`, `"anthropic"`, `"openai"`) for `AIMessage`s, or None.
def _infer_message_provider(msg: BaseMessage) -> Optional[str]:
    """Infer which LLM provider produced an `AIMessage` using metadata first, then structural block signatures."""
    if not isinstance(msg, AIMessage):
        return None

    # 1. Explicit `model_provider` recorded by LangChain (`"google_genai"`, `"anthropic"`, `"openai"`)
    rm = getattr(msg, "response_metadata", None) or {}
    norm = _normalize_provider_name(rm.get("model_provider"))
    if norm:
        return norm

    # 2. Fallback to model name substrings when older checkpoints omitted `model_provider`
    model_name = str(rm.get("model_name") or rm.get("model") or "").strip().lower()
    if model_name:
        if any(tok in model_name for tok in ("gemini", "argon", "hydrogen")):
            return "gemini"
        if any(tok in model_name for tok in ("claude", "opus", "sonnet", "haiku")):
            return "anthropic"
        if any(tok in model_name for tok in ("gpt", "o1", "o3", "o4")):
            return "openai"

    # 3. Structural marker fallback for checkpoints lacking `response_metadata`
    ak = getattr(msg, "additional_kwargs", None) or {}
    if "__gemini_function_call_thought_signatures__" in ak:
        return "gemini"

    if isinstance(msg.content, list):
        for block in msg.content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype in ("redacted_thinking", "tool_use", "server_tool_use", "mcp_tool_use"):
                return "anthropic"
            if btype == "text":
                extras = block.get("extras")
                if isinstance(extras, dict) and ("signature" in extras or "thought_signature" in extras):
                    return "gemini"

    return None


# `msg: AIMessage` is a historical assistant message in thread state.
# `-> bool` returns True if `msg` contains provider-bound thinking blocks, signatures, or native tool_use blocks.
def _has_provider_thought_artifacts(msg: AIMessage) -> bool:
    """Check whether an `AIMessage` carries provider-specific thought blocks or cryptographic signatures."""
    ak = getattr(msg, "additional_kwargs", None) or {}
    if "__gemini_function_call_thought_signatures__" in ak or "thought_signature" in ak:
        return True

    if isinstance(msg.content, list):
        for block in msg.content:
            if not isinstance(block, dict):
                continue
            if block.get("type") in _FOREIGN_BLOCK_TYPES:
                return True
            if any(k in block for k in ("signature", "thought_signature", "cache_control")):
                return True
            extras = block.get("extras")
            if isinstance(extras, dict) and ("signature" in extras or "thought_signature" in extras):
                return True

    return False


# `msg: AIMessage` is a foreign-provider (or rejected-signature) assistant message.
# `-> AIMessage` returns an ephemeral `model_copy` stripped of thought/signature metadata while leaving `msg` unmutated.
def _strip_ai_message_thought_artifacts(msg: AIMessage) -> AIMessage:
    """Create an ephemeral copy of `msg` with cross-provider thinking/signature blocks and tool envelopes removed.

    Why `model_copy` instead of mutating `msg` in place:
    `SqliteSaver` checkpoints hold references to historical `AIMessage` objects. Mutating them in place would
    corrupt persisted Anthropic/Gemini signatures if the user later switches back to the original provider.
    Tool call invocations (`msg.tool_calls`) and plain conversational text are preserved intact.
    """
    has_tool_calls = bool(getattr(msg, "tool_calls", None))
    new_content: Any = msg.content

    if isinstance(msg.content, list):
        cleaned_blocks: list[Any] = []
        for block in msg.content:
            if isinstance(block, str):
                cleaned_blocks.append(block)
            elif isinstance(block, dict):
                # Drop thinking/reasoning blocks and provider-specific tool_use wrappers (`msg.tool_calls` retains calls)
                if block.get("type") in _FOREIGN_BLOCK_TYPES:
                    continue
                b_copy = dict(block)
                b_copy.pop("signature", None)
                b_copy.pop("thought_signature", None)
                b_copy.pop("cache_control", None)
                if isinstance(b_copy.get("extras"), dict):
                    ex = dict(b_copy["extras"])
                    ex.pop("signature", None)
                    ex.pop("thought_signature", None)
                    if ex:
                        b_copy["extras"] = ex
                    else:
                        b_copy.pop("extras", None)
                cleaned_blocks.append(b_copy)
            else:
                cleaned_blocks.append(block)

        # Collapse pure-text (or empty) block lists to a plain string so neither Gemini (`parts=[]`)
        # nor Anthropic (whitespace-only text blocks) rejects empty content turns.
        only_text_or_empty = all(
            isinstance(b, str) or (isinstance(b, dict) and b.get("type") == "text")
            for b in cleaned_blocks
        )
        if only_text_or_empty:
            non_empty_texts = [
                t for t in (
                    b if isinstance(b, str) else str(b.get("text", ""))
                    for b in cleaned_blocks
                )
                if t and t.strip()
            ]
            if non_empty_texts:
                new_content = "\n".join(non_empty_texts)
            else:
                new_content = "" if has_tool_calls else "(no text)"
        else:
            # Non-text blocks (e.g. multimodal image/file blocks) survive: prune blank text dicts only
            filtered_blocks = [
                b for b in cleaned_blocks
                if not (isinstance(b, dict) and b.get("type") == "text" and not str(b.get("text", "")).strip())
            ]
            new_content = filtered_blocks if filtered_blocks else ("" if has_tool_calls else "(no text)")
    elif isinstance(new_content, str) and not new_content.strip() and not has_tool_calls:
        new_content = "(no text)"

    # Shallow-copy `additional_kwargs` and remove Gemini/provider signature keys (plus redundant `function_call`)
    new_ak = dict(getattr(msg, "additional_kwargs", None) or {})
    new_ak.pop("__gemini_function_call_thought_signatures__", None)
    new_ak.pop("thought_signature", None)
    if has_tool_calls:
        new_ak.pop("function_call", None)

    # Shallow-copy `response_metadata` and strip `output_version` so v1 block unpackers do not re-run on cleaned text
    new_rm = dict(getattr(msg, "response_metadata", None) or {})
    new_rm.pop("output_version", None)

    return msg.model_copy(
        update={
            "content": new_content,
            "additional_kwargs": new_ak,
            "response_metadata": new_rm,
        }
    )


# `messages: Sequence[BaseMessage]` is the turn-ordered conversation history from `_sanitize_messages()`.
# `target_provider: str` is the destination provider key (`"gemini"`, `"anthropic"`, `"openai"`).
# `strip_all_signatures: bool = False` forces stripping across ALL `AIMessage`s (used by reactive 400 recovery).
# `-> list[BaseMessage]` returns a list safe for the target provider, preserving same-provider message identity.
def _sanitize_messages_for_provider(
    messages: Sequence[BaseMessage],
    target_provider: str,
    *,
    strip_all_signatures: bool = False,
) -> list[BaseMessage]:
    """Strip foreign-provider thinking blocks and thought signatures before cross-provider model invocation.

    Preserves exact object identity (`msg` untouched) whenever a message originates from `target_provider`,
    guaranteeing zero KV prompt-cache prefix churn on single-provider conversations (e.g. Gemini -> Gemini
    or Anthropic -> Anthropic), while preventing `400 INVALID_THOUGHT_SIGNATURE` / `ValueError` crashes when
    switching models mid-thread (e.g. Claude Opus -> Gemini Flash).
    """
    norm_target = _normalize_provider_name(target_provider)
    result: list[BaseMessage] = []
    for msg in messages:
        if not isinstance(msg, AIMessage):
            result.append(msg)
            continue

        if strip_all_signatures:
            result.append(
                _strip_ai_message_thought_artifacts(msg)
                if _has_provider_thought_artifacts(msg)
                else msg
            )
            continue

        src_provider = _infer_message_provider(msg)
        if src_provider is not None and src_provider == norm_target:
            # Same provider: preserve cryptographic signatures and original object identity for KV caching
            result.append(msg)
        elif _has_provider_thought_artifacts(msg):
            # Foreign or unattributed message carrying provider signatures/thinking blocks: strip ephemerally
            result.append(_strip_ai_message_thought_artifacts(msg))
        else:
            result.append(msg)

    return result


# ── Helper: Sanitize Dangling Tool Calls & Mid-Turn Pruned History ───────────

def _sanitize_messages(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Ensures message history obeys strict `HumanMessage -> AIMessage(tool_calls) -> ToolMessage` ordering.

    Self-heals two edge cases that otherwise cause HTTP 400 `INVALID_ARGUMENT` on Gemini / OpenAI:
      1. Mid-turn history pruning: If an older summarizer pass sliced history inside a tool loop, strips leading
         `ToolMessage` and `AIMessage(tool_calls)` fragments that lack a preceding `HumanMessage`, and prepends a
         lightweight `HumanMessage` anchor if the history begins with a standalone conversational `AIMessage`.
      2. Interrupted tool calls: Replaces any `AIMessage(tool_calls)` missing its `ToolMessage` responses with a
         plain-text `AIMessage` and drops any partial orphaned `ToolMessage`s.
    """
    cleaned = list(messages)

    # 1. Strip leading mid-turn tool fragments (`ToolMessage` or `AIMessage` with tool_calls) before the first `HumanMessage`
    while cleaned and (
        isinstance(cleaned[0], ToolMessage)
        or (isinstance(cleaned[0], AIMessage) and bool(getattr(cleaned[0], "tool_calls", None)))
    ):
        cleaned.pop(0)

    # If the slice begins with a final conversational `AIMessage` from the prior turn, anchor it with a `HumanMessage`
    if cleaned and isinstance(cleaned[0], AIMessage):
        cleaned.insert(0, HumanMessage(content="[Prior turn context summarized in SystemMessage]"))

    # 2. Sanitize any interrupted `AIMessage(tool_calls)` missing matching `ToolMessage` responses
    dropped_tc_ids: set[str] = set()
    for i, msg in enumerate(cleaned):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            has_all_responses = True
            for tc in msg.tool_calls:
                tc_id = tc.get("id")
                if not any(getattr(m, "tool_call_id", None) == tc_id for m in cleaned[i + 1 :]):
                    has_all_responses = False
                    break
            if not has_all_responses:
                for tc in msg.tool_calls:
                    if tc.get("id"):
                        dropped_tc_ids.add(tc["id"])
                cleaned[i] = AIMessage(content=extract_message_text(msg) or "(tool calls dropped due to prior interruption)")

    if dropped_tc_ids:
        cleaned = [
            m for m in cleaned
            if not (isinstance(m, ToolMessage) and getattr(m, "tool_call_id", None) in dropped_tc_ids)
        ]

    return cleaned
