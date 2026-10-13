"""Loader for the Root Vault Playbook (Engine Constitution).

The root playbook lives at `Vault/Playbook.md` so that:
  - Humans can edit it on the fly in Obsidian like any other playbook in the Vault.
  - Internal engine agents get it injected as their static system-prompt prefix.
  - IDE agents (Antigravity, Cursor) read the SAME file at boot (see AGENTS.md),
    which makes them behave like internal "Resident" agents.
One file => zero drift between the two agent populations.
"""

from datetime import datetime
from pathlib import Path

from nexus.core.config import settings
from nexus.core.constants import VAULT_PATH

# Root playbook path at the top of the Vault hierarchy (`Vault/Playbook.md`)
CONSTITUTION_PATH: Path = VAULT_PATH / "Playbook.md"


def get_engine_constitution() -> str:
    """Return the root Vault Playbook with runtime placeholders filled in.

    Placeholders in the markdown:
      {user_name}    -> settings.nexus_user_name   (e.g. "William")
      {current_time} -> local timestamp            (e.g. "2026-10-13 17:30:00")
    """
    # Read fresh on every call (<1ms): human edits in Obsidian are live on the next LLM turn (Standard 9).
    template = CONSTITUTION_PATH.read_text(encoding="utf-8")

    # str.replace (not str.format): markdown may legitimately contain other {braces},
    # e.g. "{domain_files}" examples. .format() would raise KeyError on those.
    return (
        template
        .replace("{user_name}", settings.nexus_user_name)
        .replace("{current_time}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
