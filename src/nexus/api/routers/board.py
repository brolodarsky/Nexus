"""
board.py — FastAPI Router for the Shared Inter-Agent Blackboard (`/api/board`).

Exposes REST endpoints so the Next.js Control Panel (`/chat` Live Bulletin Feed) and external clients
can inspect, post, or clear situational bulletins published by Flash subagents and Astra.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nexus.core.blackboard import clear_bulletins, delete_bulletin, get_bulletins, post_bulletin

router = APIRouter()


# Pydantic request model for posting a bulletin via REST API
class BulletinCreateRequest(BaseModel):
    author: str = "User"
    title: str
    content: str
    pinned: bool = False
    thread_id: Optional[str] = None
    # Optional legacy channel field tolerated for backward compatibility
    channel: Optional[str] = None


@router.get("")
async def list_board_bulletins(
    limit: int = 25,
    thread_id: Optional[str] = None,
    channel: Optional[str] = None,  # Tolerated for backward compatibility
) -> Dict[str, Any]:
    """Return recent bulletins from the Shared Agent Blackboard (`blackboard.db`), optionally scoped to `thread_id`."""
    items: List[Dict[str, Any]] = get_bulletins(limit=limit, thread_id=thread_id)
    return {"bulletins": items, "count": len(items)}


@router.post("")
async def create_board_bulletin(req: BulletinCreateRequest) -> Dict[str, Any]:
    """Post a new bulletin to the Shared Agent Blackboard."""
    bulletin_id = post_bulletin(
        author=req.author,
        title=req.title,
        content=req.content,
        pinned=req.pinned,
        thread_id=req.thread_id,
    )
    return {"status": "ok", "id": bulletin_id}


@router.delete("/{bulletin_id}")
async def remove_board_bulletin(bulletin_id: int) -> Dict[str, Any]:
    """Delete a single bulletin by ID."""
    if not delete_bulletin(bulletin_id):
        raise HTTPException(status_code=404, detail=f"Bulletin #{bulletin_id} not found.")
    return {"status": "ok", "deleted_id": bulletin_id}


@router.delete("")
async def clear_board(
    thread_id: Optional[str] = None,
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    """Clear unpinned bulletins from the blackboard, optionally scoped to `thread_id`."""
    removed = clear_bulletins(thread_id=thread_id)
    return {"status": "ok", "deleted_count": removed}
