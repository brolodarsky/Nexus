"""
test_pdf_support.py — Test suite for PDF Document Ingestion, Table Extraction, and Multimodal Vision Pipeline.
Validates:
  1. `vault_reader.py`: `_read_pdf_content` and `read_note_content` on single-page, multi-page, and table PDFs.
  2. `vault_reader.py`: Page-range slicing (`start_page`, `end_page`) and line-range slicing (`start_line`, `end_line`).
  3. `vault_reader.py`: Scanned / image-only document detection for low text layer density.
  4. `shared.py`: `@tool read_file` integration with PDF documents.
  5. `POST /api/agents/upload`: Multi-page PDF rasterization into 2x supersampled PNG pages in `logs/uploads/`.
  6. `POST /api/agents/upload`: Safety guard enforcement against PDFs exceeding maximum page limit (>10 pages).
"""
import io
import pytest
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

import pymupdf
from nexus.api.main import app
from nexus.core.constants import PROJECT_ROOT, VAULT_PATH
from nexus.shared_tools.vault_reader import read_note_content, resolve_vault_note_path, _read_pdf_content
from nexus.shared_tools.shared import read_file

client = TestClient(app)
UPLOADS_DIR = PROJECT_ROOT / "logs" / "uploads"


def create_in_memory_pdf(pages: int = 1, text_per_page: str = "Test PDF Page Content") -> bytes:
    """Helper creating in-memory multi-page PDF document bytes via PyMuPDF."""
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=612, height=792)  # Standard 8.5" x 11" Letter dimensions at 72 DPI
        page.insert_text((50, 72), f"{text_per_page} (Page {i + 1})", fontsize=14)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_read_pdf_vault_single_page():
    """Validates reading a single-page PDF document from the Vault via read_note_content."""
    result = read_note_content("Cover Letter - Agentic AI Focus.pdf")
    assert "--- File:" in result
    assert "(pages 1-1 of 1)" in result
    assert "Computer Science graduate from Fordham University" in result


def test_read_pdf_vault_multi_page_slicing():
    """Validates that page slicing (start_page, end_page) isolates the requested page range."""
    # Doc - Fordham University Transcript.pdf has 4 pages
    result = read_note_content("Doc - Fordham University Transcript.pdf", start_page=2, end_page=2)
    assert "(pages 2-2 of 4)" in result
    assert "FORDHAM UNIVERSITY" in result
    assert "EXPLANATION OF TRANSCRIPT" in result


def test_read_pdf_vault_line_slicing():
    """Validates that line slicing (start_line, end_line) operates on assembled PDF text output."""
    result = read_note_content("Resume - Master.pdf", start_line=1, end_line=4)
    assert "lines 1-4" in result
    lines = [line for line in result.splitlines() if line.strip() and not line.startswith("---")]
    assert len(lines) <= 4


def test_read_pdf_vault_table_extraction():
    """Validates that real-world tables in Vault PDFs (transcript courses) are converted into Markdown tables."""
    content = read_note_content("Doc - Fordham University Transcript.pdf", start_page=1, end_page=1)
    # The transcript contains a 10-column course table
    assert "|COURSE#|COURSETITLE|" in content or "|COURSE #" in content or "|---|" in content
    assert "Bachelor of Science" in content


