"""
instruction_guard.py — Deterministic Tool-Layer Instruction Hydration & Write-Time Gating.

Guarantees that Nexus agents (both the parent Commander and ephemeral `spawn_subagent` workers)
never edit Vault notes blindly after sliced reads or missing section hydration:
  1. Tracks seen rules per execution scope (`thread_id`, isolating `conv:subagent-N` from `conv`)
     keyed by `(canonical_rel_path_lower, rule_kind, sha256_16)` so any rule edit invalidates stale cache.
  2. Uses a `ContextVar` batch ID (`_instruction_batch_id`) set per `ToolNode` execution step so parallel
     tool calls within the same LLM turn (`[read_file, modify_file]` or sibling `create_file` calls)
     cannot race past the gate before the model has observed the returned instructions.
  3. Provides pure-Python ancestor `Section Instructions.md` resolution (with HITL overlay support),
     write-time hydration gating (`check_write_instruction_gate`), and automatic `Section Instructions.md`
     discovery for `spawn_subagent` (`discover_section_instructions_for_subagent`).
"""

from contextvars import ContextVar, Token
import hashlib
import os
from pathlib import Path
import re
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from nexus.core.constants import IGNORE_DIRS
from nexus.core.hitl_queue import get_hitl_execution_context, get_pending_for_file, get_pending_transactions
from nexus.shared_tools import vault_reader

SECTION_INSTRUCTIONS_FILENAME = "Section Instructions.md"

# ContextVar identifying a single parallel `ToolNode` dispatch step (`uuid.uuid4().hex`).
# Propagates automatically across LangGraph's `ContextThreadPoolExecutor` / `copy_context()`.
_instruction_batch_id: ContextVar[Optional[str]] = ContextVar("instruction_batch_id", default=None)

# Thread-safe in-memory ledger keyed by execution scope (`thread_id`).
# Each scope maps `(canonical_rel_path_lower, rule_kind, sha256_16)` -> `seen_batch_id` (`"__prehydrated__"`,
# `"__direct__"`, or a LangGraph `ToolNode` batch UUID).
_SEEN_RULES_LOCK = threading.Lock()
_SEEN_RULES: Dict[str, Dict[Tuple[str, str, str], str]] = {}

# Tracks which ancestor `Section Instructions.md` paths already emitted their full Markdown body inside a
# `(scope_id, batch_id)` pair so parallel blocked writes deduplicate 14KB payloads within the same turn.
_BATCH_EMITTED_SECTIONS: Dict[Tuple[str, str], Set[str]] = {}

# Matches URLs, `cache://...` handles, and `{{cache:...}}` splice tokens so prompt scanning ignores web links.
_MASK_EXTERNAL_REF_RE = re.compile(
    r"(?:https?|cache)://[^\s)\]>\"'`]+|\{\{\s*cache\s*:[^{}\r\n]+\}\}",
    re.IGNORECASE,
)
# Matches Obsidian wiki-links `[[Note]]`, `[[Note#Heading]]`, `[[Note|Alias]]`.
_WIKILINK_RE = re.compile(r"\[\[([^\[\]\n]+?)\]\]")
# Matches single-line inline code spans `` `...` ``.
_BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")


def set_instruction_batch_id(batch_id: Optional[str]) -> Token:
    """Binds a batch identifier for the active `ToolNode` execution step and returns a `ContextVar` reset `Token`."""
    return _instruction_batch_id.set(batch_id)


def reset_instruction_batch_id(token: Token) -> None:
    """Restores `_instruction_batch_id` to its prior value using the `Token` returned by `set_instruction_batch_id`."""
    _instruction_batch_id.reset(token)


def get_instruction_batch_id() -> Optional[str]:
    """Returns the active `ToolNode` batch ID, or `None` when tools are invoked directly outside LangGraph."""
    return _instruction_batch_id.get()


def get_active_instruction_scope_id() -> str:
    """Resolves the active agent scope ID, keeping subagents (`conv:subagent-N`) isolated from `conv`."""
    ctx = get_hitl_execution_context()
    # Prefer `thread_id` first so ephemeral `:subagent-N` workers never inherit the parent's seen-rule ledger.
    thread_id = (ctx.get("thread_id") or "").strip()
    if thread_id:
        return thread_id
    convo_id = (ctx.get("conversation_id") or "").strip()
    if convo_id:
        return convo_id
    env_convo = (os.environ.get("NEXUS_CONVERSATION_ID") or "").strip()
    if env_convo:
        return env_convo
    return "nexus_primary"


