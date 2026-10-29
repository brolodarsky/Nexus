"""
service.py — Backend service for the Nexus Resume & Document Compiler Engine.
Provides disk discovery, document reading/editing, headless Chromium/Word rendering,
page geometry metrics parsing, and document asset downloads for the Nexus Tools UI.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Directory Layout & Anchors ────────────────────────────────────────────────
# PROJECT_ROOT: Resolves 5 directory levels up from resume_engine/ to the workspace root
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENGINE_DIR = Path(__file__).resolve().parent

# PORTFOLIO_DIR: Single source of truth for resume and cover letter markdown sources
PORTFOLIO_DIR = (
    PROJECT_ROOT
    / "Vault"
    / "3. Operations"
    / "3.1. Career Strategy & Revenue"
    / "3.1.3. Professional Portfolio & Evidence"
)
RESUMES_DIR = PORTFOLIO_DIR / "Resumes"
COVER_LETTERS_DIR = PORTFOLIO_DIR / "Cover Letters"

# METRICS_CACHE_FILE: Persistent JSON store for page geometry metrics across sessions
METRICS_CACHE_FILE = ENGINE_DIR / "metrics_cache.json"


# ── Metric Cache Storage Helpers ──────────────────────────────────────────────

def _load_metrics_cache() -> Dict[str, Any]:
    """Load cached page metrics from disk to avoid re-rendering to inspect page budgets.

    Returns:
        Dict mapping document base names (e.g. 'Resume - Master') to their metric payload.
    """
    if METRICS_CACHE_FILE.exists():
        try:
            return json.loads(METRICS_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_metrics_cache(cache: Dict[str, Any]) -> None:
    """Persist updated metrics back to disk in JSON format.

    Args:
        cache: Dict mapping document base names to their metric records.
    """
    try:
        METRICS_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[ResumeEngine] Warning: Could not write metrics cache: {e}", file=sys.stderr)


# ── Path Validation & Safety Boundary ─────────────────────────────────────────

def _validate_safe_path(target_path: str | Path) -> Path:
    """Enforce strict directory traversal guards around markdown files in the portfolio.

    Args:
        target_path: String or Path representing an absolute or relative file path.

    Returns:
        Resolved Path guaranteed to reside inside PORTFOLIO_DIR.

    Raises:
        ValueError: If path resolves outside the portfolio directory sandbox.
    """
    path_obj = Path(target_path)
    if not path_obj.is_absolute():
        path_obj = (PROJECT_ROOT / path_obj).resolve()
    else:
        path_obj = path_obj.resolve()

    # Enforce containment: Target must be inside PORTFOLIO_DIR or fail with security violation
    try:
        path_obj.relative_to(PORTFOLIO_DIR.resolve())
    except ValueError:
        raise ValueError(f"Access denied: Path {path_obj} is outside portfolio directory.")

    return path_obj


# ── Document Discovery & Metadata Inspection ──────────────────────────────────

def list_documents() -> List[Dict[str, Any]]:
    """Scan the Vault portfolio for all markdown resumes and cover letters.

    Inspects each document on disk for:
    - Base name and human-friendly display title
    - Section category ('resume' or 'cover_letter')
    - Physical file sizes and last modified timestamps
    - Existence of compiled .pdf and .docx artifacts
    - Latest known page geometry budget metrics (from disk cache)

    Returns:
        List of document summary dictionaries ordered alphabetically by title.
    """
    cache = _load_metrics_cache()
    documents: List[Dict[str, Any]] = []

    # Directories to scan paired with their semantic category tag
    scan_targets: List[Tuple[Path, str, str]] = [
        (RESUMES_DIR, "resume", "Resume"),
        (COVER_LETTERS_DIR, "cover_letter", "Cover Letter"),
    ]

    for directory, category_key, category_label in scan_targets:
        if not directory.exists():
            continue

        for md_file in sorted(directory.glob("*.md")):
            # Skip hidden files or temp backups
            if md_file.name.startswith("."):
                continue

            base_name = md_file.stem
            pdf_sibling = directory / f"{base_name}.pdf"
            docx_sibling = directory / f"{base_name}.docx"

            stat = md_file.stat()
            mod_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

            has_pdf = pdf_sibling.exists()
            has_docx = docx_sibling.exists()

            pdf_stat = pdf_sibling.stat() if has_pdf else None
            docx_stat = docx_sibling.stat() if has_docx else None

            # Retrieve cached metrics if previously rendered
            cached_metric = cache.get(base_name)

            documents.append({
                "id": str(md_file.relative_to(PORTFOLIO_DIR)).replace("\\", "/"),
                "name": base_name,
                "category": category_key,
                "category_label": category_label,
                "path": str(md_file),
                "relative_path": str(md_file.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "size_bytes": stat.st_size,
                "modified_at": mod_dt,
                "has_pdf": has_pdf,
                "has_docx": has_docx,
                "pdf_path": str(pdf_sibling) if has_pdf else None,
                "docx_path": str(docx_sibling) if has_docx else None,
                "pdf_size_bytes": pdf_stat.st_size if pdf_stat else None,
                "docx_size_bytes": docx_stat.st_size if docx_stat else None,
                "pdf_modified_at": (
                    datetime.fromtimestamp(pdf_stat.st_mtime, tz=timezone.utc).isoformat()
                    if pdf_stat
                    else None
                ),
                "docx_modified_at": (
                    datetime.fromtimestamp(docx_stat.st_mtime, tz=timezone.utc).isoformat()
                    if docx_stat
                    else None
                ),
                "metrics": cached_metric,
            })

    return documents


def get_document(target_path: str) -> Dict[str, Any]:
    """Read a single markdown resume/cover letter from disk along with text statistics.

    Args:
        target_path: Path to target markdown file.

    Returns:
        Dict containing document metadata and raw markdown content string.
    """
    safe_path = _validate_safe_path(target_path)
    if not safe_path.exists():
        raise FileNotFoundError(f"Document not found: {safe_path}")

    content = safe_path.read_text(encoding="utf-8")
    stat = safe_path.stat()
    base_name = safe_path.stem

    # Text metrics calculation for quick editorial insight
    lines = content.splitlines()
    words = content.split()
    chars = len(content)

    cache = _load_metrics_cache()
    cached_metric = cache.get(base_name)

    pdf_sibling = safe_path.parent / f"{base_name}.pdf"
    docx_sibling = safe_path.parent / f"{base_name}.docx"

    return {
        "id": str(safe_path.relative_to(PORTFOLIO_DIR)).replace("\\", "/"),
        "name": base_name,
        "path": str(safe_path),
        "relative_path": str(safe_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "content": content,
        "lines_count": len(lines),
        "words_count": len(words),
        "characters_count": chars,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "has_pdf": pdf_sibling.exists(),
        "has_docx": docx_sibling.exists(),
        "pdf_path": str(pdf_sibling) if pdf_sibling.exists() else None,
        "docx_path": str(docx_sibling) if docx_sibling.exists() else None,
        "metrics": cached_metric,
    }


def save_document(target_path: str, content: str) -> Dict[str, Any]:
    """Write updated markdown content directly to a resume or cover letter on disk.

    Args:
        target_path: Target document file path.
        content: New raw markdown text.

    Returns:
        Updated document metadata and stats dict.
    """
    safe_path = _validate_safe_path(target_path)
    safe_path.write_text(content, encoding="utf-8")
    return get_document(str(safe_path))


# ── Headless Document Compilation & Metrics Execution ────────────────────────

def render_documents(
    file_paths: List[str],
    formats: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Execute headless Chromium and native python-docx compilation over target markdown files.

    Runs `node render.js` in a subprocess for Chromium PDF compilation and page budget measurement,
    and invokes `render_docx.render_docx()` natively in Python for Word document generation.

    Args:
        file_paths: List of absolute or relative paths to render (or ['all'] to batch compile all).
        formats: List of formats to emit, e.g. ['pdf', 'docx'], ['pdf'], or ['docx']. Default both.

    Returns:
        Dict containing success flag, array of compiled document records, and execution logs.
    """
    import io
    from contextlib import redirect_stdout
    from nexus.shared_tools.resume_engine.render_docx import render_docx

    formats = formats or ["pdf", "docx"]
    is_pdf = "pdf" in formats
    is_docx = "docx" in formats

    # Resolve target document paths
    resolved_paths: List[Path] = []
    if len(file_paths) == 1 and file_paths[0].strip().lower() == "all":
        resolved_paths = [Path(p["path"]) for p in list_documents()]
    else:
        for fp in file_paths:
            safe = _validate_safe_path(fp)
            if not safe.exists():
                raise FileNotFoundError(f"File not found for rendering: {safe}")
            resolved_paths.append(safe)

    log_chunks: List[str] = []
    metrics_list: List[Dict[str, Any]] = []
    overall_success = True

    # 1. PDF Compilation & Page Geometry Measurement via Headless Chromium
    if is_pdf and resolved_paths:
        cmd = ["node", "render.js"] + [str(p) for p in resolved_paths]
        proc = subprocess.run(
            cmd,
            cwd=str(ENGINE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if proc.returncode != 0:
            overall_success = False
        log_chunks.append(proc.stdout or "")
        if proc.stderr:
            log_chunks.append(proc.stderr)

        # Parse metrics emitted by Chromium renderer
        for line in (proc.stdout or "").splitlines():
            if "[METRICS_JSON]" in line:
                try:
                    raw_json = line.split("[METRICS_JSON]", 1)[1].strip()
                    metrics_list = json.loads(raw_json)
                except Exception as parse_err:
                    print(f"[ResumeEngine] Metrics JSON parse error: {parse_err}", file=sys.stderr)
                break

        # Persist updated page budget measurements into disk cache
        cache = _load_metrics_cache()
        for metric_item in metrics_list:
            file_stem = metric_item.get("file")
            if file_stem:
                cache[file_stem] = {
                    **metric_item,
                    "measured_at": datetime.now(timezone.utc).isoformat(),
                }
        _save_metrics_cache(cache)

    # 2. Native Python Word .docx Compilation
    if is_docx and resolved_paths:
        docx_buf = io.StringIO()
        with redirect_stdout(docx_buf):
            for path_item in resolved_paths:
                try:
                    render_docx(str(path_item))
                except Exception as docx_err:
                    overall_success = False
                    print(f"Error compiling DOCX for {path_item.name}: {docx_err}", file=sys.stderr)
        docx_logs = docx_buf.getvalue().strip()
        if docx_logs:
            log_chunks.append(docx_logs)

    combined_logs = "\n".join(chunk for chunk in log_chunks if chunk).strip()

    # Build output status records
    cache = _load_metrics_cache()
    rendered_records: List[Dict[str, Any]] = []
    metric_lookup = {m.get("file"): m for m in metrics_list}
    downloads_dir = Path(os.environ.get("USERPROFILE", "~")) / "Downloads"

    for path_item in resolved_paths:
        base_name = path_item.stem
        pdf_file = path_item.parent / f"{base_name}.pdf"
        docx_file = path_item.parent / f"{base_name}.docx"

        rendered_records.append({
            "name": base_name,
            "path": str(path_item),
            "relative_path": str(path_item.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "pdf_exists": pdf_file.exists(),
            "docx_exists": docx_file.exists(),
            "pdf_path": str(pdf_file) if pdf_file.exists() else None,
            "docx_path": str(docx_file) if docx_file.exists() else None,
            "downloads_pdf": str(downloads_dir / f"{base_name}.pdf"),
            "downloads_docx": str(downloads_dir / f"{base_name}.docx"),
            "metrics": metric_lookup.get(base_name) or cache.get(base_name),
        })

    return {
        "success": overall_success,
        "exit_code": 0 if overall_success else 1,
        "results": rendered_records,
        "logs": combined_logs,
        "error": None if overall_success else "Rendering completed with errors. Check execution logs.",
    }


# ── Binary Asset Resolution & Stream Delivery ─────────────────────────────────

def resolve_document_file(target_path: str, format_type: str = "pdf") -> Tuple[Path, str, str]:
    """Resolve and validate the exact binary output file for downloading or inline streaming.

    Args:
        target_path: Source markdown path or direct compiled asset path.
        format_type: 'pdf' or 'docx'.

    Returns:
        Tuple of (absolute_file_path, mime_content_type, attachment_filename).

    Raises:
        FileNotFoundError: If the compiled file does not exist on disk.
    """
    safe_path = _validate_safe_path(target_path)
    base_name = safe_path.stem
    parent_dir = safe_path.parent

    ext = ".pdf" if format_type.lower() == "pdf" else ".docx"
    mime = "application/pdf" if ext == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    candidate = parent_dir / f"{base_name}{ext}"
    if not candidate.exists():
        raise FileNotFoundError(f"Compiled {ext} file does not exist yet for {base_name}. Please render it first.")

    return candidate, mime, f"{base_name}{ext}"
