"""Loader for the Root Master Instructions (`Vault/Master Instructions.md`).

The root instruction document lives at `Vault/Master Instructions.md` so that:
  - Humans can edit it on the fly in Obsidian like any other instruction file in the Vault.
  - Internal engine agents (`NexusAgent` and spawned subagents) get it injected via `inject_root_instructions()`.
  - IDE agents (Antigravity, Cursor) inject the SAME hydrated output at boot by running
    `python -m nexus.core.engine_constitution` (see AGENTS.md), so they behave like internal "Resident" agents.
One file => zero drift between the two agent populations.
"""

from datetime import datetime
from pathlib import Path
import re
import sys

from nexus.core.config import settings
from nexus.core.constants import VAULT_PATH
# Static (ast-based) shared tools catalog: no tool modules are imported during hydration
from nexus.core.tool_catalog import get_shared_tools_catalog
# Import deterministic vault directory tree builder for zero-overhead prompt structure hydration (<1ms disk read)
from nexus.shared_tools.vault_reader import get_directory_tree

# Root Master Instructions path at the top of the Vault hierarchy (`Vault/Master Instructions.md`)
ROOT_INSTRUCTIONS_PATH: Path = VAULT_PATH / "Master Instructions.md"
# Backward-compatible constant alias for external callers referencing CONSTITUTION_PATH
CONSTITUTION_PATH: Path = ROOT_INSTRUCTIONS_PATH


# `cache_stable: bool = True` rounds `{current_time}` to the current hour (`YYYY-MM-DD HH:00`) so the ~5,000-token
# SystemMessage prefix stays 100% byte-identical across multi-step tool loops and consecutive turns, enabling
# automatic provider KV prompt caching (50-80% input token discount + faster Time-To-First-Token).
# `-> str` type annotation indicates this function returns a hydrated UTF-8 Markdown string ready for SystemMessage injection.
def inject_root_instructions(cache_stable: bool = True) -> str:
    """Return the root Master Instructions (`Vault/Master Instructions.md`) with runtime placeholders filled in.

    Placeholders in the markdown:
      {user_name}        -> settings.nexus_user_name   (e.g. "William")
      {current_time}     -> hour-aligned timestamp     (e.g. "2026-10-21 14:00") for prompt-cache stability
      {vault_structure}  -> live directory tree string (deterministic folder hierarchy)
      {shared_tools}     -> bullet list of src/nexus/shared_tools modules (module, [CLI], summary)
    """
    # Read fresh on every call (<1ms): human edits in Obsidian are live on the next LLM turn (Standard 9).
    template = ROOT_INSTRUCTIONS_PATH.read_text(encoding="utf-8")

    # Strip Obsidian YAML frontmatter (`--- ... ---`) and top `**Back to:**` navigation bar to save prompt tokens.
    template = re.sub(r"^---\s*\r?\n.*?\r?\n---\s*\r?\n?", "", template, count=1, flags=re.DOTALL)
    template = re.sub(r"^\*\*Back to:\*\*.*\r?\n+", "", template, count=1, flags=re.MULTILINE)

    # Deterministically hydrate the live folder structure (folders only, max_depth=2 with depth-3 children inline)
    # to compress the directory tree from ~100 lines to ~28 lines while preserving all 3rd-level section names.
    vault_structure_tree = get_directory_tree(path=None, show_files=False, max_depth=2)

    # Format timestamp to the hour boundary when `cache_stable=True` so second-by-second ticks never bust the
    # provider's left-to-right KV prompt cache across multi-step tool iterations or follow-up turns.
    timestamp_str = (
        datetime.now().strftime("%Y-%m-%d %H:00")
        if cache_stable
        else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    # str.replace (not str.format): markdown may legitimately contain other {braces},
    # e.g. "{domain_files}" examples. .format() would raise KeyError on those.
    return (
        template
        .replace("{user_name}", settings.nexus_user_name)
        .replace("{current_time}", timestamp_str)
        .replace("{vault_structure}", vault_structure_tree)
        .replace("{shared_tools}", get_shared_tools_catalog())
    )


# Backward-compatible alias so legacy callers or scripts referencing get_engine_constitution() continue working seamlessly.
get_engine_constitution = inject_root_instructions


if __name__ == "__main__":
    # UTF-8 reconfigure: the instructions file contains em dashes/emoji that crash Windows' default cp1252 console.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(inject_root_instructions())
