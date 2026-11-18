"""tool_catalog.py — Deterministic catalog of runnable Nexus `[CLI]` shared tools for prompt hydration.

Builds a compact markdown list of runnable `[CLI]` Python modules in `src/nexus/shared_tools/`
(module path, `[CLI]` marker, first docstring line) by STATIC parsing with `ast`.
Nothing is imported, so heavy deps (googleapiclient, langchain) never load and the
scan stays fast and side-effect free. Non-CLI internal library modules (`shared.py`,
`summarizer.py`, `resume_engine/service.py`) are excluded so `{shared_tools}` in
`Vault/Master Instructions.md` advertises only directly invocable CLI modules.
"""

import ast
from pathlib import Path

from nexus.core.constants import PROJECT_ROOT

SHARED_TOOLS_DIR: Path = PROJECT_ROOT / "src" / "nexus" / "shared_tools"
_SKIP_DIRS: set[str] = {"__pycache__", "node_modules"}  # Vendored/compiled dirs never hold Nexus tools


def _summary_line(docstring: str | None, filename: str) -> str:
    """Return the first docstring line minus the redundant 'name.py — ' prefix many modules use."""
    if not docstring:
        return "(no module docstring)"
    first = docstring.strip().splitlines()[0].strip()
    # e.g. "calendar_engine.py — Core Google Calendar API..." -> "Core Google Calendar API..."
    for sep in (" — ", " - ", ": "):
        prefix = f"{filename}{sep}"
        if first.startswith(prefix):
            return first[len(prefix):]
    return first


# `-> str` returns a newline-delimited Markdown bullet list of `[CLI]` modules ready for `Master Instructions.md`.
def get_shared_tools_catalog() -> str:
    """
    Render runnable `[CLI]` shared tools in `src/nexus/shared_tools/` as a markdown bullet list.

    Output line shape:
      - `nexus.shared_tools.gmail_engine` [CLI] — Core Gmail REST API (v1) integration for Nexus Engine.
    Only modules exposing an `if __name__ == "__main__":` entrypoint are included so agents do not
    attempt `run_shared_tool_cli` on internal library modules already bound or imported directly.
    """
    lines: list[str] = []
    # sorted(rglob) => stable, alphabetical order every run (deterministic prompt = cache-friendly prompt)
    for path in sorted(SHARED_TOOLS_DIR.rglob("*.py")):
        rel = path.relative_to(SHARED_TOOLS_DIR)
        if path.name == "__init__.py" or any(part in _SKIP_DIRS for part in rel.parts):
            continue

        source = path.read_text(encoding="utf-8", errors="replace")
        # Filter strictly to runnable CLI modules (`__main__` guard); library-only modules like `shared.py`
        # are either bound directly via `bind_tools(...)` or imported internally by the engine.
        has_cli_entrypoint = '__name__ == "__main__"' in source or "__name__ == '__main__'" in source
        if not has_cli_entrypoint:
            continue

        try:
            docstring = ast.get_docstring(ast.parse(source))  # Parse-only: reads the module docstring without executing code
        except SyntaxError:
            docstring = None

        # Path("resume_engine/render_docx.py") -> "nexus.shared_tools.resume_engine.render_docx"
        module = "nexus.shared_tools." + ".".join(rel.with_suffix("").parts)
        lines.append(f"- `{module}` [CLI] — {_summary_line(docstring, path.name)}")

    return "\n".join(lines) if lines else "(no shared tools found)"


if __name__ == "__main__":
    import sys
    # Windows consoles default to cp1252, which mangles the em dashes above; force UTF-8
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(get_shared_tools_catalog())
