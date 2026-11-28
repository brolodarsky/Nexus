"""
shared.py — Canonical Unified @tool Registry for NexusAgent and the Nexus MCP Server.
Defines every typed Nexus capability once (Vault navigation, surgical HITL file edits,
capture-cached web/YouTube/email readers, Gmail mutations, Google Calendar, Chrome Browser
Bridge, Tavily search, Telegram notifications, media transcription, resume compiler,
Android ADB ingestion, conversation export, and branch spawning).
"""
import contextlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from nexus.core.constants import PROJECT_ROOT, VAULT_PATH


# ── 1. Vault Directory & Navigation Tools ────────────────────────────────────

# Optional[str] (str | None) allows calling with no path to inspect the Vault root, or a section path to see notes.
@tool
def get_directory_structure(path: Optional[str] = None) -> str:
    """List Vault folders (when `path` omitted), Vault root files + top folders (`path=""` / `"."`), or a section tree.

    Args:
        path: Optional Vault-relative folder path (e.g. "3. Operations/3.1. Career Strategy & Revenue").
    """
    from nexus.shared_tools.vault_reader import get_directory_tree

    # If path is omitted, show folders only for fast orientation; root aliases list depth-1 files + folders only.
    if path is None:
        return get_directory_tree(path=None, show_files=False)
    clean_path = path.strip()
    if clean_path in ("", ".", "/", "Vault", "Vault/"):
        return get_directory_tree(path=None, show_files=True, max_depth=1)
    return get_directory_tree(path=path, show_files=True)


# ── 2. Vault File Reading & Search Tools ─────────────────────────────────────

def _format_missing_cache_keys_hint(conversation_id: str) -> str:
    """Formats valid `cache://...` external captures and `cache://chat/...` draft block handles."""
    from nexus.core.conversation_cache import list_captures, list_chat_blocks

    entries = list_captures(conversation_id)
    chat_blocks = list_chat_blocks(conversation_id, limit=10)
    if not entries and not chat_blocks:
        return f"No external captures or chat draft blocks are currently cached in conversation `{conversation_id}`."
    bullets = []
    for item in entries:
        url_note = f" ({item['source_url']})" if item.get("source_url") else ""
        bullets.append(f"- `{item['cache_key']}` — {item['title']}{url_note}")
    for blk in chat_blocks:
        bullets.append(f"- `{blk['cache_key']}` — {blk['title']} (chat {blk['role']}, {blk['char_count']:,} chars)")
    return f"Valid cached keys in conversation `{conversation_id}`:\n" + "\n".join(bullets)


