"""
tools.py — Operational tools and document compiler routes for Nexus Engine.
Exposes endpoints for the Resume & Document Compiler Engine (discovery, live editing,
headless rendering, page budget metrics, and binary document streaming).
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from nexus.shared_tools.resume_engine import service

# router: Sub-application mounting all /api/tools/* routes to be registered in main.py
router = APIRouter()


# ── Pydantic Request & Response Data Models ───────────────────────────────────

class PageMetrics(BaseModel):
    """Geometry budget measurements calculated during headless Chromium rendering."""
    file: str = Field(..., description="Document file stem name")
    pages: int = Field(..., description="Total pages spanned by rendered document")
    contentHeightPx: float = Field(..., description="Measured scrollHeight of content in pixels")
    pageHeightPx: float = Field(..., description="Target single-page capacity in pixels (e.g. 998px)")
    lastPageFillPct: int = Field(..., description="Percentage of final page occupied by content")
    roomRemainingPx: float = Field(..., description="Remaining pixel headroom on final page")
    approxBulletsRemaining: int = Field(..., description="Estimated bullet points that can still fit")
    verdict: str = Field(..., description="Page budget rating: GOOD FIT, TIGHT FIT, UNDERFILL, ROOM, OVERFLOW")
    measured_at: Optional[str] = Field(None, description="ISO timestamp of when metrics were calculated")


class DocumentSummary(BaseModel):
    """Summary record for a single resume or cover letter discovered in the portfolio."""
    id: str = Field(..., description="Relative identifier from portfolio root")
    name: str = Field(..., description="Human-readable document title")
    category: str = Field(..., description="Semantic category: 'resume' or 'cover_letter'")
    category_label: str = Field(..., description="Formatted display badge label")
    path: str = Field(..., description="Absolute physical disk path")
    relative_path: str = Field(..., description="Path relative to Nexus repository root")
    size_bytes: int = Field(..., description="Disk size of markdown source in bytes")
    modified_at: str = Field(..., description="ISO 8601 modification timestamp")
    has_pdf: bool = Field(..., description="Whether compiled .pdf artifact exists")
    has_docx: bool = Field(..., description="Whether compiled .docx artifact exists")
    pdf_path: Optional[str] = Field(None, description="Absolute path to .pdf if compiled")
    docx_path: Optional[str] = Field(None, description="Absolute path to .docx if compiled")
    pdf_size_bytes: Optional[int] = Field(None, description="Compiled PDF byte size")
    docx_size_bytes: Optional[int] = Field(None, description="Compiled Word byte size")
    pdf_modified_at: Optional[str] = Field(None, description="PDF generation timestamp")
    docx_modified_at: Optional[str] = Field(None, description="Word document generation timestamp")
    metrics: Optional[Dict[str, Any]] = Field(None, description="Last recorded page geometry metrics")


class DocumentListResponse(BaseModel):
    """Collection response returning all discoverable portfolio documents."""
    documents: List[DocumentSummary]
    total: int


class DocumentDetailResponse(BaseModel):
    """Detailed view of a single resume or cover letter including full markdown content."""
    id: str
    name: str
    path: str
    relative_path: str
    content: str = Field(..., description="Raw markdown source text")
    lines_count: int
    words_count: int
    characters_count: int
    modified_at: str
    has_pdf: bool
    has_docx: bool
    pdf_path: Optional[str] = None
    docx_path: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class SaveDocumentRequest(BaseModel):
    """Request payload for writing edited markdown content back to disk."""
    path: str = Field(..., description="Absolute or repo-relative path of document to update")
    content: str = Field(..., description="New markdown source text")


class RenderRequest(BaseModel):
    """Execution parameters for triggering the headless compiler."""
    files: List[str] = Field(..., description="List of file paths to render, or ['all'] for portfolio batch")
    formats: Optional[List[str]] = Field(default=["pdf", "docx"], description="Target formats: ['pdf', 'docx'], ['pdf'], or ['docx']")


class RenderResultRecord(BaseModel):
    """Per-document result summary after compiler execution finishes."""
    name: str
    path: str
    relative_path: str
    pdf_exists: bool
    docx_exists: bool
    pdf_path: Optional[str] = None
    docx_path: Optional[str] = None
    downloads_pdf: Optional[str] = None
    downloads_docx: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class RenderResponse(BaseModel):
    """Overall execution response returned after compiler subprocess completes."""
    success: bool
    exit_code: int
    results: List[RenderResultRecord]
    logs: str = Field(..., description="Standard output and error stream logs from compiler")
    error: Optional[str] = None


# ── Route Endpoints ───────────────────────────────────────────────────────────

@router.get("/resume/documents", response_model=DocumentListResponse)
async def get_resume_documents() -> DocumentListResponse:
    """Scan and return all markdown resumes and cover letters in the portfolio."""
    try:
        docs = service.list_documents()
        return DocumentListResponse(documents=docs, total=len(docs))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scan resume portfolio: {str(exc)}",
        )


@router.get("/resume/document", response_model=DocumentDetailResponse)
async def get_resume_document(
    path: str = Query(..., description="Path to target markdown document")
) -> DocumentDetailResponse:
    """Read full markdown source and editorial statistics for a selected document."""
    try:
        detail = service.get_document(path)
        return DocumentDetailResponse(**detail)
    except FileNotFoundError as fnf_err:
        raise HTTPException(status_code=404, detail=str(fnf_err))
    except ValueError as val_err:
        raise HTTPException(status_code=403, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read resume document: {str(exc)}",
        )


@router.put("/resume/document", response_model=DocumentDetailResponse)
async def save_resume_document(req: SaveDocumentRequest) -> DocumentDetailResponse:
    """Save user modifications to a resume or cover letter on disk."""
    try:
        updated = service.save_document(req.path, req.content)
        return DocumentDetailResponse(**updated)
    except FileNotFoundError as fnf_err:
        raise HTTPException(status_code=404, detail=str(fnf_err))
    except ValueError as val_err:
        raise HTTPException(status_code=403, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save document content: {str(exc)}",
        )


@router.post("/resume/render", response_model=RenderResponse)
async def render_resumes(req: RenderRequest) -> RenderResponse:
    """Trigger Chromium and docx compiler over selected portfolio documents."""
    try:
        res = service.render_documents(req.files, req.formats)
        return RenderResponse(**res)
    except FileNotFoundError as fnf_err:
        raise HTTPException(status_code=404, detail=str(fnf_err))
    except ValueError as val_err:
        raise HTTPException(status_code=403, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Compilation failed with error: {str(exc)}",
        )


@router.get("/resume/file")
async def get_resume_binary_file(
    path: str = Query(..., description="Path to source markdown or compiled file"),
    format: str = Query(default="pdf", description="Format to retrieve: 'pdf' or 'docx'"),
    download: bool = Query(default=False, description="Whether to trigger browser download attachment"),
):
    """Stream a compiled PDF or DOCX file for inline browser viewing or local disk download."""
    try:
        file_path, media_type, filename = service.resolve_document_file(path, format)
        # Content-Disposition: 'attachment' forces browser save prompt; 'inline' renders in browser iframe/tab
        disposition = "attachment" if download else "inline"
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=filename,
            headers={
                "Content-Disposition": f'{disposition}; filename="{filename}"',
            },
        )
    except FileNotFoundError as fnf_err:
        raise HTTPException(status_code=404, detail=str(fnf_err))
    except ValueError as val_err:
        raise HTTPException(status_code=403, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to serve binary document: {str(exc)}",
        )