def clear_seen_instructions(scope_or_prefix: Optional[str] = None) -> None:
    """Clears recorded seen-rule state globally (`None`) or for a scope and its `:subagent-*` children."""
    with _SEEN_RULES_LOCK:
        if scope_or_prefix is None:
            _SEEN_RULES.clear()
            _BATCH_EMITTED_SECTIONS.clear()
            return

        prefix = scope_or_prefix.strip()
        if not prefix:
            return
        child_prefix = f"{prefix}:"
        matching_scopes = [k for k in _SEEN_RULES if k == prefix or k.startswith(child_prefix)]
        for k in matching_scopes:
            del _SEEN_RULES[k]

        matching_batches = [
            bk for bk in _BATCH_EMITTED_SECTIONS if bk[0] == prefix or bk[0].startswith(child_prefix)
        ]
        for bk in matching_batches:
            del _BATCH_EMITTED_SECTIONS[bk]


def _normalize_rel_vault_path(path_str: str) -> str:
    """Normalizes a Vault-relative path (`\\` -> `/`, strips leading `Vault/` and slashes)."""
    cleaned = (path_str or "").strip().replace("\\", "/").lstrip("/")
    if cleaned.startswith("Vault/"):
        cleaned = cleaned[len("Vault/") :]
    return cleaned.lstrip("/")


def _digest(text: str) -> str:
    """Computes a normalized 16-char SHA-256 hex digest (CRLF-normalized) for content-hash invalidation."""
    normalized = (text or "").replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _is_rule_seen_in_prior_turn(
    scope_rules: Dict[Tuple[str, str, str], str],
    rule_key: Tuple[str, str, str],
    current_batch_id: Optional[str],
) -> bool:
    """Returns True only when `rule_key` was recorded BEFORE the current parallel `ToolNode` batch."""
    recorded_batch = scope_rules.get(rule_key)
    if recorded_batch is None:
        return False
    # If recorded in the exact same `ToolNode` batch, the LLM has not seen its output yet—keep gating.
    if current_batch_id is not None and recorded_batch == current_batch_id:
        return False
    return True


def _resolve_vault_root(vault_path: Optional[Path] = None) -> Path:
    """Dynamically resolves the active `Vault` root so test monkeypatches on `vault_reader.VAULT_PATH` apply."""
    return (vault_path or vault_reader.VAULT_PATH).resolve()


def _is_active_section_instructions(cand_rel: str, resolved_vault: Path) -> bool:
    """Checks whether `cand_rel` exists on disk or as a non-deleted pending HITL transaction."""
    pending_tx = get_pending_for_file(f"Vault/{cand_rel}")
    if pending_tx is not None:
        if pending_tx.get("action_type") in ("delete", "delete_file"):
            return False
        if pending_tx.get("proposed_content") is not None:
            return True
    return (resolved_vault / cand_rel).is_file()


def find_ancestor_section_instructions(
    rel_vault_path: str,
    vault_path: Optional[Path] = None,
) -> List[str]:
    """Returns all ancestor `Section Instructions.md` paths (outermost to innermost) governing `rel_vault_path`."""
    norm_target = _normalize_rel_vault_path(rel_vault_path)
    if not norm_target:
        return []

    resolved_vault = _resolve_vault_root(vault_path)
    parts = [p for p in norm_target.split("/") if p]
    # Root-level files (`len(parts) <= 1`, e.g. `Gameplan.md`) live directly under `Master Instructions.md`.
    if len(parts) <= 1:
        return []

    ancestors: List[str] = []
    # Walk parent directories outermost -> innermost (`parts[0]` down to `parts[:-1]`).
    for depth in range(1, len(parts)):
        folder_rel = "/".join(parts[:depth])
        cand_rel = f"{folder_rel}/{SECTION_INSTRUCTIONS_FILENAME}"
        # Never treat a `Section Instructions.md` file as its own ancestor requirement.
        if cand_rel.lower() == norm_target.lower():
            continue
        if _is_active_section_instructions(cand_rel, resolved_vault):
            ancestors.append(cand_rel)
    return ancestors


