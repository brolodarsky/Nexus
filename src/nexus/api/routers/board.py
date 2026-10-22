"""
board.py — FastAPI Router for the Shared Inter-Agent Blackboard (`/api/board`).

Exposes REST endpoints so the Next.js Control Panel (`/ask` Live Bulletin Feed) and external clients
can inspect, filter, post, or clear situational bulletins published by Flash subagents and Astra.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nexus.core.blackboard import clear_bulletins, delete_bulletin, get_bulletins, post_bulletin

router = APIRouter()


# Pydantic request model for posting a bulletin via REST API
class BulletinCreateRequest(BaseModel):
    author: str = "User"
    channel: str = "general"
    title: str
    content: str
    pinned: bool = False


@router.get("")
async def list_board_bulletins(
    channel: Optional[str] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    """Return recent bulletins from the Shared Agent Blackboard (`blackboard.db`), optionally filtered by channel."""
    items: List[Dict[str, Any]] = get_bulletins(channel=channel, limit=limit)
    return {"bulletins": items, "count": len(items)}


@router.post("")
async def create_board_bulletin(req: BulletinCreateRequest) -> Dict[str, Any]:
    """Post a new bulletin to the Shared Agent Blackboard."""
    bulletin_id = post_bulletin(
        author=req.author,
        title=req.title,
        content=req.content,
        channel=req.channel,
        pinned=req.pinned,
    )
    return {"status": "ok", "id": bulletin_id}


@router.delete("/{bulletin_id}")
async def remove_board_bulletin(bulletin_id: int) -> Dict[str, Any]:
    """Delete a single bulletin by ID."""
    if not delete_bulletin(bulletin_id):
        raise HTTPException(status_code=404, detail=f"Bulletin #{bulletin_id} not found.")
    return {"status": "ok", "deleted_id": bulletin_id}


@router.delete("")
async def clear_board(channel: Optional[str] = None) -> Dict[str, Any]:
    """Clear unpinned bulletins (or all bulletins in a specific channel)."""
    removed = clear_bulletins(channel=channel)
    return {"status": "ok", "deleted_count": removed}
