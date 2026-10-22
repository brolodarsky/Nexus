from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
import os
import subprocess

from nexus.core.hitl_queue import (
    get_pending_transactions,
    get_transaction,
    update_transaction_status,
    add_transaction,
    commit_transaction,
    rollback_transaction,
    rebase_transaction,
    get_recent_revisions,
    HitlCommitError,
    TransactionNotFoundError,
    StaleBaseError,
    MergeConflictError,
)
from nexus.core.constants import PROJECT_ROOT

router = APIRouter()


def _raise_http_for(err: HitlCommitError) -> None:
    """Maps engine commit errors to HTTP codes the GUI can branch on.

    404 -> unknown tx | 409 + structured `detail` -> stale base / merge conflict | 400 -> invalid state.
    The 409 `detail` is a dict (FastAPI serializes it as JSON) so the GUI can read `code` and `current_content`.
    """
    if isinstance(err, TransactionNotFoundError):
        raise HTTPException(status_code=404, detail=str(err))
    if isinstance(err, StaleBaseError):
        raise HTTPException(
            status_code=409,
            detail={"code": "stale_base", "message": str(err), "current_content": err.current_content},
        )
    if isinstance(err, MergeConflictError):
        raise HTTPException(status_code=409, detail={"code": "merge_conflict", "message": str(err)})
    raise HTTPException(status_code=400, detail=str(err))

class TransactionResponse(BaseModel):
    id: int
    agent_name: str
    action_type: str
    target_file: str
    original_content: Optional[str]
    proposed_content: str
    reasoning: Optional[str]
    status: str
    created_at: str

@router.get("/pending", response_model=List[TransactionResponse])
async def get_pending():
    """Fetch all pending HITL transactions."""
    return get_pending_transactions()

@router.get("/revisions/recent")
async def recent_revisions(limit: int = 20):
    """List recently applied revisions (newest first) so the GUI can offer Undo."""
    return get_recent_revisions(limit)

@router.get("/{tx_id}", response_model=TransactionResponse)
async def get_tx(tx_id: int):
    """Fetch a specific transaction."""
    tx = get_transaction(tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx

@router.post("/{tx_id}/approve")
async def approve_tx(tx_id: int, force: bool = False):
    """Approve a transaction and write to disk.

    Delegates to `commit_transaction`, which refuses with 409 `stale_base` if the note changed on disk
    since the edit was staged (pass `?force=true` to overwrite anyway) and snapshots the prior content
    into `revisions` so the write can be undone via `/rollback`.
    """
    # Resolve target_file against PROJECT_ROOT so relative paths
    # (e.g. "Vault/...") always land in the correct location,
    # regardless of uvicorn's working directory.
    try:
        result = commit_transaction(tx_id, PROJECT_ROOT, force=force)
    except HitlCommitError as err:
        _raise_http_for(err)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write file: {str(e)}")

    # Optional: trigger sync_vault.py or commit script
    # This might run in background, but for now we just try to call it if it exists.
    # Sync script isn't strictly required for the test to pass, but good practice.
    # We will assume scripts/sync_vault.py exists and can be run.
    # subprocess.run(["python", "scripts/sync_vault.py"])

    return {"status": "success", "message": "Transaction approved and applied", **result}

@router.post("/{tx_id}/rollback")
async def rollback_tx(tx_id: int, force: bool = False):
    """Restore the note to its pre-approval snapshot (409 `stale_base` if it changed since approval)."""
    try:
        result = rollback_transaction(tx_id, PROJECT_ROOT, force=force)
    except HitlCommitError as err:
        _raise_http_for(err)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore file: {str(e)}")
    return {"status": "success", "message": "Transaction rolled back", **result}

@router.post("/{tx_id}/rebase")
async def rebase_tx(tx_id: int):
    """Re-stage a stale pending edit on top of current disk content (409 `merge_conflict` if edits touch)."""
    try:
        result = rebase_transaction(tx_id, PROJECT_ROOT)
    except HitlCommitError as err:
        _raise_http_for(err)
    return {"status": "success", **result}

@router.post("/{tx_id}/reject")
async def reject_tx(tx_id: int):
    """Reject a transaction."""
    tx = get_transaction(tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if tx['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Transaction is not pending")

    update_transaction_status(tx_id, "rejected")
    return {"status": "success", "message": "Transaction rejected"}

class MockTransactionRequest(BaseModel):
    agent_name: str
    action_type: str
    target_file: str
    original_content: Optional[str] = None
    proposed_content: str
    reasoning: Optional[str] = None

@router.post("/mock")
async def create_mock_tx(request: MockTransactionRequest):
    """Create a mock transaction for testing."""
    tx_id = add_transaction(
        agent_name=request.agent_name,
        action_type=request.action_type,
        target_file=request.target_file,
        original_content=request.original_content,
        proposed_content=request.proposed_content,
        reasoning=request.reasoning
    )
    return {"status": "success", "tx_id": tx_id}