def _format_cached_capture_for_read(
    capture: dict,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    """Formats a per-conversation cached external capture for `read_file` with optional 1-indexed line slicing."""
    cache_key = capture["cache_key"]
    short_key = cache_key[len("cache://") :] if cache_key.startswith("cache://") else cache_key
    title = capture.get("title") or cache_key
    src_type = capture.get("source_type") or "capture"
    char_count = int(capture.get("char_count") or len(capture.get("content") or ""))
    src_url = capture.get("source_url")
    url_part = f" | URL: {src_url}" if src_url else ""
    banner = (
        f"[CONVERSATION CACHE CAPTURE (`{cache_key}`) — {title} | {src_type} | "
        f"{char_count:,} chars{url_part}]\n"
        f"*(Embed verbatim in `create_file` / `modify_file` via `{{{{cache:{short_key}}}}}`)*\n\n"
    )
    body = capture.get("content") or ""
    if start_line is not None or end_line is not None:
        lines = body.splitlines()
        s_idx = max(0, (start_line or 1) - 1)
        e_idx = min(len(lines), end_line or len(lines))
        sliced = "\n".join(f"{i + 1}: {lines[i]}" for i in range(s_idx, e_idx))
        return f"{banner}--- {cache_key} (Lines {s_idx + 1}-{e_idx} of {len(lines)}) ---\n{sliced}"
    return f"{banner}{body}"


# Pure-Python shared helper used by both `@tool read_file` and `spawn_subagent(context_files=...)`
# so HITL staged-edit overlays, disk reads, and per-conversation `cache://` captures share one canonical path.
def read_vault_file_with_hitl_overlay(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    record_seen: bool = True,
) -> str:
    """Resolve and read a Vault note (with HITL overlays) or per-conversation `cache://` capture."""
    from nexus.core.conversation_cache import (
        format_captures_manifest,
        format_chat_blocks_manifest,
        get_active_conversation_id,
        get_capture,
        is_cache_ref,
    )
    from nexus.core.hitl_queue import get_pending_for_file
    from nexus.core.instruction_guard import record_read_instructions
    from nexus.shared_tools.vault_reader import format_partial_read_context, read_note_content, resolve_vault_note_path

    cleaned_ref = (file_path or "").strip()
    # 0. Support per-conversation external capture & chat-draft lookups (`cache://`, `cache://chat`, `cache://<key>`, or cached URLs)
    if cleaned_ref.lower().rstrip("/") in ("cache:", "cache://", "cache://list", "cache://*"):
        return format_captures_manifest(get_active_conversation_id())
    if cleaned_ref.lower().rstrip("/") in ("cache://chat", "cache://chat/list", "cache://chat/*"):
        return format_chat_blocks_manifest(get_active_conversation_id())

    if is_cache_ref(cleaned_ref) or cleaned_ref.lower().startswith(("http://", "https://")):
        active_convo = get_active_conversation_id()
        capture = get_capture(active_convo, cleaned_ref)
        if capture is not None:
            return _format_cached_capture_for_read(capture, start_line=start_line, end_line=end_line)
        hint = _format_missing_cache_keys_hint(active_convo)
        return (
            f"Error: Cached capture `{cleaned_ref}` was not found in conversation `{active_convo}`.\n\n"
            f"{hint}"
        )

    # 1. Check if this file has a pending transaction in the HITL queue (`hitl.db`).
    # First resolve on disk if it exists so short filenames ("Plan.md") map to their canonical `Vault/...` path.
    resolved_path, err = resolve_vault_note_path(file_path)
    if err and ("outside the Vault" in err or "cannot be empty" in err):
        return err

    lookup_target = (
        f"Vault/{str(resolved_path.relative_to(VAULT_PATH.resolve())).replace(chr(92), '/')}"
        if resolved_path is not None
        else file_path
    )
    pending_tx = get_pending_for_file(lookup_target)
    if pending_tx and pending_tx.get("proposed_content") is not None:
        staged_text: str = pending_tx["proposed_content"]
        tx_id = pending_tx.get("id")
        target_name = pending_tx.get("target_file", lookup_target)
        norm_target_rel = target_name.replace("\\", "/")
        if norm_target_rel.startswith("Vault/"):
            norm_target_rel = norm_target_rel[len("Vault/") :]
        action_type = pending_tx.get("action_type", "")

        # Branch on staged action type to display high-signal context
        if action_type in ("delete", "delete_file"):
            orig_text = pending_tx.get("original_content") or ""
            banner = (
                f"[STAGED FOR DELETION IN HITL QUEUE (Tx #{tx_id} on `{target_name}`) — "
                f"Awaiting human approval]\n\n"
            )
            return f"{banner}--- {target_name} (Content prior to proposed deletion) ---\n{orig_text}"

        if record_seen:
            record_read_instructions(
                norm_target_rel,
                staged_text,
                start_line=start_line,
                end_line=end_line,
            )

        if action_type in ("move", "move_file"):
            dest_name = pending_tx.get("destination_file", "unknown")
            banner = (
                f"[STAGED TO MOVE IN HITL QUEUE (Tx #{tx_id}: `{target_name}` → `{dest_name}`) — "
                f"Showing proposed content awaiting human approval]\n\n"
            )
            if start_line is not None or end_line is not None:
                lines = staged_text.splitlines()
                s_idx = max(0, (start_line or 1) - 1)
                e_idx = min(len(lines), end_line or len(lines))
                sliced = "\n".join(f"{i + 1}: {lines[i]}" for i in range(s_idx, e_idx))
                ctx_banner = format_partial_read_context(staged_text, s_idx + 1, e_idx)
                header_line = f"--- {target_name} → {dest_name} (Lines {s_idx + 1}-{e_idx} of {len(lines)}) ---"
                if ctx_banner:
                    return f"{banner}{header_line}\n{ctx_banner}\n\n{sliced}"
                return f"{banner}{header_line}\n{sliced}"
            return f"{banner}--- {target_name} → {dest_name} ---\n{staged_text}"

        banner = (
            f"[STAGED IN HITL QUEUE (Tx #{tx_id} on `{target_name}`) — "
            f"Showing cumulative pending content awaiting human approval]\n\n"
        )
        if start_line is not None or end_line is not None:
            lines = staged_text.splitlines()
            s_idx = max(0, (start_line or 1) - 1)
            e_idx = min(len(lines), end_line or len(lines))
            sliced = "\n".join(f"{i + 1}: {lines[i]}" for i in range(s_idx, e_idx))
            ctx_banner = format_partial_read_context(staged_text, s_idx + 1, e_idx)
            header_line = f"--- {target_name} (Lines {s_idx + 1}-{e_idx} of {len(lines)}) ---"
            if ctx_banner:
                return f"{banner}{header_line}\n{ctx_banner}\n\n{sliced}"
            return f"{banner}{header_line}\n{sliced}"
        return f"{banner}--- {target_name} ---\n{staged_text}"

    # 2. Otherwise read directly from disk
    disk_result = read_note_content(
        note_path=file_path,
        domain_path=None,
        start_line=start_line,
        end_line=end_line,
        start_page=start_page,
        end_page=end_page,
    )
    if (
        record_seen
        and resolved_path is not None
        and resolved_path.suffix.lower() != ".pdf"
        and not disk_result.startswith(("Error", "File not found", "Multiple files found"))
    ):
        try:
            rel_vault_path = str(resolved_path.relative_to(VAULT_PATH.resolve())).replace("\\", "/")
            raw_disk_text = resolved_path.read_text(encoding="utf-8")
            record_read_instructions(
                rel_vault_path,
                raw_disk_text,
                start_line=start_line,
                end_line=end_line,
            )
        except (OSError, UnicodeDecodeError):
            pass
    return disk_result


# `context_files: Optional[List[str]]` lists Vault paths, unique note titles, or `cache://...` captures to pre-hydrate.
# `task_prompt: Optional[str]` enables deterministic auto-discovery of touched `Section Instructions.md` files.
# -> tuple[Optional[str], Optional[str]] returns (prehydrated_markdown, None) on success or (None, fail_fast_error) if any path fails.
def hydrate_subagent_context_files(
    context_files: Optional[List[str]],
    *,
    task_prompt: Optional[str] = None,
    auto_discover_section_instructions: bool = True,
) -> tuple[Optional[str], Optional[str]]:
    """Pre-hydrates Vault files, auto-discovered `Section Instructions.md`, and `cache://` captures for `spawn_subagent`."""
    from nexus.core.conversation_cache import (
        format_captures_manifest,
        format_chat_blocks_manifest,
        get_active_conversation_id,
        get_capture,
        is_cache_ref,
    )
    from nexus.core.hitl_queue import get_pending_for_file
    from nexus.core.instruction_guard import (
        discover_section_instructions_for_subagent,
        read_raw_vault_text_with_hitl,
        record_read_instructions,
    )
    from nexus.shared_tools.vault_reader import find_nearest_directory_and_matches, resolve_vault_note_path

    if not context_files and not (auto_discover_section_instructions and (task_prompt or "").strip()):
        return None, None

    active_convo = get_active_conversation_id()

    # Deduplicate requested paths while preserving caller order so identical files are never injected twice.
    seen_refs: set[str] = set()
    ordered_refs: List[str] = []
    for raw in (context_files or []):
        cleaned = (raw or "").strip()
        key = cleaned.lower()
        if not cleaned:
            ordered_refs.append("")
            continue
        if key not in seen_refs:
            seen_refs.add(key)
            ordered_refs.append(cleaned)

    resolved_sections: List[str] = []
    seen_resolved_labels: set[str] = set()
    failure_blocks: List[str] = []
    resolved_vault_rel_paths: List[str] = []
    prehydrated_records: List[tuple[str, str]] = []

    # Step 1: Resolve explicit `context_files` (with fail-fast diagnostics before any LLM call).
    for ref in ordered_refs:
        if not ref:
            failure_blocks.append("- `<empty string>`: Error: Path cannot be empty.")
            continue

        # Support `cache://` / `cache://chat` manifests and individual `cache://...` keys (or cached URLs) in this conversation
        if ref.lower().rstrip("/") in ("cache:", "cache://", "cache://list", "cache://*"):
            if "cache://" in seen_resolved_labels:
                continue
            seen_resolved_labels.add("cache://")
            resolved_sections.append(
                f"## `cache://` (Conversation Capture Manifest)\n\n{format_captures_manifest(active_convo)}"
            )
            continue
        if ref.lower().rstrip("/") in ("cache://chat", "cache://chat/list", "cache://chat/*"):
            if "cache://chat" in seen_resolved_labels:
                continue
            seen_resolved_labels.add("cache://chat")
            resolved_sections.append(
                f"## `cache://chat` (Chat Draft Blocks Manifest)\n\n{format_chat_blocks_manifest(active_convo)}"
            )
            continue

        if is_cache_ref(ref) or ref.lower().startswith(("http://", "https://")):
            capture = get_capture(active_convo, ref)
            if capture is not None:
                cache_key = capture["cache_key"]
                if cache_key.lower() in seen_resolved_labels:
                    continue
                seen_resolved_labels.add(cache_key.lower())
                short_key = cache_key[len("cache://") :] if cache_key.startswith("cache://") else cache_key
                url_line = f"- **Source URL:** {capture['source_url']}\n" if capture.get("source_url") else ""
                resolved_sections.append(
                    f"## `{cache_key}` — {capture['title']}\n"
                    f"{url_line}"
                    f"- **Embed Verbatim Placeholder:** `{{{{cache:{short_key}}}}}`\n\n"
                    f"{capture['content']}"
                )
                continue

            hint = _format_missing_cache_keys_hint(active_convo)
            failure_blocks.append(f"- `{ref}`: Cached capture not found in conversation `{active_convo}`.\n  {hint}")
            continue

        resolved_path, err = resolve_vault_note_path(ref)
        if err and ("outside the Vault" in err or "cannot be empty" in err):
            failure_blocks.append(f"- `{ref}`: {err}")
            continue

        if resolved_path is not None:
            rel_label = str(resolved_path.relative_to(VAULT_PATH.resolve())).replace("\\", "/")
            if rel_label.lower() in seen_resolved_labels:
                continue
            content = read_vault_file_with_hitl_overlay(file_path=ref, record_seen=False)
            if content.startswith(("Error reading file", "Error reading PDF")):
                failure_blocks.append(f"- `{ref}`: {content}")
                continue
            seen_resolved_labels.add(rel_label.lower())
            resolved_sections.append(f"## `{rel_label}`\n\n{content}")
            resolved_vault_rel_paths.append(rel_label)
            raw_text = read_raw_vault_text_with_hitl(rel_label, vault_path=VAULT_PATH)
            if raw_text is not None:
                prehydrated_records.append((rel_label, raw_text))
            continue

        # Allow newly staged HITL `create_file` notes that are not yet committed to disk.
        pending_tx = get_pending_for_file(ref)
        if pending_tx and pending_tx.get("proposed_content") is not None:
            rel_label = pending_tx.get("target_file", ref)
            norm_rel = rel_label.replace("\\", "/")
            if norm_rel.startswith("Vault/"):
                norm_rel = norm_rel[len("Vault/") :]
            if norm_rel.lower() in seen_resolved_labels or rel_label.lower() in seen_resolved_labels:
                continue
            content = read_vault_file_with_hitl_overlay(file_path=ref, record_seen=False)
            seen_resolved_labels.add(rel_label.lower())
            seen_resolved_labels.add(norm_rel.lower())
            resolved_sections.append(f"## `{rel_label}`\n\n{content}")
            resolved_vault_rel_paths.append(norm_rel)
            prehydrated_records.append((norm_rel, str(pending_tx["proposed_content"])))
            continue

        # Fail-fast hallucination catch: surface nearest directory contents and similar filenames on disk.
        msg_lines = [f"- `{ref}`: {err or 'File not found on disk.'}"]
        if not err or "Multiple files found" not in err:
            diag = find_nearest_directory_and_matches(ref)
            if diag.get("nearest_dir") and diag.get("directory_listing"):
                msg_lines.append(
                    f"  Actual files in nearest matching directory (`{diag['nearest_dir']}`):\n"
                    f"  ```\n{diag['directory_listing']}\n  ```"
                )
            if diag.get("similar_files"):
                similar_list = ", ".join(f"`{p}`" for p in diag["similar_files"])
                msg_lines.append(f"  Closest matching Vault files on disk: {similar_list}")
        failure_blocks.append("\n".join(msg_lines))

    # Step 2: Fail fast on invalid explicit `context_files` before auto-discovery or ledger writes.
    if failure_blocks:
        error_report = (
            "❌ Fail-Fast Context Hydration Error: One or more `context_files` passed to `spawn_subagent` "
            "could not be resolved on disk or in the conversation cache. Subagent execution aborted before wasting LLM turns.\n\n"
            + "\n\n".join(failure_blocks)
            + "\n\nVerify actual on-disk filenames (`get_directory_structure`) or cached captures (`read_file(\"cache://\")`) and re-invoke `spawn_subagent`."
        )
        return None, error_report

    # Step 3: Auto-discover governing `Section Instructions.md` files from `context_files` and `task_prompt`.
    if auto_discover_section_instructions:
        discovered_sections = discover_section_instructions_for_subagent(
            task_prompt or "",
            resolved_context_rel_paths=resolved_vault_rel_paths,
            vault_path=VAULT_PATH,
        )
        for sec_rel in discovered_sections:
            if sec_rel.lower() in seen_resolved_labels:
                continue
            sec_content = read_vault_file_with_hitl_overlay(file_path=sec_rel, record_seen=False)
            if sec_content.startswith(("Error", "File not found", "Multiple files found")):
                continue
            seen_resolved_labels.add(sec_rel.lower())
            resolved_sections.append(
                f"## `{sec_rel}` *(Auto-Hydrated Section Instructions)*\n\n{sec_content}"
            )
            raw_sec = read_raw_vault_text_with_hitl(sec_rel, vault_path=VAULT_PATH)
            if raw_sec is not None:
                prehydrated_records.append((sec_rel, raw_sec))

    # Step 4: Return None when neither explicit `context_files` nor governed section instructions applied.
    if not resolved_sections:
        return None, None

    # Step 5: Mark all pre-hydrated files & section instructions as seen before Turn 1 so Turn-1 writes pass cleanly.
    for rel_label, raw_text in prehydrated_records:
        record_read_instructions(rel_label, raw_text, prehydrated=True)

    # Step 6: Assemble the `# Pre-Hydrated Disk Context` block prepended to the subagent's `HumanMessage`.
    prehydrated_block = (
        "# Pre-Hydrated Disk Context\n\n"
        "The following Vault files and/or cached external captures were resolved directly before execution:\n\n"
        + "\n\n---\n\n".join(resolved_sections)
    )
    return prehydrated_block, None


# Optional[int] parameters let the agent inspect specific line ranges of large logs or TOC files without blowing token budget.
# Optional[int] start_page / end_page allow inspecting specific page ranges of PDF documents.
@tool
def read_file(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
) -> str:
    """Read a Vault note (including pending HITL edits), PDF, or `cache://` external capture.

    Sliced reads automatically prepend frontmatter `instructions:` and enclosing heading rules.
    Offload >2-file reads to parallel `spawn_subagent(context_files=...)`.

    Args:
        file_path: Vault-relative path, unique filename, `"cache://"`, `"cache://chat"`, `"cache://<key>"`, or cached URL.
        start_line: Optional 1-indexed start line (inclusive).
        end_line: Optional 1-indexed end line (inclusive).
        start_page: Optional 1-indexed PDF start page (inclusive).
        end_page: Optional 1-indexed PDF end page (inclusive).
    """
    return read_vault_file_with_hitl_overlay(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        start_page=start_page,
        end_page=end_page,
    )


@tool
def search_vault(
    keyword: Optional[str] = None,
    path: Optional[str] = None,
    tags: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
) -> str:
    """Search Vault notes by keyword, multi-term `keywords=[...]` (OR-ranked), or YAML `tags`.

    Args:
        keyword: Optional single case-insensitive search term.
        path: Optional Vault-relative folder path to scope the search.
        tags: Optional YAML frontmatter tags filter.
        keywords: Optional list of search terms evaluated together in one pass.
    """
    from nexus.shared_tools.vault_reader import search_within

    return search_within(keyword=keyword, root_path=path, tags=tags, keywords=keywords)


@tool
def get_recent_modifications(
    hours: Optional[float] = None,
    since_date: Optional[str] = None,
    path: Optional[str] = None,
    limit: int = 50,
) -> str:
    """List Vault notes created or modified today (default) or within a lookback window, newest-first.

    Args:
        hours: Optional rolling lookback in hours (omit for edits since local midnight).
        since_date: Optional ISO date `'YYYY-MM-DD'`.
        path: Optional Vault-relative folder scope.
        limit: Max notes to return (default: 50).
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


# Matches universal `{{cache:<key>}}` or `{{cache:cache://<key>}}` placeholders in `create_file` / `modify_file`
_CACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*cache\s*:\s*([^{}\r\n]+?)\s*\}\}", re.IGNORECASE)


def _is_literal_cache_placeholder(text: str, match: re.Match[str]) -> bool:
    """Return True when a `{{cache:...}}` match is documentation/metasyntax rather than an active splice key.

    Leaves inline-backticked syntax examples (`` `{{cache:...}}` ``) and metasyntax placeholders
    containing `...`, `<...>`, `*`, or whitespace untouched so documenting Nexus cache syntax inside
    instruction notes never trips fail-fast cache validation.
    """
    start, end = match.span()
    if start > 0 and end < len(text) and text[start - 1] == "`" and text[end] == "`":
        return True
    inner_ref = match.group(1).strip()
    if "..." in inner_ref or any(ch in "<>*" for ch in inner_ref) or re.search(r"\s", inner_ref):
        return True
    return False


def _resolve_cache_placeholders(
    text: str,
    conversation_id: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], int]:
    """Deterministically replaces `{{cache:<key>}}` placeholders with verbatim text from `conversation_cache`.

    Uses a single-pass regex lambda callback so backslashes (e.g. `\\1`, Windows paths) inside
    cached captures are inserted literally, literal `{{cache:...}}` strings inside captured
    bodies are never recursively expanded, and inline-backticked/metasyntax doc examples pass through.
    """
    from nexus.core.conversation_cache import get_active_conversation_id, get_capture

    if not text or "{{" not in text:
        return text, None, 0

    matches = list(_CACHE_PLACEHOLDER_RE.finditer(text))
    if not matches:
        return text, None, 0

    active_matches = [m for m in matches if not _is_literal_cache_placeholder(text, m)]
    if not active_matches:
        return text, None, 0

    convo_id = (conversation_id or "").strip() or get_active_conversation_id()
    resolved_by_token: dict[str, str] = {}
    missing_refs: list[str] = []

    for match in active_matches:
        raw_token = match.group(0)
        if raw_token in resolved_by_token:
            continue
        inner_ref = match.group(1).strip()
        capture = get_capture(convo_id, inner_ref)
        if capture is None:
            if inner_ref not in missing_refs:
                missing_refs.append(inner_ref)
        else:
            resolved_by_token[raw_token] = str(capture.get("content") or "")

    if missing_refs:
        missing_display = ", ".join(f"`{{{{cache:{ref}}}}}`" for ref in missing_refs)
        hint = _format_missing_cache_keys_hint(convo_id)
        return (
            None,
            (
                f"Error: Unresolved cache placeholder(s) {missing_display} in conversation `{convo_id}`. "
                f"Check the key name (`read_file(\"cache://\")` / `read_file(\"cache://chat\")`) or capture the source first.\n\n"
                f"{hint}"
            ),
            0,
        )

    spliced = _CACHE_PLACEHOLDER_RE.sub(
        lambda m: m.group(0) if _is_literal_cache_placeholder(text, m) else resolved_by_token[m.group(0)],
        text,
    )
    return spliced, None, len(active_matches)


@tool
def modify_file(
    file_path: str,
    target: str,
    replacement: str,
    reasoning: str,
) -> str:
    """Surgically patch an exact `target` block in an existing (or pending HITL) Vault note with `replacement`.

    Stacks onto pending HITL edits in place; enforces section/frontmatter instruction hydration.
    Supports `{{cache:<key>}}` placeholders in `replacement` for deterministic verbatim capture splicing.

    Args:
        file_path: Vault-relative path or unique filename.
        target: Exact contiguous text block to replace (read via `read_file` first).
        replacement: Drop-in replacement text (or `""` to delete `target`; supports `{{cache:<key>}}`).
        reasoning: Concise justification shown in the HITL review queue.
    """
    from nexus.core.hitl_queue import add_transaction, get_file_mutation_lock, get_pending_for_file
    from nexus.shared_tools.vault_reader import resolve_vault_note_path

    if not target:
        return "Error: `target` cannot be empty in `modify_file`. Read the file first and pass the exact text block to replace, or use `create_file` for new files."

    spliced_replacement, splice_err, spliced_count = _resolve_cache_placeholders(replacement)
    if splice_err:
        return splice_err
    assert spliced_replacement is not None
    replacement = spliced_replacement

    resolved_path, err = resolve_vault_note_path(file_path)
    if err and ("outside the Vault" in err or "cannot be empty" in err):
        return err
    if resolved_path is not None:
        rel_vault_path = str(resolved_path.relative_to(VAULT_PATH.resolve())).replace("\\", "/")
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
            except UnicodeDecodeError:
                disk_content = f"[Binary file ({resolved_path.stat().st_size} bytes)]"
            except Exception as e:
                return f"Error reading existing file '{file_path}': {e}"
        else:
            pending_new = get_pending_for_file(file_path)
            disk_content = pending_new.get("original_content") if pending_new else None

        if disk_content and disk_content.startswith("[Binary file:"):
            return f"Error: Cannot perform text patch on binary file '{file_path}'. Binary files cannot be modified via `modify_file`."

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

        # Write-time instruction hydration gate: block until ancestor Section Instructions, frontmatter, & inline rules are seen.
        from nexus.core.instruction_guard import check_write_instruction_gate

        rel_for_gate = hitl_target_file[len("Vault/") :] if hitl_target_file.startswith("Vault/") else hitl_target_file
        gate_msg = check_write_instruction_gate(
            rel_for_gate,
            working_base=working_base,
            target_text=target,
            is_create=False,
            vault_path=VAULT_PATH,
        )
        if gate_msg is not None:
            return gate_msg

        tx_id = add_transaction(
            agent_name="nexus_agent",
            action_type=action_type,
            target_file=hitl_target_file,
            proposed_content=proposed_content,
            original_content=baseline_original,
            reasoning=reasoning,
        )
        splice_note = f" (spliced {spliced_count} cached capture(s) verbatim)" if spliced_count > 0 else ""
        if pending_tx:
            return (
                f"✅ Surgical modification stacked onto existing pending HITL Transaction #{tx_id} on `{hitl_target_file}`"
                f"{splice_note} (cumulative diff updated in place). Awaiting human approval."
            )
        return (
            f"✅ Surgical modification staged to HITL queue (Transaction #{tx_id} on `{hitl_target_file}`)"
            f"{splice_note}. Awaiting human approval."
        )


@tool
def create_file(
    file_path: str,
    content: str,
    reasoning: str,
    overwrite: bool = False,
) -> str:
    """Stage creation of a new Vault note (or `overwrite=True` replacement) into the HITL review queue.

    Enforces section instruction hydration and expands `{{cache:<key>}}` placeholders verbatim before staging.

    Args:
        file_path: Vault-relative path for the note.
        content: Full Markdown body (include YAML frontmatter, `**Back to:**`, and optional `{{cache:<key>}}`).
        reasoning: Concise justification for HITL review.
        overwrite: Set True only to replace an entire existing file (default: False).
    """
    from nexus.core.hitl_queue import add_transaction, get_file_mutation_lock

    clean_rel = file_path.strip().replace("\\", "/").lstrip("/")
    if clean_rel.startswith("Vault/"):
        clean_rel = clean_rel[len("Vault/"):]
    if not clean_rel.endswith(".md") and "." not in clean_rel.split("/")[-1]:
        clean_rel += ".md"

    resolved_vault = VAULT_PATH.resolve()
    candidate_target = (resolved_vault / clean_rel).resolve()
    if not candidate_target.is_relative_to(resolved_vault):
        return f"Error: Refusing to stage file outside the Vault: '{file_path}'"

    # Universal deterministic cache-splice: expand any {{cache:<key>}} placeholders verbatim before staging
    spliced_content, splice_err, spliced_count = _resolve_cache_placeholders(content)
    if splice_err:
        return splice_err
    assert spliced_content is not None
    content = spliced_content

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

        # Write-time instruction hydration gate: block until ancestor `Section Instructions.md` (and overwritten frontmatter) are seen.
        from nexus.core.instruction_guard import check_write_instruction_gate

        gate_msg = check_write_instruction_gate(
            clean_rel,
            working_base=original_content,
            target_text=None,
            is_create=True,
            vault_path=VAULT_PATH,
        )
        if gate_msg is not None:
            return gate_msg

        tx_id = add_transaction(
            agent_name="nexus_agent",
            action_type="modify" if original_content is not None else "create",
            target_file=hitl_target_file,
            proposed_content=content,
            original_content=original_content,
            reasoning=reasoning,
        )
        splice_note = f" (spliced {spliced_count} cached capture(s) verbatim)" if spliced_count > 0 else ""
        return (
            f"✅ File {'overwrite' if original_content is not None else 'creation'} staged to HITL queue "
            f"(Transaction #{tx_id} on `{hitl_target_file}`){splice_note}. Awaiting human approval."
        )


# Signature breakdown for move_file:
# - source_path: Relative Vault path (or unique filename) of the existing note to move
# - destination_path: Target relative path where the note will live after approval
# - reasoning: Plain-English justification explaining the move for human review in the HITL panel
# - overwrite: Boolean guard preventing accidental overwrites if a file already exists at destination_path
@tool
def move_file(
    source_path: str,
    destination_path: str,
    reasoning: str,
    overwrite: bool = False,
) -> str:
    """Stage an atomic Vault note move/rename/archival into the HITL review queue.

    Args:
        source_path: Existing Vault-relative path or unique note filename.
        destination_path: Target Vault-relative destination path.
        reasoning: Concise justification for moving or archiving the note.
        overwrite: Set True only to replace an existing file at `destination_path` (default: False).
    """
    from nexus.core.hitl_queue import add_transaction, get_file_mutation_lock, get_pending_for_file
    from nexus.shared_tools.vault_reader import resolve_vault_note_path

    # Phase 1: Validate input parameters and prevent empty path operations
    if not source_path or not source_path.strip():
        return "Error: `source_path` cannot be empty in `move_file`."
    if not destination_path or not destination_path.strip():
        return "Error: `destination_path` cannot be empty in `move_file`."
    if not reasoning or not reasoning.strip():
        return "Error: `reasoning` cannot be empty in `move_file`. Provide context for HITL review."

    # Phase 2: Normalize and validate destination path containment within Vault
    clean_dst = destination_path.strip().replace("\\", "/").lstrip("/")
    if clean_dst.startswith("Vault/"):
        clean_dst = clean_dst[len("Vault/"):]
    if not clean_dst.endswith(".md") and "." not in clean_dst.split("/")[-1]:
        clean_dst += ".md"

    clean_src_raw = source_path.strip().replace("\\", "/").lstrip("/")
    if clean_src_raw.startswith("Vault/"):
        clean_src_raw = clean_src_raw[len("Vault/"):]
    if not clean_src_raw.endswith(".md") and "." not in clean_src_raw.split("/")[-1]:
        clean_src_raw += ".md"

    if clean_src_raw.lower() == clean_dst.lower():
        return f"Error: Source and destination paths are identical ('Vault/{clean_src_raw}')."

    resolved_vault = VAULT_PATH.resolve()
    candidate_dst = (resolved_vault / clean_dst).resolve()
    if not candidate_dst.is_relative_to(resolved_vault):
        return f"Error: Refusing to move file outside the Vault: '{destination_path}'"

    # Phase 3: Resolve source note on disk (or verify pending staged status)
    resolved_src, err = resolve_vault_note_path(source_path)
    if err and ("outside the Vault" in err or "cannot be empty" in err):
        return err

    if resolved_src is not None:
        rel_src = str(resolved_src.relative_to(resolved_vault)).replace("\\", "/")
        hitl_source_file = f"Vault/{rel_src}"
    else:
        pending_src = get_pending_for_file(source_path)
        if pending_src is None:
            return err or f"Error: Source file '{source_path}' does not exist in the Vault."
        hitl_source_file = pending_src["target_file"]

    hitl_dest_file = f"Vault/{clean_dst}"

    # Phase 4: Guard against identity moves (source == destination)
    if hitl_source_file.lower() == hitl_dest_file.lower():
        return f"Error: Source and destination paths are identical ('{hitl_source_file}')."

    # Phase 5: Check destination collision guard (unless overwrite=True)
    full_dst_path = resolved_vault / clean_dst
    if full_dst_path.exists() and not overwrite:
        return (
            f"Error: Destination file '{hitl_dest_file}' already exists on disk. "
            f"Pass `overwrite=True` if you intentionally intend to replace it."
        )

    # Phase 6: Thread-safe locking across both source and destination target paths
    with get_file_mutation_lock(hitl_source_file):
        with get_file_mutation_lock(hitl_dest_file):
            # Check if source has pending staged edits so proposed content carries edits forward
            pending_tx = get_pending_for_file(hitl_source_file)
            if resolved_src is not None:
                try:
                    disk_content: Optional[str] = resolved_src.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    disk_content = f"[Binary file ({resolved_src.stat().st_size} bytes)]"
                except Exception as e:
                    return f"Error reading source file '{source_path}': {e}"
            else:
                disk_content = pending_tx.get("original_content") if pending_tx else None

            # Carry pending content if source was already modified in queue; otherwise use disk baseline
            content_to_move = (
                pending_tx["proposed_content"]
                if (pending_tx and pending_tx.get("proposed_content") is not None)
                else (disk_content or "")
            )
            baseline_original = (
                pending_tx.get("original_content")
                if (pending_tx and pending_tx.get("original_content") is not None)
                else disk_content
            )

            tx_id = add_transaction(
                agent_name="nexus_agent",
                action_type="move",
                target_file=hitl_source_file,
                destination_file=hitl_dest_file,
                proposed_content=content_to_move,
                original_content=baseline_original,
                reasoning=reasoning,
            )
            return (
                f"✅ File move staged to HITL queue (Transaction #{tx_id}: `{hitl_source_file}` → `{hitl_dest_file}`). "
                f"Awaiting human approval."
            )


# Signature breakdown for delete_file:
# - file_path: Relative Vault path (or unique filename) of the existing note to delete
# - reasoning: Plain-English explanation justifying the deletion for human HITL review
@tool
def delete_file(
    file_path: str,
    reasoning: str,
) -> str:
    """Stage deletion of a Vault note into the HITL review queue (prefer `move_file` for archival).

    Args:
        file_path: Vault-relative path or unique filename to delete.
        reasoning: Concise justification for HITL review.
    """
    from nexus.core.hitl_queue import add_transaction, get_file_mutation_lock, get_pending_for_file, update_transaction_status
    from nexus.shared_tools.vault_reader import resolve_vault_note_path

    # Phase 1: Validate input parameters
    if not file_path or not file_path.strip():
        return "Error: `file_path` cannot be empty in `delete_file`."
    if not reasoning or not reasoning.strip():
        return "Error: `reasoning` cannot be empty in `delete_file`. Explain why deletion is warranted."

    # Phase 2: Resolve note on disk or check pending staged queue
    resolved_path, err = resolve_vault_note_path(file_path)
    if err and ("outside the Vault" in err or "cannot be empty" in err):
        return err

    resolved_vault = VAULT_PATH.resolve()
    if resolved_path is not None:
        rel_vault_path = str(resolved_path.relative_to(resolved_vault)).replace("\\", "/")
        hitl_target_file = f"Vault/{rel_vault_path}"
    else:
        pending_tx = get_pending_for_file(file_path)
        if pending_tx is None:
            return err or f"Error: File '{file_path}' does not exist in the Vault."
        hitl_target_file = pending_tx["target_file"]

    # Phase 3: Lock target file and stage deletion
    with get_file_mutation_lock(hitl_target_file):
        pending_tx = get_pending_for_file(hitl_target_file)

        # If note was staged as a pending create but never committed to disk, discard it cleanly
        if pending_tx and pending_tx.get("action_type") == "create" and resolved_path is None:
            update_transaction_status(pending_tx["id"], "rejected")
            return f"✅ Discarded pending staged note creation for `{hitl_target_file}` (Tx #{pending_tx['id']} cancelled)."

        if resolved_path is not None:
            try:
                disk_content: Optional[str] = resolved_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                disk_content = f"[Binary file ({resolved_path.stat().st_size} bytes)]"
            except Exception as e:
                return f"Error reading existing file '{file_path}': {e}"
        else:
            disk_content = pending_tx.get("original_content") if pending_tx else None

        baseline_original = (
            pending_tx.get("original_content")
            if (pending_tx and pending_tx.get("original_content") is not None)
            else disk_content
        )

        tx_id = add_transaction(
            agent_name="nexus_agent",
            action_type="delete",
            target_file=hitl_target_file,
            proposed_content="",
            original_content=baseline_original,
            reasoning=reasoning,
        )
        return (
            f"✅ File deletion staged to HITL queue (Transaction #{tx_id} on `{hitl_target_file}`). "
            f"Awaiting human approval."
        )


# ── 4. External Communication & Schedule Tools (Gmail & Calendar) ────────────

# Cap each email body so a long newsletter cannot blow the context window
_BODY_CHAR_LIMIT = 4000


# Maximum full MIME bodies hydrated automatically when `include_body=True` is passed in sweep mode
_FETCH_EMAILS_AUTO_BODY_CAP = 20


# Signature breakdown for _hydrate_email_message_entry:
# - msg_id: Gmail message ID to fetch full MIME content for.
# - candidate_accounts: ordered account aliases/emails to attempt (`[msg_acc]` from summary, or all active accounts).
# - summary: optional lightweight metadata dict from `list_messages()` used for graceful error fallback.
# - service_cache: per-call cache mapping `account -> Gmail Resource` to avoid rebuilding Discovery clients.
# - gmail_engine_mod: imported `nexus.shared_tools.gmail_engine` module reference.
# - Returns: structured dict with full body (up to `_BODY_CHAR_LIMIT`), non-text metadata, and `cache://email/<id>` key.
def _hydrate_email_message_entry(
    msg_id: str,
    candidate_accounts: List[str],
    summary: Optional[Dict[str, Any]],
    service_cache: dict[str, object],
    gmail_engine_mod: Any,
) -> Dict[str, Any]:
    """Fetch, cache verbatim (`cache://email/<id>`), and format one full email entry with graceful fallback."""
    last_exc: Optional[Exception] = None
    msg: Optional[Dict[str, Any]] = None
    resolved_acc = candidate_accounts[0] if candidate_accounts else "default"

    for acc in candidate_accounts:
        try:
            if acc not in service_cache:
                service_cache[acc] = gmail_engine_mod.get_gmail_service(account=acc)
            msg = gmail_engine_mod.get_message(msg_id, account=acc, service=service_cache[acc])
            resolved_acc = acc
            break
        except Exception as exc:
            last_exc = exc

    if msg is None:
        base_summary = summary or {}
        fallback_entry: Dict[str, Any] = {
            "id": msg_id,
            "account": base_summary.get("account") or resolved_acc,
            "thread_id": base_summary.get("thread_id", ""),
            "subject": base_summary.get("subject", ""),
            "sender": base_summary.get("sender", ""),
            "date": base_summary.get("date", ""),
            "labels": base_summary.get("labels", []),
            "snippet": base_summary.get("snippet", ""),
            "body_error": f"Failed to hydrate full body: {last_exc}",
        }
        return fallback_entry

    full_body = str(msg.get("body") or "")
    attachments = msg.get("attachments") or []
    inline_media = msg.get("inline_media") or []
    non_text_notice = str(msg.get("non_text_notice") or "").strip()
    effective_acc = msg.get("account", resolved_acc)

    cache_key: Optional[str] = None
    try:
        from nexus.core.conversation_cache import get_active_conversation_id, put_capture

        convo_id = get_active_conversation_id()
        attachment_lines = ""
        if attachments:
            att_summary = ", ".join(
                f"{a['filename']} ({a['mime_type']}, {a['size']})"
                if isinstance(a, dict)
                else str(a)
                for a in attachments
            )
            attachment_lines += f"- **Attachments:** {att_summary}\n"
        if non_text_notice:
            attachment_lines += f"- **Non-Text Notice:** {non_text_notice}\n"

        email_doc = (
            f"# {msg.get('subject') or '(No Subject)'}\n"
            f"- **From:** {msg.get('sender') or ''}\n"
            f"- **Date:** {msg.get('date') or ''}\n"
            f"- **Account:** {effective_acc}\n"
            f"- **Message ID:** {msg['id']}\n"
            f"- **Thread ID:** {msg.get('thread_id') or ''}\n"
            f"{attachment_lines}\n"
            f"{full_body}"
        )
        cache_key = put_capture(
            conversation_id=convo_id,
            source_type="email",
            title=str(msg.get("subject") or f"Email {msg['id']}"),
            content=email_doc,
            source_url=None,
            cache_key=f"cache://email/{msg['id']}",
        )
    except Exception:
        cache_key = None

    email_entry: Dict[str, Any] = {
        "id": msg["id"],
        "account": effective_acc,
        "thread_id": msg.get("thread_id", ""),
        "subject": msg.get("subject", ""),
        "sender": msg.get("sender", ""),
        "date": msg.get("date", ""),
        "labels": msg.get("labels", (summary or {}).get("labels", [])),
        "body": full_body[:_BODY_CHAR_LIMIT],
    }
    # Only include non-text metadata keys when present so plain-text emails stay lean
    if attachments:
        email_entry["attachments"] = attachments
    if inline_media:
        email_entry["inline_media"] = inline_media
    if non_text_notice:
        email_entry["non_text_notice"] = non_text_notice
    if cache_key:
        email_entry["cache_key"] = cache_key
    return email_entry


# Signature breakdown for fetch_emails:
# - count: int = 10 limits the total number of emails to collect across accounts.
# - include_archived: bool = False sweeps `in:inbox` (all inbox emails regardless of labels) by default; True includes archived mail.
# - query: str = "" optional Gmail search filter (leave empty for a general inbox sweep).
# - account: str = "all" targets all configured Gmail accounts or a single concrete alias/email.
# - include_body: bool = False returns lightweight metadata + snippet by default (two-phase scan-then-hydrate); True hydrates up to 20 bodies immediately.
# - message_ids: Optional[List[str]] = None batch-hydrates full bodies (plus cache://email/<id> & non-text notices) for exact selected Gmail IDs.
@tool
def fetch_emails(
    count: int = 10,
    include_archived: bool = False,
    query: str = "",
    account: str = "all",
    include_body: bool = False,
    message_ids: Optional[List[str]] = None,
) -> str:
    """Two-phase Gmail search and selective body hydration across connected accounts.

    Scans `in:inbox` metadata+snippets by default (`include_body=False`), then batch-hydrates full bodies
    and `cache://email/<id>` captures via `message_ids=[...]`. Follow `[[Protocol - Email Triage]]` on sweeps.

    Args:
        count: Max emails to return during scan (default: 10).
        include_archived: Set True to include non-inbox archived mail (default: False).
        query: Optional Gmail search syntax (combine terms with `OR`).
        account: `'all'` (default), `'default'`, or specific account alias/email.
        include_body: Set True to hydrate up to 20 full bodies immediately (default: False).
        message_ids: Exact Gmail IDs to batch-hydrate full bodies and `cache://email/<id>` captures.
    """
    from nexus.shared_tools import gmail_engine

    try:
        # Cache one Discovery Resource per account across the loop so we don't rebuild clients N times
        service_cache: dict[str, object] = {}

        # Mode 1: Selective batch hydration by exact Gmail message IDs
        if message_ids:
            deduped_ids: List[str] = []
            seen_ids: set[str] = set()
            for raw_id in message_ids:
                cleaned_id = str(raw_id or "").strip()
                if cleaned_id and cleaned_id not in seen_ids:
                    seen_ids.add(cleaned_id)
                    deduped_ids.append(cleaned_id)

            if account.lower() == "all":
                candidate_accounts = [
                    acc for acc in gmail_engine.list_available_accounts()
                    if acc.lower() != "all"
                ] or ["default"]
            else:
                candidate_accounts = [account]

            hydrated = [
                _hydrate_email_message_entry(
                    msg_id=mid,
                    candidate_accounts=candidate_accounts,
                    summary=None,
                    service_cache=service_cache,
                    gmail_engine_mod=gmail_engine,
                )
                for mid in deduped_ids
            ]
            return json.dumps(hydrated, ensure_ascii=False)

        # Mode 2: Search / sweep (`list_messages` metadata+snippets first; optional immediate body hydration)
        summaries = gmail_engine.list_messages(
            query=query,
            max_results=count,
            account=account,
            include_archived=include_archived,
        )
        emails = []
        for idx, s in enumerate(summaries):
            msg_acc = s.get("account") or (account if account.lower() != "all" else "default")
            if not include_body:
                emails.append({
                    "id": s.get("id"),
                    "account": msg_acc,
                    "thread_id": s.get("thread_id"),
                    "subject": s.get("subject"),
                    "sender": s.get("sender"),
                    "date": s.get("date"),
                    "labels": s.get("labels", []),
                    "snippet": s.get("snippet", ""),
                })
                continue

            if idx >= _FETCH_EMAILS_AUTO_BODY_CAP:
                emails.append({
                    "id": s.get("id"),
                    "account": msg_acc,
                    "thread_id": s.get("thread_id"),
                    "subject": s.get("subject"),
                    "sender": s.get("sender"),
                    "date": s.get("date"),
                    "labels": s.get("labels", []),
                    "snippet": s.get("snippet", ""),
                    "body_omitted_reason": (
                        f"Summary only beyond first {_FETCH_EMAILS_AUTO_BODY_CAP} full bodies; "
                        f"call fetch_emails(message_ids=['{s.get('id')}'], account='{msg_acc}') for full body."
                    ),
                })
                continue

            emails.append(
                _hydrate_email_message_entry(
                    msg_id=s["id"],
                    candidate_accounts=[msg_acc],
                    summary=s,
                    service_cache=service_cache,
                    gmail_engine_mod=gmail_engine,
                )
            )
        return json.dumps(emails, ensure_ascii=False)
    except Exception as exc:
        return json.dumps([{"error": f"fetch_emails failed: {exc}"}])


# Shared multi-account Gmail resolution helper used by `fetch_emails`, `modify_emails`, and `trash_emails`.
def _resolve_gmail_candidate_accounts(account: str, gmail_engine_mod: Any) -> List[str]:
    """Return concrete Gmail account aliases to query, expanding `'all'` without triggering reserved alias loops."""
    if (account or "").strip().lower() == "all":
        return [
            acc for acc in gmail_engine_mod.list_available_accounts()
            if acc.lower() != "all"
        ] or ["default"]
    return [account or "default"]


# Executes a per-message Gmail write callable across concrete candidate accounts with client caching.
# - op_fn: Callable taking `(message_id, account, service)` and returning a JSON-serializable status value.
def _run_gmail_batch_action(
    message_ids: List[str],
    account: str,
    action_name: str,
    op_fn: Any,
) -> str:
    """Apply a Gmail mutation across deduplicated `message_ids` with multi-account fallback and JSON reporting."""
    from nexus.shared_tools import gmail_engine

    # Deduplicate non-empty message IDs while preserving caller order
    deduped_ids: List[str] = []
    seen: set[str] = set()
    for raw_id in message_ids or []:
        cleaned = str(raw_id or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped_ids.append(cleaned)

    if not deduped_ids:
        return json.dumps({"error": f"`message_ids` cannot be empty in `{action_name}`."})

    try:
        candidates = _resolve_gmail_candidate_accounts(account, gmail_engine)
    except Exception as exc:
        return json.dumps({"error": f"{action_name} failed to resolve accounts: {exc}"})

    # Cache one Gmail Discovery client per account across all message IDs in the batch
    service_cache: dict[str, object] = {}
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for mid in deduped_ids:
        last_exc: Optional[Exception] = None
        matched = False
        for acc in candidates:
            try:
                if acc not in service_cache:
                    service_cache[acc] = gmail_engine.get_gmail_service(account=acc)
                outcome = op_fn(mid, acc, service_cache[acc], gmail_engine)
                results.append({"id": mid, "account": acc, "result": outcome})
                matched = True
                break
            except Exception as exc:
                last_exc = exc
        if not matched:
            errors.append({"id": mid, "error": str(last_exc or "Unknown error")})

    return json.dumps({"results": results, "errors": errors}, ensure_ascii=False)


# Signature breakdown for modify_emails:
# - message_ids: List[str] of Gmail message IDs to mutate in one batch.
# - add_labels / remove_labels: Optional[List[str]] of human label names (e.g. "INBOX", "UNREAD", "Receipts").
# - account: str target mailbox alias or "all" to probe configured accounts for each ID.
@tool
def modify_emails(
    message_ids: List[str],
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
    account: str = "default",
) -> str:
    """Add or remove Gmail labels on message IDs (e.g. `remove_labels=["INBOX"]` to archive).

    Confirm with the user before mutating mail per `[[Protocol - Email Triage]]`.

    Args:
        message_ids: Gmail message IDs to update.
        add_labels: Label names to add (e.g. `["Receipts"]`).
        remove_labels: Label names to remove (e.g. `["INBOX", "UNREAD"]`).
        account: Target account alias or `"all"`.
    """
    if not add_labels and not remove_labels:
        return json.dumps({"error": "Specify at least one label in `add_labels` or `remove_labels`."})

    return _run_gmail_batch_action(
        message_ids=message_ids,
        account=account,
        action_name="modify_emails",
        op_fn=lambda mid, acc, svc, gm: gm.modify_labels(
            message_id=mid,
            add=add_labels,
            remove=remove_labels,
            account=acc,
            service=svc,
        ),
    )


@tool
def trash_emails(
    message_ids: List[str],
    account: str = "default",
) -> str:
    """Move Gmail message IDs to Trash (recoverable for 30 days; confirm with user first).

    Args:
        message_ids: Gmail message IDs to move to Trash.
        account: Target account alias or `"all"`.
    """
    return _run_gmail_batch_action(
        message_ids=message_ids,
        account=account,
        action_name="trash_emails",
        op_fn=lambda mid, acc, svc, gm: gm.trash_message(message_id=mid, account=acc, service=svc),
    )


@tool
def create_email_draft(
    to: str,
    subject: str,
    body: str,
    reply_to_message_id: Optional[str] = None,
    account: str = "default",
    send_as: Optional[str] = None,
) -> str:
    """Create a Gmail draft without sending (user reviews and sends manually in Gmail).

    Args:
        to: Recipient email address(es), comma-separated.
        subject: Email subject line.
        body: Plain-text draft body.
        reply_to_message_id: Optional Gmail message ID to thread this draft as a reply.
        account: Concrete account alias (or `"all"` when `send_as` is provided).
        send_as: Optional verified Gmail `'Send mail as'` email for the `From` header.
    """
    from nexus.shared_tools import gmail_engine

    try:
        res = gmail_engine.create_draft(
            to=to,
            subject=subject,
            body=body,
            reply_to_message_id=reply_to_message_id,
            account=account,
            send_as=send_as,
        )
        return json.dumps(res, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"create_email_draft failed: {exc}"})


@tool
def get_calendar_schedule(days_ahead: int = 1, days_back: int = 0) -> str:
    """Fetch Google Calendar events for today, past days (`days_back`), or upcoming days (`days_ahead`).

    Args:
        days_ahead: Days forward from today (default: 1; set 0 when querying only past days).
        days_back: Days backward from today (default: 0).
    """
    from datetime import datetime, time, timedelta
    from nexus.shared_tools.calendar_engine import format_events_as_markdown, list_events

    now_local = datetime.now().astimezone()
    start_dt = datetime.combine(now_local.date() - timedelta(days=max(0, days_back)), time.min).astimezone()
    end_offset = max(-days_back, days_ahead - 1)
    end_dt = datetime.combine(now_local.date() + timedelta(days=end_offset), time.max).astimezone()

    # Execute Google Calendar API query within defensive try/except wrapper
    try:
        events = list_events(start_iso=start_dt.isoformat(), end_iso=end_dt.isoformat())
        if start_dt.date() == end_dt.date():
            title = f"Schedule ({start_dt.strftime('%A, %b %d')})"
        else:
            title = f"Schedule ({start_dt.strftime('%a, %b %d')} – {end_dt.strftime('%a, %b %d')})"
        return format_events_as_markdown(events, title=title)
    except Exception as exc:
        return f"❌ Failed to query calendar schedule: {exc}"


@tool
def create_calendar_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    location: str = "",
) -> str:
    """Create a Google Calendar event.

    Args:
        summary: Event title.
        start_iso: RFC3339 datetime or `'YYYY-MM-DD'` date.
        end_iso: RFC3339 datetime or `'YYYY-MM-DD'` date.
        description: Optional event description.
        location: Optional location or meeting link.
    """
    from nexus.shared_tools.calendar_engine import create_event

    # Call calendar creation service with defensive error handling
    try:
        res = create_event(
            summary=summary,
            start_iso=start_iso,
            end_iso=end_iso,
            description=description,
            location=location,
        )
        if res.get("status") == "error":
            return f"❌ Failed to create calendar event '{summary}': {res.get('error')}"
        return f"✅ Event created: '{res.get('summary')}' (ID: {res.get('id')}) from {res.get('start')} to {res.get('end')}."
    except Exception as exc:
        return f"❌ Failed to create calendar event '{summary}': {exc}"


@tool
def update_calendar_event(
    event_id: str,
    summary: str = "",
    start_iso: str = "",
    end_iso: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """Update an existing Google Calendar event by `event_id` (from `get_calendar_schedule`).

    Args:
        event_id: Google Calendar event ID.
        summary: Optional updated title.
        start_iso: Optional updated RFC3339 start time.
        end_iso: Optional updated RFC3339 end time.
        description: Optional updated description.
        location: Optional updated location.
    """
    from nexus.shared_tools.calendar_engine import update_event

    # Defensively intercept HttpError (e.g. 404 Not Found) so invalid event IDs emit actionable strings rather than crashing the turn
    try:
        res = update_event(
            event_id=event_id,
            summary=summary or None,
            start_iso=start_iso or None,
            end_iso=end_iso or None,
            description=description or None,
            location=location or None,
        )
        if res.get("status") == "error":
            return f"❌ Failed to update calendar event '{event_id}': {res.get('error')}. Verify event ID with get_calendar_schedule()."
        return f"✅ Event updated: '{res.get('summary')}' (ID: {res.get('id')})."
    except Exception as exc:
        return f"❌ Failed to update calendar event '{event_id}': {exc}"


@tool
def delete_calendar_event(event_id: str) -> str:
    """Delete an event from Google Calendar by its unique ID.

    Args:
        event_id: The unique Google Calendar event ID (as returned by `get_calendar_schedule`).
    """
    from nexus.shared_tools.calendar_engine import delete_event

    # Delete calendar event defensively; returns clean status string back to LLM
    try:
        ok = delete_event(event_id=event_id)
        if ok:
            return f"✅ Event deleted: ID '{event_id}'."
        return f"❌ Failed to delete event '{event_id}': Event not found or deletion failed on Google Calendar."
    except Exception as exc:
        return f"❌ Failed to delete event '{event_id}': {exc}"


# ── 5. Live Web, Browser Bridge, YouTube & Domain Utilities ──────────────────

# Signature breakdown:
# - query: Search string sent to Tavily (avoid hardcoding stale year anchors unless looking for historical data)
# - max_results: Bounded result count (default 5)
# - search_depth: "basic" (fast lookup) or "advanced" (deep extraction for clinical/technical/company research)
# - topic: "general", "news", or "finance"
# - include_domains / exclude_domains: Optional domain filter lists (e.g. ["pubmed.ncbi.nlm.nih.gov"])
@tool
def search_web(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    topic: str = "general",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
) -> str:
    """Search the live web via Tavily; returns a Markdown digest with exact source URLs.

    Args:
        query: Search query string.
        max_results: Max results (1–15, default: 5).
        search_depth: `"basic"` (default) or `"advanced"`.
        topic: `"general"` (default), `"news"`, or `"finance"`.
        include_domains: Optional domain allowlist.
        exclude_domains: Optional domain blocklist.
    """
    from nexus.shared_tools.web_search import execute_web_search, format_search_results_as_markdown

    data = execute_web_search(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        topic=topic,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
    )
    return format_search_results_as_markdown(data)


# Signature breakdown for list_browser_tabs:
# - group_name: Optional case-insensitive Chrome Tab Group title filter (e.g. "Jobs")
# - query: Optional substring filter matching tab title, URL, or group name
# - active_only: When True, returns only the currently focused tab in each Chrome window
@tool
def list_browser_tabs(
    group_name: Optional[str] = None,
    query: Optional[str] = None,
    active_only: bool = False,
) -> str:
    """List open Chrome tabs and Chrome Tab Groups (`tab_id`, title, URL, group) read-only.

    Args:
        group_name: Optional Chrome Tab Group title filter.
        query: Optional substring filter across title, URL, or group.
        active_only: Set True for only the focused tab (default: False).
    """
    from nexus.shared_tools.browser_bridge import format_tabs_as_markdown, list_tabs

    result = list_tabs(group_name=group_name, query=query, active_only=active_only)
    return format_tabs_as_markdown(result)


# Signature breakdown for read_browser_tabs:
# - tab_ids: Optional list of integer Chrome tab IDs (from `list_browser_tabs`) to extract
# - group_name: Optional Chrome Tab Group title to extract all tabs from
# - query: Optional substring filter on tab title or URL
# - active_only: Set True to read only the currently focused Chrome tab
# - max_chars: Maximum Markdown character budget per tab (default 15,000)
# - include_refs: Set True when inspecting a form to stamp `ref=f0_1` handles for `fill_browser_form`
@tool
def read_browser_tabs(
    tab_ids: Optional[List[int]] = None,
    group_name: Optional[str] = None,
    query: Optional[str] = None,
    active_only: bool = False,
    max_chars: int = 15000,
    include_refs: bool = False,
) -> str:
    """Extract Markdown from live authenticated Chrome tabs and cache under `cache://tab/<slug>`.

    Args:
        tab_ids: Optional Chrome `tab_id` integers to read.
        group_name: Optional Chrome Tab Group title filter.
        query: Optional title/URL substring filter.
        active_only: Set True for only the focused tab.
        max_chars: Max Markdown chars per tab (default: 15000).
        include_refs: Set True to stamp `ref` handles for `fill_browser_form` (default: False).
    """
    from nexus.shared_tools.browser_bridge import format_tab_reads_as_markdown, read_tabs

    result = read_tabs(
        tab_ids=tab_ids,
        group_name=group_name,
        query=query,
        active_only=active_only,
        max_chars=max_chars,
        include_refs=include_refs,
    )
    return format_tab_reads_as_markdown(result)


# Signature breakdown for open_browser_tabs:
# - urls: List[str] of 1-10 HTTP(S) URLs to open into Chrome tabs
# - group_name: Optional Chrome Tab Group title (reuses existing group in window or creates a new one)
# - group_color: Chrome Tab Group color enum (default "blue")
# - activate_first: If True, focuses the first newly opened tab
@tool
def open_browser_tabs(
    urls: List[str],
    group_name: Optional[str] = None,
    group_color: str = "blue",
    activate_first: bool = False,
) -> str:
    """Open 1–10 `http(s)` URLs in Chrome, optionally grouped into a Chrome Tab Group.

    Args:
        urls: 1–10 `http://` or `https://` URLs.
        group_name: Optional Chrome Tab Group title.
        group_color: Group color (`blue`, `grey`, `red`, `yellow`, `green`, `pink`, `purple`, `cyan`, `orange`).
        activate_first: Focus the first opened tab (default: False).
    """
    from nexus.shared_tools.browser_bridge import format_open_tabs_as_markdown, open_tabs

    result = open_tabs(
        urls=urls,
        group_name=group_name,
        group_color=group_color,
        activate_first=activate_first,
    )
    return format_open_tabs_as_markdown(result)


# Signature breakdown for fill_browser_form:
# - tab_id: int Chrome tab ID returned by `list_browser_tabs` / `read_browser_tabs`
# - fields: Dict[str, Any] mapping transient form refs (`f0_1`, etc.) to draft field values
@tool
def fill_browser_form(
    tab_id: int,
    fields: Dict[str, Any],
) -> str:
    """Draft-fill visible form fields in a Chrome tab using `ref` handles from `read_browser_tabs(..., include_refs=True)`.

    Highlights filled controls for human review; never submits forms or fills passwords/payment/SSN fields.

    Args:
        tab_id: Target Chrome `tab_id`.
        fields: Map of element `ref` handles (e.g. `{"f0_1": "Jane Doe"}`) to draft values.
    """
    from nexus.shared_tools.browser_bridge import fill_form, format_fill_form_as_markdown

    result = fill_form(tab_id=tab_id, fields=fields)
    return format_fill_form_as_markdown(result)


# Signature breakdown for read_webpage:
# - url: Target http(s) URL to extract (checks `conversation_cache` first before fetching live HTML).
# - output_format: Extraction format (`"markdown"`, `"txt"`, `"json"`, `"xml"`).
@tool
def read_webpage(url: str, output_format: str = "markdown") -> str:
    """Extract clean webpage content (`trafilatura` + JSON-LD/meta fallback) and cache under `cache://web/<slug>`.

    Args:
        url: Target `http://` or `https://` URL.
        output_format: Output format (`"markdown"`, `"txt"`, `"json"`, or `"xml"`, default: `"markdown"`).
    """
    from nexus.shared_tools.read_webpage import scrape_url_with_cache

    content, cache_key = scrape_url_with_cache(url, output_format=output_format)
    if not content:
        return f"Error: Could not extract content from '{url}'."

    if cache_key and output_format in ("markdown", "txt"):
        short_key = cache_key[len("cache://"):] if cache_key.startswith("cache://") else cache_key
        return (
            f"- **Cache Key:** `{cache_key}` *(embed verbatim via `{{{{cache:{short_key}}}}}`)*\n\n"
            f"{content}"
        )
    return content


# Signature breakdown for get_youtube_transcript:
# - url_or_id: YouTube watch/short URL or 11-char video ID.
# - save_to_inbox: bool = False writes `Vault/0. Inbox/YouTube - <title>.md` (or `output_note_path`) directly.
# - output_note_path: Optional[str] Vault-relative path override (validated inside `VAULT_PATH`).
@tool
def get_youtube_transcript(
    url_or_id: str,
    save_to_inbox: bool = False,
    output_note_path: Optional[str] = None,
) -> str:
    """Fetch a YouTube video's transcript, cache under `cache://youtube/<id>`, and optionally save to Inbox.

    Args:
        url_or_id: YouTube URL or video ID.
        save_to_inbox: Save a formatted capture note to `Vault/0. Inbox/` (default: False).
        output_note_path: Optional Vault-relative path to save the note.
    """
    from nexus.shared_tools.youtube_transcript import fetch_youtube_transcript

    return fetch_youtube_transcript(
        url_or_id=url_or_id,
        save_to_inbox=save_to_inbox,
        output_note_path=output_note_path,
    )


# Signature breakdown for render_resume_documents:
# - file_paths: List[str] of resume/cover-letter paths in `3.1.3. Professional Portfolio & Evidence/` (or `["all"]`).
# - formats: Optional[List[str]] subset of `["pdf", "docx"]` (defaults to both).
@tool
def render_resume_documents(
    file_paths: List[str],
    formats: Optional[List[str]] = None,
) -> str:
    """Compile portfolio Markdown resumes/cover letters to PDF (Playwright) and DOCX with page-fill metrics.

    Args:
        file_paths: Paths inside `3.1.3. Professional Portfolio & Evidence/` (or `["all"]`).
        formats: Formats to render (`["pdf", "docx"]` default).
    """
    from nexus.shared_tools.resume_engine.service import render_documents

    try:
        res = render_documents(file_paths=file_paths, formats=formats)
        return json.dumps(res, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": f"render_resume_documents failed: {exc}"})


# Signature breakdown for ingest_phone_chat:
# - screens: int = 1 number of phone screens to scroll/capture via Android ADB.
# - raw: bool = False emits plain `[Me]/[Them]` lines instead of formatted Markdown.
# - save_to_inbox: bool = True persists the captured conversation to `Vault/0. Inbox/`.
# - device: Optional[str] ADB device serial when multiple Android devices are attached.
@tool
def ingest_phone_chat(
    screens: int = 1,
    raw: bool = False,
    save_to_inbox: bool = True,
    device: Optional[str] = None,
) -> str:
    """Capture the visible Android messaging thread over USB/wireless ADB and optionally save to `0. Inbox/`.

    Args:
        screens: Number of screens to scroll up and capture (default: 1).
        raw: Return plain `[Me]`/`[Them]` lines instead of Markdown (default: False).
        save_to_inbox: Save capture note under `Vault/0. Inbox/` (default: True).
        device: Optional ADB device serial.
    """
    from datetime import datetime
    from nexus.shared_tools import ingest_phone

    try:
        # Redirect interactive print() progress banners from `ingest_phone` to stderr so MCP stdio stays valid
        with contextlib.redirect_stdout(sys.stderr):
            resolved_device = ingest_phone.check_device(device)
            messages, app_package, contact_name = ingest_phone.capture_conversation(
                resolved_device, max(1, int(screens or 1)), 1.5
            )
    except SystemExit as exc:
        return f"Error: Android ADB capture failed (exit {exc.code}). Ensure USB debugging and ADB device connection."
    except Exception as exc:
        return f"Error: Android ADB capture failed: {exc}"

    if not messages:
        return "Error: No messages extracted. Make sure a chat thread is open on the connected Android screen."

    output = (
        ingest_phone.format_raw(messages)
        if raw
        else ingest_phone.format_markdown(messages, app_package, contact_name, max(1, int(screens or 1)))
    )

    if save_to_inbox:
        app_name = ingest_phone.APP_NAMES.get(app_package, "Chat")
        safe_contact = re.sub(r"[^\w\s-]", "", contact_name or "Unknown").strip() or "Unknown"
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        out_path = (VAULT_PATH / "0. Inbox" / f"Capture - {app_name} - {safe_contact} - {timestamp}.md").resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        rel_path = f"Vault/{str(out_path.relative_to(VAULT_PATH.resolve())).replace(chr(92), '/')}"
        return f"- **Saved Note:** `{rel_path}`\n\n{output}"

    return output


# Signature breakdown for export_agent_conversation:
# - source: str = "latest" ("latest", conversation ID prefix, or `.jsonl`/`.json` path).
# - output_note_path: Optional[str] Vault-relative path to write the Obsidian Markdown transcript.
# - include_thinking: bool = False includes model reasoning accordions.
# - include_tools: bool = True includes coalesced tool execution `<details>` blocks.
# - list_recent: bool = False returns the 15 most recent local Antigravity sessions without exporting.
@tool
def export_agent_conversation(
    source: str = "latest",
    output_note_path: Optional[str] = None,
    include_thinking: bool = False,
    include_tools: bool = True,
    list_recent: bool = False,
) -> str:
    """List or coalesce-export a local Antigravity conversation transcript into clean Obsidian Markdown.

    Args:
        source: `"latest"`, conversation ID/prefix, or transcript path.
        output_note_path: Optional Vault-relative path to write the exported Markdown note.
        include_thinking: Include model thinking accordions (default: False).
        include_tools: Include coalesced tool action summaries (default: True).
        list_recent: Set True to list recent available conversations instead of exporting.
    """
    from nexus.shared_tools import export_conversation

    try:
        if list_recent:
            recents = export_conversation.list_conversations(15)
            if not recents:
                return "No local conversation transcripts found."
            lines = [
                f"- `{r['id']}` — {r['created_at']} ({r['messages']} steps): {r['preview']}"
                for r in recents
            ]
            return "\n".join(lines)

        title_or_id, messages, source_desc = export_conversation.load_conversation_source(source)
        turns = export_conversation.coalesce_conversation_turns(messages)
        rendered = export_conversation.format_turns_to_markdown(
            title_or_id=title_or_id,
            turns=turns,
            source_desc=source_desc,
            include_thinking=include_thinking,
            include_tools=include_tools,
            vault_format=bool(output_note_path),
        )

        if output_note_path:
            clean = output_note_path.strip().replace("\\", "/").lstrip("/")
            if clean.startswith("Vault/"):
                clean = clean[len("Vault/"):]
            if not clean or re.match(r"^[a-zA-Z]:", clean):
                return f"Error: Invalid Vault path '{output_note_path}'."
            resolved_vault = VAULT_PATH.resolve()
            out_file = (resolved_vault / clean).resolve()
            if not out_file.is_relative_to(resolved_vault):
                return f"Error: Refusing to write outside the Vault: '{output_note_path}'"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(rendered, encoding="utf-8")
            rel = f"Vault/{str(out_file.relative_to(resolved_vault)).replace(chr(92), '/')}"
            return f"✅ Exported {len(messages)} steps ({len(turns)} turns) to `{rel}`."

        return rendered
    except Exception as exc:
        return f"Error exporting conversation '{source}': {exc}"


# ── 6. Mobile Push Notification Tool (Telegram Bridge) ───────────────────────

# `message: str` is the Markdown or plain-text notification body to push to the user's phone.
@tool
def send_telegram_notification(message: str) -> str:
    """Send a push notification to the user's phone via the Telegram Mobile Bridge.

    Args:
        message: Concise Markdown or plain-text message body.
    """
    from nexus.shared_tools.telegram_bridge import send_telegram_message

    try:
        sent_ids = send_telegram_message(text=message)
        return f"📱 Sent Telegram notification to phone (message_ids={sent_ids})."
    except Exception as exc:
        return f"Error sending Telegram notification: {exc}"


# ── 8. Media Transcription Tool (Gemini File API) ────────────────────────────

# `file_path: str` relative (to Vault/Project) or absolute path to an audio or video file.
# `output_note_path: Optional[str]` optional relative path in Vault to save Markdown transcript note.
# `include_timestamps: bool` whether to format transcript with [MM:SS] timestamps at speaker turns.
# `save_to_vault: bool` whether to persist the formatted transcript note into the Obsidian Vault.
# `-> str` returns the complete verbatim transcript text (never summarized or abridged).
@tool
def transcribe_media(
    file_path: str,
    output_note_path: Optional[str] = None,
    include_timestamps: bool = True,
    save_to_vault: bool = True,
) -> str:
    """Transcribe an audio or video file verbatim via Gemini File API and optionally save to Vault.

    Args:
        file_path: Path to audio/video file (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.mp4`, `.mov`, etc.).
        output_note_path: Optional Vault-relative path to save transcript (defaults under `0. Inbox/Transcripts/`).
        include_timestamps: Include `[MM:SS]` timestamps (default: True).
        save_to_vault: Save formatted Markdown note into Vault (default: True).
    """
    from nexus.shared_tools.transcribe_media import transcribe_media_file

    try:
        return transcribe_media_file(
            file_path=file_path,
            output_note_path=output_note_path,
            include_timestamps=include_timestamps,
            save_to_vault=save_to_vault,
        )
    except Exception as exc:
        return f"Error transcribing media file '{file_path}': {exc}"


# ── 9. Conversation Spawning & Context Handoff Tool ──────────────────────────

# `title: str` is the concise topic label displayed in the Chat Sidebar (auto-prefixed with `🌿 ` when nested).
# `context_brief: str` is the self-contained Markdown handoff seeded into the fresh conversation's context window.
# `nest_under_current: bool` nests the spawned conversation under the active thread by default (`True`), or creates a root thread (`False`).
# `target_section: Optional[str]` optional Vault folder path whose live directory snapshot is appended to the seeded brief.
# `-> str` returns a compact creation receipt containing the new conversation's title, UUID, and any path verification warnings.
@tool
def spawn_conversation(
    title: str,
    context_brief: str,
    nest_under_current: bool = True,
    target_section: Optional[str] = None,
) -> str:
    """Seed a new isolated conversation thread ("seed & wait") without firing an LLM turn.

    Inherits `cache://` captures automatically and validates referenced `[[Wiki-Links]]` / filenames.

    Args:
        title: Concise conversation title.
        context_brief: Self-contained Markdown handoff brief (IDs, verified paths, `cache://` keys, goals).
        nest_under_current: Nest as child branch under current thread (True) or standalone root (False).
        target_section: Optional Vault folder whose live file tree is appended to the seeded brief.
    """
    from nexus.core.chat_branching import spawn_seeded_conversation
    from nexus.core.conversation_cache import get_active_conversation_id
    from nexus.core.hitl_queue import get_hitl_execution_context

    # Read `conversation_id` from ContextVar-backed execution context (propagated into both Head Agent & subagent threads)
    exec_ctx = get_hitl_execution_context()
    raw_parent_id = exec_ctx.get("conversation_id")
    # Treat the synthetic `"nexus_primary"` CLI/eval default as having no persistent parent row in `chats.db`
    # while still inheriting any captures cached under that active conversation ID.
    parent_id = raw_parent_id if (raw_parent_id and raw_parent_id != "nexus_primary") else None
    cache_source_id = (raw_parent_id or "").strip() or get_active_conversation_id()

    try:
        result = spawn_seeded_conversation(
            title=title,
            context_brief=context_brief,
            parent_conversation_id=parent_id,
            nest_under_parent=nest_under_current,
            target_section=target_section,
            source_cache_conversation_id=cache_source_id,
        )
        new_id = result["conversation_id"]
        created_title = result["title"]
        linked_parent = result.get("parent_conversation_id")
        inherited_count = int(result.get("inherited_captures") or 0)
        scope_note = (
            f"nested branch under `{linked_parent}`"
            if linked_parent
            else "standalone root conversation"
        )
        cache_note = f", inherited captures: {inherited_count}" if inherited_count > 0 else ""
        receipt = (
            f"💬 Spawned {scope_note}: **{created_title}** "
            f"(conversation_id: `{new_id}`, seeded brief: {len(context_brief.strip()):,} chars{cache_note}). "
            f"Ready and waiting in the sidebar."
        )
        if result.get("section_warning"):
            receipt += f"\n{result['section_warning']}"
        if result.get("warning_block"):
            receipt += f"\n{result['warning_block']}"
        return receipt
    except Exception as exc:
        return f"Error spawning conversation '{title}': {exc}"
