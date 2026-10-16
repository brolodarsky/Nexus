"""Loader for the Root Vault Playbook (Engine Constitution).

The root playbook lives at `Vault/Playbook.md` so that:
  - Humans can edit it on the fly in Obsidian like any other playbook in the Vault.
  - Internal engine agents get it injected as their static system-prompt prefix.
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

# Root playbook path at the top of the Vault hierarchy (`Vault/Playbook.md`)
CONSTITUTION_PATH: Path = VAULT_PATH / "Playbook.md"


def get_engine_constitution() -> str:
    """Return the root Vault Playbook with runtime placeholders filled in.

    Placeholders in the markdown:
      {user_name}        -> settings.nexus_user_name   (e.g. "William")
      {current_time}     -> local timestamp            (e.g. "2026-10-13 17:30:00")
      {vault_structure}  -> live directory tree string (deterministic folder hierarchy)
      {shared_tools}     -> bullet list of src/nexus/shared_tools modules (module, [CLI], summary)
    """
    # Read fresh on every call (<1ms): human edits in Obsidian are live on the next LLM turn (Standard 9).
    template = CONSTITUTION_PATH.read_text(encoding="utf-8")

    # Strip Obsidian YAML frontmatter (`--- ... ---`) and top `**Back to:**` navigation bar to save prompt tokens.
    template = re.sub(r"^---\s*\r?\n.*?\r?\n---\s*\r?\n?", "", template, count=1, flags=re.DOTALL)
    template = re.sub(r"^\*\*Back to:\*\*.*\r?\n+", "", template, count=1, flags=re.MULTILINE)

    # Deterministically hydrate the live folder structure (folders only, max_depth=2 with depth-3 children inline)
    # to compress the directory tree from ~100 lines to ~28 lines while preserving all 3rd-level section names.
    vault_structure_tree = get_directory_tree(path=None, show_files=False, max_depth=2)

    # str.replace (not str.format): markdown may legitimately contain other {braces},
    # e.g. "{domain_files}" examples. .format() would raise KeyError on those.
    return (
        template
        .replace("{user_name}", settings.nexus_user_name)
        .replace("{current_time}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        .replace("{vault_structure}", vault_structure_tree)
        .replace("{shared_tools}", get_shared_tools_catalog())
    )


if __name__ == "__main__":
    # UTF-8 reconfigure: the Playbook contains em dashes/emoji that crash Windows' default cp1252 console.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(get_engine_constitution())