def read_raw_vault_text_with_hitl(
    rel_vault_path: str,
    vault_path: Optional[Path] = None,
) -> Optional[str]:
    """Reads unbannered UTF-8 note text, honoring pending HITL edits/creations and returning None if absent/deleted."""
    norm_rel = _normalize_rel_vault_path(rel_vault_path)
    if not norm_rel:
        return None

    pending_tx = get_pending_for_file(f"Vault/{norm_rel}")
    if pending_tx is not None:
        if pending_tx.get("action_type") in ("delete", "delete_file"):
            return None
        if pending_tx.get("proposed_content") is not None:
            return str(pending_tx["proposed_content"])

    resolved_vault = _resolve_vault_root(vault_path)
    disk_file = (resolved_vault / norm_rel).resolve()
    if not disk_file.is_relative_to(resolved_vault) or not disk_file.is_file():
        return None

    try:
        return disk_file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


# `prehydrated=True` marks instructions injected into `spawn_subagent` before Turn 1 so Turn 1 writes pass immediately.
def record_read_instructions(
    rel_vault_path: str,
    full_content: str,
    *,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    prehydrated: bool = False,
    scope_id: Optional[str] = None,
) -> None:
    """Records which section, frontmatter, and inline heading rules were exposed to the active agent scope."""
    norm_rel = _normalize_rel_vault_path(rel_vault_path)
    if not norm_rel or full_content is None:
        return

    rel_low = norm_rel.lower()
    effective_scope = (scope_id or "").strip() or get_active_instruction_scope_id()
    batch_tag = "__prehydrated__" if prehydrated else (get_instruction_batch_id() or "__direct__")

    lines = full_content.splitlines()
    total_lines = len(lines)
    s_1idx = max(1, start_line) if start_line and start_line > 0 else 1
    e_1idx = min(total_lines, end_line) if (end_line is not None and total_lines > 0) else total_lines
    is_full_read = (
        prehydrated
        or (start_line is None and end_line is None)
        or (s_1idx == 1 and e_1idx >= total_lines)
    )

    keys_to_record: List[Tuple[str, str, str]] = []

    # Only a complete read (or pre-hydration) of `Section Instructions.md` satisfies the section-level gate.
    if Path(norm_rel).name.lower() == SECTION_INSTRUCTIONS_FILENAME.lower() and is_full_read:
        keys_to_record.append((rel_low, "section_instructions", _digest(full_content)))

    # Both full reads and sliced reads (via Pillar 1 banner) expose frontmatter `instructions:`.
    fm_instructions, _ = vault_reader.extract_frontmatter_instructions(full_content)
    if fm_instructions:
        keys_to_record.append((rel_low, "frontmatter_instructions", _digest("\n".join(fm_instructions))))

    # Record inline heading rules exposed either across the whole file or inside/above a partial slice.
    all_headings = vault_reader.extract_all_headings_with_rules(full_content)
    if is_full_read:
        for heading in all_headings:
            rule = heading.get("inline_rule")
            if rule:
                keys_to_record.append((rel_low, f"heading_rule:{heading['text'].lower()}", _digest(rule)))
    else:
        # Pillar 1 injects every enclosing ancestor heading rule above `s_1idx`.
        for heading in vault_reader.extract_heading_context_for_line(full_content, s_1idx, inclusive=False):
            rule = heading.get("inline_rule")
            if rule:
                keys_to_record.append((rel_low, f"heading_rule:{heading['text'].lower()}", _digest(rule)))

        # Record headings inside `[s_1idx..e_1idx]` only when their inline rule also fits cleanly within `e_1idx`.
        for heading in all_headings:
            rule = heading.get("inline_rule")
            if not rule:
                continue
            rule_end = heading.get("rule_end_line") or heading["line"]
            if s_1idx <= heading["line"] < e_1idx and rule_end <= e_1idx:
                keys_to_record.append((rel_low, f"heading_rule:{heading['text'].lower()}", _digest(rule)))

    if not keys_to_record:
        return

    with _SEEN_RULES_LOCK:
        scope_rules = _SEEN_RULES.setdefault(effective_scope, {})
        for rule_key in keys_to_record:
            # Preserve an earlier turn's tag; upgrade only when pre-hydrating a fresh subagent before Turn 1.
            if rule_key not in scope_rules or batch_tag == "__prehydrated__":
                scope_rules[rule_key] = batch_tag


