from pathlib import Path
from core.constants import IGNORE_DIRS

def collect_markdown_files(vault_path: Path) -> list[Path]:
    """
    Recursively finds all .md files in the vault, skipping ignored directories.
    """
    md_files = []
    for path in vault_path.rglob("*.md"):
        if any(ignored in path.parts for ignored in IGNORE_DIRS):
            continue
        md_files.append(path)
    return md_files
