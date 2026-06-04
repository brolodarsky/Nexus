"""
vault.py — Vault exploration routes.
Exposes the Vault's structure and note contents over HTTP for the Control Panel.
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import sys
import subprocess
from pathlib import Path
from core.constants import VAULT_PATH, IGNORE_DIRS, PROJECT_ROOT

router = APIRouter()


# ── Response Models ───────────────────────────────────────────

class VaultStructureResponse(BaseModel):
    tree: str
    path: str | None


class NoteContentResponse(BaseModel):
    path: str
    content: str


class SearchResult(BaseModel):
    results: str
    keyword: str
    path: str | None


# ── Routes ────────────────────────────────────────────────────

@router.get("/structure", response_model=VaultStructureResponse)
async def get_vault_structure(path: str | None = Query(default=None)):
    """
    Returns an indented tree of the vault directory structure.
    Without a path, returns top-level folders only.
    With a path, returns folders AND files in that subtree.
    """
    try:
        from shared_tools.vault_reader import get_directory_tree
        tree = get_directory_tree(path=path, show_files=path is not None)
        return VaultStructureResponse(tree=tree, path=path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read vault structure: {str(e)}",
        )


@router.get("/note", response_model=NoteContentResponse)
async def get_note(path: str = Query(..., description="Relative path from Vault root")):
    """
    Reads a specific note's contents from the Vault.
    """
    if not path.strip():
        raise HTTPException(status_code=400, detail="Path cannot be empty.")

    try:
        from shared_tools.vault_reader import read_note_content
        content = read_note_content(path)

        if content.startswith("File not found:"):
            raise HTTPException(status_code=404, detail=content)

        return NoteContentResponse(path=path, content=content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read note: {str(e)}",
        )


@router.get("/search", response_model=SearchResult)
async def search_vault(
    keyword: str = Query(..., description="Search term"),
    path: str | None = Query(default=None, description="Optional folder scope"),
):
    """
    Searches notes in the vault for a keyword. Optionally scoped to a folder.
    """
    if not keyword.strip():
        raise HTTPException(status_code=400, detail="Keyword cannot be empty.")

    try:
        from shared_tools.vault_reader import search_within
        results = search_within(keyword, root_path=path)
        return SearchResult(results=results, keyword=keyword, path=path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}",
        )


class VaultEntry(BaseModel):
    name: str
    path: str
    type: str
    size: int | None = None
    mtime: float | None = None
    has_audio: bool = False

@router.get("/list", response_model=list[VaultEntry])
async def list_vault(path: str | None = Query(default=None)):
    """
    Lists the entries of a specific vault directory as a JSON list.
    """
    target_dir = VAULT_PATH
    if path:
        # Prevent directory traversal attacks
        safe_path = (VAULT_PATH / path).resolve()
        if not safe_path.is_relative_to(VAULT_PATH):
            raise HTTPException(status_code=400, detail="Invalid directory path")
        target_dir = safe_path

    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    entries = []
    try:
        for item in sorted(target_dir.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
            if item.is_dir() and item.name in IGNORE_DIRS:
                continue
            
            if item.name.startswith("."):
                continue

            rel_path = str(item.relative_to(VAULT_PATH)).replace("\\", "/")
            entry_type = "directory" if item.is_dir() else "file"
            
            if entry_type == "file" and not item.name.endswith(".md"):
                continue
                
            has_audio = False
            if entry_type == "file":
                audio_file = item.with_suffix(".mp3")
                has_audio = audio_file.exists()

            entries.append(VaultEntry(
                name=item.name,
                path=rel_path,
                type=entry_type,
                size=item.stat().st_size if item.is_file() else None,
                mtime=item.stat().st_mtime if item.is_file() else None,
                has_audio=has_audio
            ))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list directory: {str(e)}")

    return entries


class GeneratePodcastRequest(BaseModel):
    path: str
    force: bool = False

@router.post("/podcast/generate")
async def generate_podcast(req: GeneratePodcastRequest):
    """
    Generates a podcast MP3 for a note.
    """
    note_path = req.path
    if not note_path.strip():
        raise HTTPException(status_code=400, detail="Path cannot be empty.")

    note_file = (VAULT_PATH / note_path).resolve()
    if not note_file.is_relative_to(VAULT_PATH):
        raise HTTPException(status_code=400, detail="Invalid file path.")

    if not note_file.exists() or not note_file.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    script_path = (PROJECT_ROOT / "tools" / "generate_podcast.py").resolve()
    
    cmd = [sys.executable, str(script_path), str(note_file)]
    if req.force:
        cmd.append("--force")

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        if "Error" in result.stdout or "Error" in result.stderr:
            raise HTTPException(status_code=500, detail=f"Podcast generation failed: {result.stdout or result.stderr}")
            
        audio_file = note_file.with_suffix(".mp3")
        if not audio_file.exists():
            raise HTTPException(status_code=500, detail="Audio file was not generated.")

        return {
            "status": "success",
            "message": "Podcast generated successfully",
            "note_path": note_path,
            "has_audio": True
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Subprocess failed (exit {e.returncode}): {e.stderr or e.stdout}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run podcast generator: {str(e)}"
        )


@router.get("/podcast/download")
async def download_podcast(path: str = Query(..., description="Relative path from Vault root to the note")):
    """
    Streams or downloads the generated podcast MP3.
    """
    note_file = (VAULT_PATH / path).resolve()
    if not note_file.is_relative_to(VAULT_PATH):
        raise HTTPException(status_code=400, detail="Invalid note path.")

    audio_file = note_file.with_suffix(".mp3")
    if not audio_file.exists():
        raise HTTPException(status_code=404, detail="Audio file not found for this note. Please generate it first.")

    return FileResponse(
        path=str(audio_file),
        media_type="audio/mpeg",
        filename=audio_file.name
    )
