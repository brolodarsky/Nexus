"""
test_image_upload_and_multimodal.py — Test suite for Chat Image Uploads & Multimodal Vision Pipeline.
Validates:
  1. POST /api/agents/upload endpoint (integrity verification, format handling, aspect ratio downscaling).
  2. GET /api/agents/uploads/{filename} endpoint (safe asset serving and path traversal prevention).
  3. chats_db schema persistence and retrieval of `images` column.
  4. resolve_image_to_data_url base64 conversion and HumanMessage multimodal construction in api.py.
"""
import io
import pytest
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from nexus.api.main import app
import nexus.core.chats_db as chats_db
from nexus.core.chats_db import init_db, log_message, get_chat_history, create_conversation, delete_conversation
from nexus.agent.api import resolve_image_to_data_url
from nexus.core.constants import PROJECT_ROOT

client = TestClient(app)
UPLOADS_DIR = PROJECT_ROOT / "logs" / "uploads"


@pytest.fixture(autouse=True)
def isolated_chats_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect `chats_db.DB_PATH` to an isolated temporary SQLite database per test."""
    monkeypatch.setattr(chats_db, "DB_PATH", tmp_path / "test_chats.db")
    init_db()


def create_test_image_bytes(format="PNG", size=(100, 100), color="blue") -> bytes:
    """Helper creating in-memory image bytes for test uploads."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def test_upload_valid_image():
    """Validates that a legitimate PNG image uploads successfully, persists to disk, and returns metadata."""
    img_bytes = create_test_image_bytes(format="PNG", size=(200, 150))
    response = client.post(
        "/api/agents/upload",
        files={"file": ("test_pic.png", img_bytes, "image/png")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert "filename" in data
    assert data["mime_type"] == "image/png"
    assert data["width"] == 200
    assert data["height"] == 150

    # Verify file exists on disk
    saved_file = UPLOADS_DIR / data["filename"]
    assert saved_file.is_file()

    # Clean up test artifact
    saved_file.unlink(missing_ok=True)


def test_upload_oversized_image_downscaling():
    """Validates that images exceeding 1600px are automatically downscaled preserving aspect ratio."""
    # 2400 x 1200 image -> should downscale to max edge 1600 (1600 x 800)
    img_bytes = create_test_image_bytes(format="JPEG", size=(2400, 1200))
    response = client.post(
        "/api/agents/upload",
        files={"file": ("huge_photo.jpg", img_bytes, "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["width"] == 1600
    assert data["height"] == 800

    saved_file = UPLOADS_DIR / data["filename"]
    assert saved_file.is_file()
    saved_file.unlink(missing_ok=True)


def test_upload_rejects_non_image():
    """Validates that non-image file uploads (e.g. .txt, text/plain) are rejected with HTTP 400."""
    response = client.post(
        "/api/agents/upload",
        files={"file": ("malicious.txt", b"plain text payload", "text/plain")},
    )
    assert response.status_code == 400
    assert "Only image files" in response.json()["detail"]


def test_upload_rejects_corrupted_image():
    """Validates that fake or corrupted image bytes are caught and rejected."""
    response = client.post(
        "/api/agents/upload",
        files={"file": ("fake.png", b"not a real png header", "image/png")},
    )
    assert response.status_code == 400
    assert "Corrupted or invalid" in response.json()["detail"]


def test_get_uploaded_image_asset_serving():
    """Validates retrieving a saved image asset via GET /api/agents/uploads/{filename}."""
    img_bytes = create_test_image_bytes(format="PNG", size=(50, 50))
    post_res = client.post(
        "/api/agents/upload",
        files={"file": ("sample.png", img_bytes, "image/png")},
    )
    filename = post_res.json()["filename"]

    # Fetch asset
    get_res = client.get(f"/api/agents/uploads/{filename}")
    assert get_res.status_code == 200
    assert get_res.headers["content-type"] == "image/png"
    assert len(get_res.content) > 0

    # Clean up
    (UPLOADS_DIR / filename).unlink(missing_ok=True)


def test_get_uploaded_image_path_traversal_prevention():
    """Validates that path traversal attacks (e.g. ../../) are neutralized."""
    response = client.get("/api/agents/uploads/../../etc/passwd")
    # Path().name strips traversal components, so it safely searches logs/uploads/passwd and 404s
    assert response.status_code == 404


def test_chats_db_image_persistence():
    """Validates that `log_message` stores image arrays and `get_chat_history` cleanly deserializes them."""
    init_db()
    conv_id = create_conversation("Image Persistence Test")
    try:
        sample_images = ["/api/agents/uploads/img1.png", "/api/agents/uploads/img2.jpg"]
        log_message(
            role="user",
            content="Check these two diagrams",
            conversation_id=conv_id,
            images=sample_images,
        )
        log_message(
            role="assistant",
            content="Analysis complete.",
            conversation_id=conv_id,
        )

        history = get_chat_history(conv_id)
        assert len(history) == 2

        user_turn = history[0]
        assert user_turn["role"] == "user"
        assert user_turn["content"] == "Check these two diagrams"
        assert user_turn["images"] == sample_images

        assistant_turn = history[1]
        assert assistant_turn["role"] == "assistant"
        assert assistant_turn["images"] == []
    finally:
        delete_conversation(conv_id)


def test_resolve_image_to_data_url():
    """Validates converting disk upload paths to base64 data URLs for multimodal LLMs."""
    img_bytes = create_test_image_bytes(format="PNG", size=(30, 30))
    post_res = client.post(
        "/api/agents/upload",
        files={"file": ("data_url_test.png", img_bytes, "image/png")},
    )
    url_ref = post_res.json()["url"]
    filename = post_res.json()["filename"]

    try:
        # 1. Resolve relative API URL
        resolved = resolve_image_to_data_url(url_ref)
        assert resolved.startswith("data:image/png;base64,")

        # 2. Existing data URL should be returned unmodified
        passthrough = resolve_image_to_data_url("data:image/jpeg;base64,abc123xyz")
        assert passthrough == "data:image/jpeg;base64,abc123xyz"

        # 3. Missing file should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            resolve_image_to_data_url("/api/agents/uploads/non_existent_file_9999.png")
    finally:
        (UPLOADS_DIR / filename).unlink(missing_ok=True)


def test_get_chat_history_preserves_conversations_over_50_messages():
    """
    Verifies that conversations with >50 messages (e.g. 55 messages with image attachments at turn 53)
    are returned in full without being truncated by the default limit, while honoring explicit limit params.
    """
    init_db()
    conv_id = create_conversation("Long History & Image Attachment Test")
    try:
        # Insert 52 background turns
        for i in range(52):
            log_message(
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i+1}",
                conversation_id=conv_id,
            )
        
        # Turn 53: user uploads an image attachment
        img_url = "/api/agents/uploads/test_long_history_attachment.png"
        log_message(
            role="user",
            content="Analyze this screenshot",
            conversation_id=conv_id,
            images=[img_url],
        )

        # Turn 54: assistant replies to the image
        log_message(
            role="assistant",
            content="Here is the detailed analysis of the screenshot.",
            conversation_id=conv_id,
        )

        # 1. Unbounded query (default limit=None) via Python chats_db layer
        full_history = get_chat_history(conv_id)
        assert len(full_history) == 54
        assert full_history[52]["role"] == "user"
        assert full_history[52]["images"] == [img_url]
        assert full_history[53]["role"] == "assistant"
        assert full_history[53]["content"] == "Here is the detailed analysis of the screenshot."

        # 2. HTTP GET endpoint /api/agents/ask/history without limit parameter
        api_res = client.get(f"/api/agents/ask/history?conversation_id={conv_id}")
        assert api_res.status_code == 200
        api_history = api_res.json()
        assert len(api_history) == 54
        assert api_history[52]["images"] == [img_url]

        # 3. HTTP GET endpoint with explicit limit parameter (e.g. limit=10)
        api_limited_res = client.get(f"/api/agents/ask/history?conversation_id={conv_id}&limit=10")
        assert api_limited_res.status_code == 200
        assert len(api_limited_res.json()) == 10
    finally:
        delete_conversation(conv_id)

