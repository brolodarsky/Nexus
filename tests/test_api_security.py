"""
test_api_security.py — Regression suite for Nexus API Bearer Auth, Host Validation (`S6`),
and single-turn `persist_conversation_model=False` preservation (`C3`).
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from nexus.api.main import app
import nexus.api.security as security
import nexus.core.chats_db as chats_db


@pytest.fixture
def auth_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Enable strict TestClient auth enforcement backed by an isolated temporary token file."""
    token_file = tmp_path / "api_token"
    monkeypatch.setattr(security, "API_TOKEN_FILE", token_file)
    monkeypatch.delenv("NEXUS_API_TOKEN", raising=False)
    monkeypatch.delenv("NEXUS_LOCALHOST_ONLY", raising=False)
    monkeypatch.setenv("NEXUS_ENFORCE_TEST_AUTH", "1")
    return security.get_or_create_api_token()


def test_api_token_auto_generation_and_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify get_or_create_api_token generates, persists, and reuses a 32-byte URL-safe token."""
    token_file = tmp_path / "nested" / "api_token"
    monkeypatch.setattr(security, "API_TOKEN_FILE", token_file)
    monkeypatch.delenv("NEXUS_API_TOKEN", raising=False)

    tok1 = security.get_or_create_api_token()
    assert len(tok1) >= 32
    assert token_file.is_file()
    assert security.get_or_create_api_token() == tok1


def test_bearer_and_x_nexus_token_auth_across_routers(auth_env: str) -> None:
    """Verify /api/health stays public while /api/* routers require Bearer or X-Nexus-Token."""
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

    # Health check stays unauthenticated for startup probes
    health_res = client.get("/api/health")
    assert health_res.status_code == 200
    assert health_res.json()["auth_enabled"] is True

    # Missing or invalid credentials -> 401
    for path in (
        "/api/vault/notes",
        "/api/hitl/pending",
        "/api/agents/models",
        "/api/telegram/status",
        "/api/browser/tabs",
    ):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer wrong-token"}).status_code == 401

    # Valid Authorization: Bearer and X-Nexus-Token -> 200 (or 503 for disconnected browser extension)
    assert client.get("/api/agents/models", headers={"Authorization": f"Bearer {auth_env}"}).status_code == 200
    assert client.get("/api/telegram/status", headers={"X-Nexus-Token": auth_env}).status_code == 200
    assert client.get("/api/browser/tabs", headers={"X-Nexus-Token": auth_env}).status_code == 503


def test_query_token_strictly_scoped_to_media_get_routes(
    auth_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify `?token=` works on media/upload GET routes and is rejected on standard JSON endpoints."""
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

    # Regular JSON API endpoints must NOT accept ?token= query params
    assert client.get(f"/api/agents/models?token={auth_env}").status_code == 401
    assert client.get(f"/api/vault/notes?token={auth_env}").status_code == 401

    # Media upload GET route accepts ?token= (returns 404 for nonexistent file rather than 401)
    import nexus.api.routers.agents as agents_router

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    (uploads_dir / "sample.png").write_bytes(b"pngdata")
    monkeypatch.setattr(agents_router, "UPLOADS_DIR", uploads_dir)

    assert client.get("/api/agents/uploads/sample.png").status_code == 401
    media_res = client.get(f"/api/agents/uploads/sample.png?token={auth_env}")
    assert media_res.status_code == 200
    assert media_res.content == b"pngdata"

    # Podcast download and resume file routes also honor ?token= past auth (reject 401 without token; reach path validation with token)
    assert client.get("/api/vault/podcast/download?path=NonExistent.md").status_code == 401
    assert client.get(f"/api/vault/podcast/download?path=NonExistent.md&token={auth_env}").status_code in (400, 403, 404)
    assert client.get("/api/tools/resume/file?path=NonExistent.md").status_code == 401
    assert client.get(f"/api/tools/resume/file?path=NonExistent.md&token={auth_env}").status_code in (400, 403, 404)


def test_host_header_validation_and_localhost_only_mode(auth_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify HostValidationMiddleware blocks DNS rebinding while permitting LAN/Tailscale unless localhost-only."""
    headers = {"Authorization": f"Bearer {auth_env}"}

    # DNS-rebinding attack host rejected with 403
    evil_client = TestClient(app, base_url="http://evil.attacker.com:8000", client=("127.0.0.1", 50000))
    assert evil_client.get("/api/health").status_code == 403

    # RFC1918 LAN and Tailscale hosts permitted in default mode
    for origin_base in (
        "http://192.168.1.25:8000",
        "http://10.0.0.14:8000",
        "http://100.88.1.2:8000",
        "http://nexus-host.tail1234.ts.net:8000",
    ):
        lan_client = TestClient(app, base_url=origin_base, client=("192.168.1.50", 50000))
        assert lan_client.get("/api/agents/models", headers=headers).status_code == 200

    # NEXUS_LOCALHOST_ONLY=true blocks both LAN hosts and non-loopback peers
    monkeypatch.setenv("NEXUS_LOCALHOST_ONLY", "true")
    lan_client = TestClient(app, base_url="http://192.168.1.25:8000", client=("192.168.1.50", 50000))
    assert lan_client.get("/api/health").status_code == 403

    local_client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    assert local_client.get("/api/agents/models", headers=headers).status_code == 200


def test_browser_bridge_extension_origin_and_web_origin_blocking(auth_env: str) -> None:
    """Verify /api/browser/status and /ws allow chrome-extension:// probes while blocking http:// web origins."""
    client = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

    # Chrome extension Origin without token succeeds on loopback
    ext_headers = {"Origin": "chrome-extension://abcdefghijklmnop"}
    assert client.get("/api/browser/status", headers=ext_headers).status_code == 200

    # Arbitrary webpage Origin without token is blocked on both HTTP and WS
    assert client.get("/api/browser/status", headers={"Origin": "https://evil.example"}).status_code == 401
    with pytest.raises(WebSocketDisconnect) as ws_exc:
        with client.websocket_connect("/api/browser/ws", headers={"Origin": "https://evil.example"}):
            pass
    assert ws_exc.value.code == 1008


def test_log_message_persist_conversation_model_false_preserves_baseline() -> None:
    """Verify 1× Boost (`persist_conversation_model=False`) records turn model on messages without clobbering baseline."""
    conv_id = chats_db.create_conversation(
        title="Boost Baseline Test",
        last_model_tier="medium",
        last_model_name="gemini-4-hydrogen",
    )
    chats_db.log_message(
        role="user",
        content="Hard planning question",
        conversation_id=conv_id,
        model_tier="strong",
        model_name="gemini-4-argon",
        persist_conversation_model=False,
    )
    chats_db.log_message(
        role="assistant",
        content="Deep answer",
        agent="nexus",
        conversation_id=conv_id,
        model_tier="strong",
        model_name="gemini-4-argon",
        persist_conversation_model=False,
    )

    conv = chats_db.get_conversation(conv_id)
    assert conv is not None
    assert conv["last_model_tier"] == "medium"
    assert conv["last_model_name"] == "gemini-4-hydrogen"

    history = chats_db.get_chat_history(conv_id)
    assert len(history) == 2
    assert history[-1]["model_tier"] == "strong"
    assert history[-1]["model_name"] == "gemini-4-argon"
