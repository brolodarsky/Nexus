"""Loader for the Nexus Engine Constitution.

The constitution text lives in `ENGINE_CONSTITUTION.md` (same folder) so that:
  - Internal engine agents get it injected as their static system-prompt prefix.
  - IDE agents (Antigravity, Cursor) read the SAME file at boot (see AGENTS.md),
    which makes them behave exactly like internal "Resident" agents.
One file => zero drift between the two agent populations.

NOTE (2026-10-07): As of this commit, no graph imports `get_engine_constitution()` yet.
Wiring it into each agent's `call_model()` node is a tracked roadmap item.
"""

from datetime import datetime
from pathlib import Path  # Path(__file__) -> absolute path of THIS .py file, OS-independent

from src.nexus.core.config import settings

# Path(__file__).parent -> src/nexus/core/ ; `/` operator joins path segments (pathlib idiom)
CONSTITUTION_PATH: Path = Path(__file__).parent / "ENGINE_CONSTITUTION.md"


def get_engine_constitution() -> str:
    """Return the constitution with runtime placeholders filled in.

    Placeholders in the markdown:
      {user_name}    -> settings.nexus_user_name   (e.g. "William")
      {current_time} -> local timestamp            (e.g. "2026-10-07 18:30:00")
    """
    # Read fresh on every call (<1ms): human edits are live on the next LLM turn (Standard 9).
    template = CONSTITUTION_PATH.read_text(encoding="utf-8")

    # str.replace (not str.format): markdown may legitimately contain other {braces},
    # e.g. "{domain_files}" examples. .format() would raise KeyError on those.
    return (
        template
        .replace("{user_name}", settings.nexus_user_name)
        .replace("{current_time}", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