def _find_target_start_line(source_text: str, target_text: str) -> Optional[int]:
    """Locates the 1-indexed start line of `target_text` inside `source_text` (CRLF-tolerant)."""
    if not source_text or not target_text:
        return None
    idx = source_text.find(target_text)
    if idx != -1:
        return source_text[:idx].count("\n") + 1

    norm_source = source_text.replace("\r\n", "\n")
    norm_target = target_text.replace("\r\n", "\n")
    idx = norm_source.find(norm_target)
    if idx != -1:
        return norm_source[:idx].count("\n") + 1
    return None


# `working_base: Optional[str]` is the unbannered baseline note text (`None` for brand-new `create_file`).
# `target_text: Optional[str]` is the contiguous `target` snippet passed to `modify_file` (`None` for `create_file`).
# -> Optional[str] returns None when all governing rules were already seen in prior turns, or a blocking report otherwise.
def check_write_instruction_gate(
    rel_vault_path: str,
    *,
    working_base: Optional[str] = None,
    target_text: Optional[str] = None,
    is_create: bool = False,
    vault_path: Optional[Path] = None,
    scope_id: Optional[str] = None,
) -> Optional[str]:
    """Enforces that ancestor `Section Instructions.md`, frontmatter `instructions:`, and inline heading rules were seen."""
    _ = is_create
    norm_rel = _normalize_rel_vault_path(rel_vault_path)
    if not norm_rel:
        return None

    rel_low = norm_rel.lower()
    resolved_vault = _resolve_vault_root(vault_path)
    effective_scope = (scope_id or "").strip() or get_active_instruction_scope_id()
    current_batch_id = get_instruction_batch_id()

    # Phase 1: Collect candidate rules from disk/HITL before acquiring `_SEEN_RULES_LOCK`.
    candidate_sections: List[Tuple[str, Tuple[str, str, str], str]] = []
    for sec_rel in find_ancestor_section_instructions(norm_rel, vault_path=resolved_vault):
        sec_text = read_raw_vault_text_with_hitl(sec_rel, vault_path=resolved_vault)
        if sec_text is None:
            continue
        sec_key = (sec_rel.lower(), "section_instructions", _digest(sec_text))
        candidate_sections.append((sec_rel, sec_key, sec_text))

    fm_candidate: Optional[Tuple[Tuple[str, str, str], List[str]]] = None
    heading_candidates: List[Tuple[Tuple[str, str, str], Dict[str, Any]]] = []
    if working_base is not None:
        fm_rules, _ = vault_reader.extract_frontmatter_instructions(working_base)
        if fm_rules:
            fm_key = (rel_low, "frontmatter_instructions", _digest("\n".join(fm_rules)))
            fm_candidate = (fm_key, fm_rules)

        if target_text:
            target_line = _find_target_start_line(working_base, target_text)
            if target_line is not None:
                enclosing = vault_reader.extract_heading_context_for_line(
                    working_base, target_line, inclusive=True
                )
                for heading in enclosing:
                    rule = heading.get("inline_rule")
                    if rule:
                        h_key = (rel_low, f"heading_rule:{heading['text'].lower()}", _digest(rule))
                        heading_candidates.append((h_key, heading))

    if not candidate_sections and fm_candidate is None and not heading_candidates:
        return None

    # Phase 2: Check & update `_SEEN_RULES` atomically under `_SEEN_RULES_LOCK` so parallel batch calls coordinate.
    missing_sections: List[Tuple[str, str, bool]] = []
    missing_frontmatter: List[str] = []
    missing_headings: List[Dict[str, Any]] = []

    with _SEEN_RULES_LOCK:
        scope_rules = _SEEN_RULES.setdefault(effective_scope, {})
        record_tag = current_batch_id or "__direct__"
        emitted_in_batch: Optional[Set[str]] = None
        if current_batch_id is not None:
            emitted_in_batch = _BATCH_EMITTED_SECTIONS.setdefault((effective_scope, current_batch_id), set())

        keys_to_mark: List[Tuple[str, str, str]] = []

        for sec_rel, sec_key, sec_text in candidate_sections:
            if not _is_rule_seen_in_prior_turn(scope_rules, sec_key, current_batch_id):
                already_emitted = emitted_in_batch is not None and sec_rel.lower() in emitted_in_batch
                missing_sections.append((sec_rel, sec_text, already_emitted))
                if emitted_in_batch is not None and not already_emitted:
                    emitted_in_batch.add(sec_rel.lower())
                keys_to_mark.append(sec_key)

        if fm_candidate is not None:
            fm_key, fm_rules = fm_candidate
            if not _is_rule_seen_in_prior_turn(scope_rules, fm_key, current_batch_id):
                missing_frontmatter = fm_rules
                keys_to_mark.append(fm_key)

        seen_heading_keys: Set[Tuple[str, str, str]] = set()
        for h_key, heading in heading_candidates:
            if h_key in seen_heading_keys:
                continue
            seen_heading_keys.add(h_key)
            if not _is_rule_seen_in_prior_turn(scope_rules, h_key, current_batch_id):
                missing_headings.append(heading)
                keys_to_mark.append(h_key)

        if not missing_sections and not missing_frontmatter and not missing_headings:
            return None

        # Mark newly returned rules with the active turn/batch tag so the next turn's retry proceeds cleanly.
        for key in keys_to_mark:
            if key not in scope_rules:
                scope_rules[key] = record_tag

    # Phase 3: Format the actionable blocked-write response containing all unhydrated instructions.
    blocks: List[str] = [
        f"⚠️ Write Blocked — Instruction Hydration Required (`Vault/{norm_rel}`)",
        (
            f"Before staging writes to `Vault/{norm_rel}`, review the governing rules below "
            f"(note: `Vault/Master Instructions.md` also governs all writes). "
            f"No HITL transaction was staged. Verify compliance and re-submit your write call."
        ),
    ]

    for sec_rel, sec_text, already_emitted in missing_sections:
        if already_emitted:
            blocks.append(
                f"### Section Instructions: `{sec_rel}`\n"
                f"*(Full text already returned in an earlier blocked tool result in this batch — review it above.)*"
            )
        else:
            blocks.append(f"### Section Instructions: `{sec_rel}`\n{sec_text.strip()}")

    if missing_frontmatter:
        fm_lines = "\n".join(f"- {rule}" for rule in missing_frontmatter)
        blocks.append(f"### Document Frontmatter `instructions:` (`Vault/{norm_rel}`)\n{fm_lines}")

    if missing_headings:
        h_lines: List[str] = []
        for heading in missing_headings:
            formatted_rule = str(heading["inline_rule"]).replace("\n", "\n  ")
            h_lines.append(f"- `{heading['raw_heading']}` (L{heading['line']}) — {formatted_rule}")
        blocks.append(
            f"### Inline Section Rules Enclosing Target (`Vault/{norm_rel}`)\n" + "\n".join(h_lines)
        )

    return "\n\n".join(blocks)


