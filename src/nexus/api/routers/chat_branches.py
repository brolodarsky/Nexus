"""
chat_branches.py — Dedicated FastAPI router for Universal Conversation Branching (`chats.db` DAG).

Keeps branching and subroutine-merge HTTP endpoints modular and isolated from `agents.py`.
Mounted at `/api/agents` in `src/nexus/api/main.py`:
  - `POST /api/agents/ask/conversations/{conversation_id}/branch`
  - `POST /api/agents/ask/conversations/{conversation_id}/merge`
"""

import asyncio
from typing import Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nexus.core.chat_branching import distill_and_merge_branch, fork_conversation

router = APIRouter()


# Pydantic request schema for forking a parent conversation at a specific message turn
# - parent_message_id: optional SQLite `messages.id` of the turn where the branch occurs
# - parent_message_index: optional 0-based index fallback when branching from a freshly streamed turn
# - branch_mode: `'tangent'` (context-sliced Parent Context Brief + focal turn) or `'fork'` (full clone)
# - title: optional explicit display title for the child branch
# - model_tier: optional model tier (`'low'`, `'medium'`, `'strong'`) for synthesizing the Parent Context Brief
class BranchConversationRequest(BaseModel):
    parent_message_id: Optional[int] = None
    parent_message_index: Optional[int] = None
    branch_mode: str = "tangent"
    title: Optional[str] = None
    model_tier: Optional[str] = "low"


# Pydantic request schema for distilling a child branch and merging takeaways back into its parent thread
# - guidance: optional user note specifying what aspects of the branch to emphasize
# - model_tier: optional model tier (`'low'`, `'medium'`, `'strong'`) for synthesizing the distillation
class MergeBranchRequest(BaseModel):
    guidance: Optional[str] = None
    model_tier: Optional[str] = "low"


@router.post("/ask/conversations/{conversation_id}/branch")
async def create_conversation_branch(
    conversation_id: str,
    req: BranchConversationRequest,
) -> dict[str, Any]:
    """
    Spawns an isolated child branch conversation from `conversation_id` at the target message turn.

    Executes in a worker thread via `asyncio.to_thread` so LLM synthesis in `'tangent'` mode never blocks
    the async FastAPI event loop.
    """
    try:
        result = await asyncio.to_thread(
            fork_conversation,
            parent_conversation_id=conversation_id,
            parent_message_id=req.parent_message_id,
            parent_message_index=req.parent_message_index,
            branch_mode=req.branch_mode,
            title=req.title,
            model_tier=req.model_tier or "low",
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to branch conversation: {exc}")


@router.post("/ask/conversations/{conversation_id}/merge")
async def merge_conversation_branch(
    conversation_id: str,
    req: MergeBranchRequest,
) -> dict[str, Any]:
    """
    Distills the child branch `conversation_id` and merges its synthesized takeaways into the parent thread.

    Executes in a worker thread via `asyncio.to_thread` so LLM distillation never blocks the FastAPI event loop.
    """
    try:
        result = await asyncio.to_thread(
            distill_and_merge_branch,
            branch_conversation_id=conversation_id,
            user_guidance=req.guidance,
            model_tier=req.model_tier or "low",
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to distill and merge branch: {exc}")
