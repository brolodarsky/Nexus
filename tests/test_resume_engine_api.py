"""
test_resume_engine_api.py — Unit and integration tests for the Resume Engine API and service.
Tests document discovery, safe path resolution, document reading, saving, and endpoint responses.
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from nexus.api.main import app
from nexus.shared_tools.resume_engine import service


@pytest.fixture
def client():
    """Create FastAPI test client instance for testing HTTP routes."""
    return TestClient(app)


def test_list_documents_discovers_portfolio():
    """Verify service.list_documents returns portfolio resumes and cover letters."""
    docs = service.list_documents()
    assert isinstance(docs, list)
    assert len(docs) > 0

    first = docs[0]
    assert "id" in first
    assert "name" in first
    assert "category" in first
    assert first["category"] in ("resume", "cover_letter")
    assert "path" in first
    assert Path(first["path"]).exists()
    assert "size_bytes" in first
    assert "modified_at" in first


def test_get_document_content():
    """Verify service.get_document returns valid markdown source and metrics."""
    docs = service.list_documents()
    assert len(docs) > 0
    target = docs[0]["path"]

    doc = service.get_document(target)
    assert doc["name"] == docs[0]["name"]
    assert "content" in doc
    assert isinstance(doc["content"], str)
    assert len(doc["content"]) > 0
    assert doc["lines_count"] > 0
    assert doc["words_count"] > 0


def test_safe_path_traversal_guard():
    """Verify that path traversal attempts outside the portfolio directory raise ValueError."""
    # Attempting to access sensitive system files or files outside Portfolio should raise ValueError
    with pytest.raises(ValueError, match="Access denied"):
        service.get_document("../../../../.env")

    with pytest.raises(ValueError, match="Access denied"):
        service.get_document("C:/Windows/System32/drivers/etc/hosts")


def test_api_get_resume_documents(client):
    """Verify GET /api/tools/resume/documents returns 200 with structured document array."""
    resp = client.get("/api/tools/resume/documents")
    assert resp.status_code == 200
    data = resp.json()
    assert "documents" in data
    assert "total" in data
    assert data["total"] == len(data["documents"])
    assert data["total"] > 0


def test_api_get_resume_document_detail(client):
    """Verify GET /api/tools/resume/document returns 200 with raw content and counts."""
    docs_resp = client.get("/api/tools/resume/documents")
    first_path = docs_resp.json()["documents"][0]["path"]

    detail_resp = client.get("/api/tools/resume/document", params={"path": first_path})
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert "content" in detail
    assert "lines_count" in detail
    assert "words_count" in detail
    assert detail["path"] == first_path


def test_api_document_not_found(client):
    """Verify GET /api/tools/resume/document returns 404 for nonexistent document within portfolio."""
    non_existent = str(service.PORTFOLIO_DIR / "Resumes" / "NonExistentResume123.md")
    resp = client.get("/api/tools/resume/document", params={"path": non_existent})
    assert resp.status_code == 404


def test_api_document_forbidden_traversal(client):
    """Verify GET /api/tools/resume/document returns 403 for paths attempting to escape portfolio."""
    resp = client.get("/api/tools/resume/document", params={"path": "../../../../../AGENTS.md"})
    assert resp.status_code == 403


def test_api_stream_pdf_file(client):
    """Verify GET /api/tools/resume/file returns application/pdf for an existing compiled resume."""
    docs_resp = client.get("/api/tools/resume/documents")
    compiled_doc = next((d for d in docs_resp.json()["documents"] if d["has_pdf"]), None)

    if compiled_doc:
        resp = client.get("/api/tools/resume/file", params={"path": compiled_doc["path"], "format": "pdf"})
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("content-type", "")