def _scan_vault_tree_fast(resolved_vault: Path) -> Tuple[List[Tuple[str, str]], Set[str], List[str], Dict[str, List[str]]]:
    """Single fast `os.walk` (<5ms) returning section dirs, all rel dirs, all rel files, and basename lookup map."""
    section_map: Dict[str, Tuple[str, str]] = {}
    rel_dirs: Set[str] = set()
    rel_files: List[str] = []
    basename_to_rels: Dict[str, List[str]] = {}

    if resolved_vault.exists():
        for root, dirs, files in os.walk(resolved_vault):
            dirs[:] = [
                d for d in dirs
                if d not in IGNORE_DIRS and (Path(root) / d).resolve().is_relative_to(resolved_vault)
            ]
            root_path = Path(root).resolve()
            if root_path != resolved_vault:
                rel_dir = str(root_path.relative_to(resolved_vault)).replace("\\", "/")
                rel_dirs.add(rel_dir)
            else:
                rel_dir = ""

            for fname in files:
                if fname.startswith("."):
                    continue
                fpath = (root_path / fname).resolve()
                if not fpath.is_relative_to(resolved_vault):
                    continue
                rel_file = f"{rel_dir}/{fname}" if rel_dir else fname
                rel_files.append(rel_file)
                basename_to_rels.setdefault(fname.lower(), []).append(rel_file)
                if fname.lower() == SECTION_INSTRUCTIONS_FILENAME.lower() and rel_dir:
                    section_map[rel_file.lower()] = (rel_dir, rel_file)

    # Also account for pending HITL creations/deletions of `Section Instructions.md` without failing if DB uninitialized.
    try:
        pending_list = get_pending_transactions()
    except Exception:
        pending_list = []

    for tx in pending_list:
        target = _normalize_rel_vault_path(tx.get("target_file") or "")
        if not target or "/" not in target:
            continue
        if Path(target).name.lower() != SECTION_INSTRUCTIONS_FILENAME.lower():
            continue
        action = tx.get("action_type") or ""
        if action in ("delete", "delete_file"):
            section_map.pop(target.lower(), None)
        elif tx.get("proposed_content") is not None:
            parent_dir = target.rsplit("/", 1)[0]
            rel_dirs.add(parent_dir)
            section_map[target.lower()] = (parent_dir, target)

    return list(section_map.values()), rel_dirs, rel_files, basename_to_rels


