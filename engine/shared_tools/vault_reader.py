"""
vault_reader.py — Pure Python filesystem operations for Vault navigation.
No LangChain @tool decorators here. These functions can be used by any agent or HTTP route.
"""
import os
import re
from pathlib import Path
from typing import Optional, List

from core.constants import IGNORE_DIRS, VAULT_PATH

def read_toc_content() -> str:
    """Reads the Table of Contents.md file to understand the folder structure of the Vault."""
    toc_path = VAULT_PATH / "Table of Contents.md"
    try:
        with open(toc_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading Table of Contents: {str(e)}"


def get_directory_tree(path: Optional[str] = None, show_files: bool = False) -> str:
    """
    Returns an indented directory tree string.
    
    Args:
        path: Optional relative path from Vault root.
        show_files: If True, include files in the output.
    """
    if path:
        start_path = VAULT_PATH / path
        if not start_path.exists() or not start_path.is_dir():
            return (
                f"Error: Path '{path}' does not exist or is not a directory. "
                f"Call with no arguments to see available folders."
            )
    else:
        start_path = VAULT_PATH

    lines = []
    _build_tree(start_path, lines, prefix="", show_files=show_files)

    if not lines:
        return f"No contents found at '{path or 'Vault root'}'."

    header = f"{path}/" if path else "Vault/"
    return header + "\n" + "\n".join(lines)


def _build_tree(directory: Path, lines: list, prefix: str, show_files: bool):
    """Recursively build an indented tree representation of a directory."""
    try:
        entries = sorted(directory.iterdir(), key=lambda e: e.name)
    except PermissionError:
        return

    dirs = [e for e in entries if e.is_dir() and e.name not in IGNORE_DIRS]
    files = [e for e in entries if e.is_file()] if show_files else []

    for d in dirs:
        lines.append(f"{prefix}  {d.name}/")
        _build_tree(d, lines, prefix=prefix + "  ", show_files=show_files)

    for f in files:
        lines.append(f"{prefix}  {f.name}")


def _parse_frontmatter_tags(content: str) -> list:
    """Extract tags from YAML frontmatter using lightweight regex parsing."""
    fm_match = re.match(r'^---\s*\r?\n(.*?)\r?\n---', content, re.DOTALL)
    if not fm_match:
        return []

    frontmatter = fm_match.group(1)

    # Try inline style: tags: [tag1, tag2]
    inline_match = re.search(r'tags:\s*\[([^\]]*)\]', frontmatter)
    if inline_match:
        raw = inline_match.group(1)
        return [t.strip().strip('"').strip("'") for t in raw.split(',') if t.strip()]

    # Try list style: tags:\n  - tag1\n  - tag2
    list_match = re.search(r'tags:\s*\r?\n((?:\s+-\s+.*\r?\n?)+)', frontmatter)
    if list_match:
        raw_lines = list_match.group(1).strip().splitlines()
        tags = []
        for line in raw_lines:
            line = line.strip()
            if line.startswith('- '):
                tags.append(line[2:].strip().strip('"').strip("'"))
        return tags

    return []


def read_note_content(note_path: str) -> str:
    """Reads the contents of a specific note or file in the Vault."""
    if os.path.isabs(note_path):
        target_path = Path(note_path)
    else:
        target_path = VAULT_PATH / note_path
        if not target_path.exists():
            if not target_path.name.endswith('.md'):
                target_path = target_path.with_suffix('.md')
            
    if target_path.exists() and target_path.is_file():
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                try:
                    rel_path = target_path.relative_to(VAULT_PATH)
                except ValueError:
                    rel_path = target_path
                return f"--- File: {rel_path} ---\n\n" + f.read()
        except Exception as e:
            return f"Error reading file {note_path}: {str(e)}"
    
    base_name = os.path.basename(note_path)
    if not base_name.endswith('.md'):
        base_name += '.md'
        
    found_paths = []
    for root, dirs, files in os.walk(VAULT_PATH):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
        for file in files:
            if file == base_name or file == os.path.basename(note_path):
                found_paths.append(Path(root) / file)
                
    if not found_paths:
        return f"File not found: {note_path}. Try using search to find the correct path."
    elif len(found_paths) == 1:
        try:
            with open(found_paths[0], 'r', encoding='utf-8') as f:
                rel_path = found_paths[0].relative_to(VAULT_PATH)
                return f"--- File: {rel_path} ---\n\n" + f.read()
        except Exception as e:
            return f"Error reading file {found_paths[0]}: {str(e)}"
    else:
        rel_paths = [str(p.relative_to(VAULT_PATH)) for p in found_paths]
        return f"Multiple files found for {note_path}. Please be more specific. Matches:\n" + "\n".join(rel_paths)


def search_within(keyword: str, root_path: Optional[str] = None, tags: Optional[List[str]] = None) -> str:
    """Searches notes in the vault for a keyword string."""
    if root_path:
        search_root = VAULT_PATH / root_path
        if not search_root.exists() or not search_root.is_dir():
            return (
                f"Error: Path '{root_path}' does not exist or is not a directory. "
                f"Call get_directory_tree() to see available folders."
            )
    else:
        search_root = VAULT_PATH

    results = []
    keyword_lower = keyword.lower()
    tags_lower = {t.lower() for t in tags} if tags else None
    
    for root, dirs, files in os.walk(search_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            if not file.endswith('.md'):
                continue
                
            filepath = Path(root) / file
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                if tags_lower:
                    note_tags = _parse_frontmatter_tags(content)
                    note_tags_lower = {t.lower() for t in note_tags}
                    if not tags_lower.intersection(note_tags_lower):
                        continue

                if keyword_lower in content.lower():
                    idx = content.lower().find(keyword_lower)
                    start = max(0, idx - 40)
                    end = min(len(content), idx + len(keyword) + 40)
                    snippet = content[start:end].replace('\n', ' ')
                    
                    rel_path = filepath.relative_to(VAULT_PATH)
                    results.append(f"- {rel_path}: \"...{snippet}...\"")
            except Exception:
                pass
                
    if not results:
        scope = f"in '{root_path}'" if root_path else "across the entire vault"
        tag_info = f" (filtered by tags: {', '.join(tags)})" if tags else ""
        return f"No results found for keyword: '{keyword}' {scope}{tag_info}."
        
    scope = f"in '{root_path}'" if root_path else "across the entire vault"
    output = f"Found '{keyword}' in {len(results)} files {scope}:\n"
    for r in results[:20]:
        output += f"{r}\n"
    if len(results) > 20:
        output += f"...and {len(results)-20} more files."
        
    return output