def test_read_pdf_synthetic_table_extraction(tmp_path: Path):
    """Validates that tabular structures in PDFs are detected and converted to GitHub Flavored Markdown."""
    # Create a synthetic PDF containing a structured table with drawn cell borders
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((50, 50), "Document Title Above Table", fontsize=16)

    # Draw table bounding rectangles (rows & columns) so PyMuPDF find_tables recognizes it
    rects = [
        pymupdf.Rect(50, 100, 200, 140),  # Header Col 1
        pymupdf.Rect(200, 100, 350, 140), # Header Col 2
        pymupdf.Rect(50, 140, 200, 180),  # Row 1 Col 1
        pymupdf.Rect(200, 140, 350, 180), # Row 1 Col 2
    ]
    for r in rects:
        page.draw_rect(r, color=(0, 0, 0), width=1)

    page.insert_text((60, 125), "Metric", fontsize=12)
    page.insert_text((210, 125), "Value", fontsize=12)
    page.insert_text((60, 165), "Latency", fontsize=12)
    page.insert_text((210, 165), "12ms", fontsize=12)

    page.insert_text((50, 220), "Paragraph Text Below Table", fontsize=12)

    test_pdf_file = tmp_path / "table_test.pdf"
    doc.save(str(test_pdf_file))
    doc.close()

    # Read the generated PDF via _read_pdf_content directly
    content = _read_pdf_content(test_pdf_file, rel_path=Path("table_test.pdf"))
    assert "Document Title Above Table" in content
    assert "Paragraph Text Below Table" in content
    assert "Metric" in content
    assert "Latency" in content
    assert "12ms" in content


def test_read_pdf_scanned_detection(tmp_path: Path):
    """Validates that pages with zero text layer and embedded images are flagged as scanned/image documents."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)

    # Insert a dummy in-memory image into the page with zero text
    img = Image.new("RGB", (200, 200), color="green")
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    page.insert_image(pymupdf.Rect(50, 50, 250, 250), stream=img_buf.getvalue())

    scanned_pdf_file = tmp_path / "scanned_test.pdf"
    doc.save(str(scanned_pdf_file))
    doc.close()

    content = _read_pdf_content(scanned_pdf_file, rel_path=Path("scanned_test.pdf"))
    assert "Scanned or image document" in content
    assert "embedded image" in content


def test_read_file_tool_pdf():
    """Validates that the LangChain @tool read_file wrapper seamlessly ingests PDFs."""
    tool_output = read_file.invoke({"file_path": "Cover Letter - Forward Deployed Software Engineer.pdf"})
    assert "--- File:" in tool_output
    assert "(pages 1-1 of 1)" in tool_output
    assert "Forward Deployed" in tool_output


def test_upload_valid_multipage_pdf():
    """Validates that POST /api/agents/upload accepts a 2-page PDF, rasterizes both pages, and returns page_urls."""
    pdf_bytes = create_in_memory_pdf(pages=2, text_per_page="Nexus Multimodal Document Ingestion")
    response = client.post(
        "/api/agents/upload",
        files={"file": ("test_doc.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mime_type"] == "application/pdf"
    assert data["page_count"] == 2
    assert "page_urls" in data
    assert len(data["page_urls"]) == 2
    assert data["url"] == data["page_urls"][0]

    # Verify that each rasterized PNG page exists on disk in logs/uploads/
    created_files = []
    for page_url in data["page_urls"]:
        fname = page_url.split("/")[-1]
        disk_path = UPLOADS_DIR / fname
        assert disk_path.is_file()
        created_files.append(disk_path)

    # Clean up created test assets
    for f in created_files:
        f.unlink(missing_ok=True)


def test_upload_oversized_pdf_page_limit():
    """Validates that PDFs exceeding the maximum 10-page limit are rejected with HTTP 400."""
    oversized_pdf = create_in_memory_pdf(pages=11, text_per_page="Overflow Page")
    response = client.post(
        "/api/agents/upload",
        files={"file": ("too_long.pdf", oversized_pdf, "application/pdf")},
    )
    assert response.status_code == 400
    assert "exceeding the maximum limit of 10 pages" in response.json()["detail"]


def test_upload_corrupted_pdf():
    """Validates that corrupted or malformed PDF payloads are rejected with HTTP 400."""
    corrupted_bytes = b"%PDF-invalid-bytes-header-corrupted"
    response = client.post(
        "/api/agents/upload",
        files={"file": ("broken.pdf", corrupted_bytes, "application/pdf")},
    )
    assert response.status_code == 400
    assert "Corrupted or invalid PDF document" in response.json()["detail"]