def _match_section_dir_in_prompt(sec_dir_rel: str, norm_prompt: str) -> bool:
    """Checks whether `norm_prompt` explicitly mentions `sec_dir_rel` or its numbered leaf section name."""
    # Match full relative folder path (`3. Operations/3.1. Career Strategy & Revenue` or `Finance/Budget`).
    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(sec_dir_rel)}(?![A-Za-z0-9_])", norm_prompt, re.IGNORECASE):
        # Single-word unnumbered folders (e.g. `Notes`) require either exact case, a trailing `/`, or backticks
        # so casual English words inside prompts ("check my notes") do not pull unrelated instructions.
        if "/" in sec_dir_rel or re.match(r"^\d+(?:\.\d+)*\.\s+", sec_dir_rel):
            return True
        if (
            re.search(rf"(?<![A-Za-z0-9_]){re.escape(sec_dir_rel)}/", norm_prompt, re.IGNORECASE)
            or re.search(rf"`[^`\n]*{re.escape(sec_dir_rel)}[^`\n]*`", norm_prompt, re.IGNORECASE)
            or re.search(rf"(?<![A-Za-z0-9_]){re.escape(sec_dir_rel)}(?![A-Za-z0-9_])", norm_prompt)
        ):
            return True

    # Also match numbered leaf section names (`3.1. Career Strategy & Revenue`, `6. Engineering`, `2. Health`).
    leaf_name = sec_dir_rel.rsplit("/", 1)[-1]
    if re.match(r"^\d+(?:\.\d+)*\.\s+.+", leaf_name):
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(leaf_name)}(?![A-Za-z0-9_])", norm_prompt, re.IGNORECASE):
            return True

    return False


# `resolved_context_rel_paths` holds explicit Vault-relative paths already passed in `context_files`.
# -> List[str] returns deduplicated, sorted ancestor `Section Instructions.md` paths absent from `resolved_context_rel_paths`.
def discover_section_instructions_for_subagent(
    task_prompt: str,
    resolved_context_rel_paths: Optional[List[str]] = None,
    vault_path: Optional[Path] = None,
) -> List[str]:
    """Deterministically discovers governing `Section Instructions.md` files for a `spawn_subagent` task."""
    resolved_vault = _resolve_vault_root(vault_path)
    explicit_rel_list = [_normalize_rel_vault_path(p) for p in (resolved_context_rel_paths or []) if p]
    explicit_lower = {p.lower() for p in explicit_rel_list if p}

    discovered: Dict[str, str] = {}

    def _add_ancestors_for_rel(rel_candidate: str) -> None:
        for sec_rel in find_ancestor_section_instructions(rel_candidate, vault_path=resolved_vault):
            sec_low = sec_rel.lower()
            if sec_low not in explicit_lower:
                discovered[sec_low] = sec_rel

    # Source 1: Ancestor `Section Instructions.md` files for every explicit Vault path in `context_files`.
    for rel_p in explicit_rel_list:
        _add_ancestors_for_rel(rel_p)

    # Source 2: Best-effort deterministic scan of `task_prompt` for section folders, directories, wiki-links, and files.
    norm_prompt = (task_prompt or "").replace("\\", "/")
    if norm_prompt.strip():
        section_dirs, rel_dirs, rel_files, basename_to_rels = _scan_vault_tree_fast(resolved_vault)
        if section_dirs:
            masked_prompt = _MASK_EXTERNAL_REF_RE.sub(" ", norm_prompt)
            masked_low = masked_prompt.lower()
            rel_dirs_list = sorted(rel_dirs)

            # 2a. Direct section folder mentions (e.g. `3.1. Career Strategy & Revenue` or `Finance/New.md`).
            for sec_dir_rel, sec_file_rel in section_dirs:
                if _match_section_dir_in_prompt(sec_dir_rel, masked_prompt):
                    sec_low = sec_file_rel.lower()
                    if sec_low not in explicit_lower:
                        discovered[sec_low] = sec_file_rel
                    _add_ancestors_for_rel(sec_file_rel)

            # Helper to map an explicit folder reference (like `Saved Job Listings/`) to its governing sections.
            def _match_dir_ref(dir_ref: str) -> None:
                clean_d = _normalize_rel_vault_path(dir_ref).rstrip("/")
                if not clean_d:
                    return
                clean_d_low = clean_d.lower()
                exact_matches = [d for d in rel_dirs_list if d.lower() == clean_d_low]
                if exact_matches:
                    for matched in exact_matches:
                        _add_ancestors_for_rel(f"{matched}/__probe__.md")
                    return
                # Unique leaf/suffix directory match (e.g. `Saved Job Listings/` -> `3.1.../Saved Job Listings`).
                suffix_matches = [d for d in rel_dirs_list if d.lower().endswith(f"/{clean_d_low}")]
                if len(suffix_matches) == 1:
                    _add_ancestors_for_rel(f"{suffix_matches[0]}/__probe__.md")

            # 2b-i. Obsidian `[[Wiki-Links]]` resolved silently against `resolved_vault`.
            for wl_match in _WIKILINK_RE.finditer(masked_prompt):
                target = wl_match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
                if not target or any(ch in "*?<>{}" for ch in target):
                    continue
                resolved_path, _ = vault_reader.resolve_vault_note_path(target)
                if resolved_path is not None and resolved_path.is_relative_to(resolved_vault):
                    rel_note = str(resolved_path.relative_to(resolved_vault)).replace("\\", "/")
                    _add_ancestors_for_rel(rel_note)

            # 2b-ii. Backticked paths, folder refs ending in `/`, or note paths not yet on disk (`Folder/New.md`).
            for bt_match in _BACKTICK_SPAN_RE.finditer(masked_prompt):
                span = bt_match.group(1).strip()
                if not span or any(ch in "*?<>{}" for ch in span):
                    continue
                clean_span = _normalize_rel_vault_path(span)
                if span.endswith("/"):
                    _match_dir_ref(clean_span)
                    continue
                if "/" in clean_span or clean_span.lower().endswith((".md", ".pdf", ".docx")):
                    # Even if a newly created target note isn't on disk yet, checking its folder path resolves sections.
                    if "/" in clean_span:
                        _add_ancestors_for_rel(clean_span)
                    resolved_path, _ = vault_reader.resolve_vault_note_path(clean_span)
                    if resolved_path is not None and resolved_path.is_relative_to(resolved_vault):
                        rel_note = str(resolved_path.relative_to(resolved_vault)).replace("\\", "/")
                        _add_ancestors_for_rel(rel_note)

            # 2b-iii. Unquoted relative paths & unique basenames present in `masked_prompt`.
            if rel_files:
                for rel_file in rel_files:
                    if rel_file.lower() in masked_low:
                        _add_ancestors_for_rel(rel_file)
                for base_low, matching_rels in basename_to_rels.items():
                    # Skip ambiguous basenames (e.g. `Log.md`, `Tasks.md`) unless referenced by relative path above.
                    if len(matching_rels) == 1 and base_low in masked_low:
                        rel_only = matching_rels[0]
                        base_name = rel_only.rsplit("/", 1)[-1]
                        if re.search(
                            rf"(?<![A-Za-z0-9_/]){re.escape(base_name)}(?![A-Za-z0-9_])",
                            masked_prompt,
                            re.IGNORECASE,
                        ):
                            _add_ancestors_for_rel(rel_only)

    return sorted(discovered.values())
