"""
test_telegram_bridge.py — Unit and integration tests for the Telegram Mobile Voice & Notification Bridge.

Verifies:
  1. Persistent state ledger (`load_bridge_state`, `save_bridge_state`, `record_message_thread`).
  2. First-user auto-enrollment & strict owner authorization (`authorize_telegram_user`).
  3. Telegram message chunking & HTTP 400 Markdown entity parse fallback (`send_telegram_message`).
  4. Multimodal voice note transcription (`transcribe_audio_bytes`).
  5. End-to-end `process_telegram_message` spine (text, voice notes, swipe-to-reply thread continuation,
     slash commands, and HITL staging alerts in ping-backs).
"""
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

import nexus.shared_tools.telegram_bridge as tb


@pytest.fixture(autouse=True)
def isolated_telegram_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect `STATE_FILE_PATH` and `POLLER_LOCK_PATH` to an isolated temporary directory per test."""
    test_state_file = tmp_path / "telegram_state.json"
    test_lock_file = tmp_path / "telegram_poller.lock"
    monkeypatch.setattr(tb, "STATE_FILE_PATH", test_state_file)
    monkeypatch.setattr(tb, "POLLER_LOCK_PATH", test_lock_file)
    tb.close_telegram_http_client()
    yield test_state_file
    tb.close_telegram_http_client()


def test_default_model_tier_is_low():
    """Verify EngineSettings defaults telegram_default_tier to 'low' for fast, inexpensive mobile turns."""
    from nexus.core.config import EngineSettings

    settings = EngineSettings()
    assert settings.telegram_default_tier == "low"


def test_first_user_auto_enrollment_and_unauthorized_rejection(monkeypatch: pytest.MonkeyPatch):
    """When TELEGRAM_ALLOWED_USER_ID is unset, the first user is auto-enrolled and all other IDs are blocked."""
    mock_settings = MagicMock()
    mock_settings.telegram_allowed_user_id = None
    monkeypatch.setattr(tb, "EngineSettings", lambda: mock_settings)

    # First message from William (user_id=777111, chat_id=777111) auto-enrolls
    is_auth_1, newly_enrolled_1 = tb.authorize_telegram_user(user_id=777111, chat_id=777111)
    assert is_auth_1 is True
    assert newly_enrolled_1 is True

    # Subsequent message from the same user is authorized without re-triggering enrollment banner
    is_auth_2, newly_enrolled_2 = tb.authorize_telegram_user(user_id=777111, chat_id=777111)
    assert is_auth_2 is True
    assert newly_enrolled_2 is False

    # Message from an unknown user ID is rejected
    is_auth_stranger, _ = tb.authorize_telegram_user(user_id=999888, chat_id=999888)
    assert is_auth_stranger is False


def test_explicit_env_allowed_user_id_override(monkeypatch: pytest.MonkeyPatch):
    """When TELEGRAM_ALLOWED_USER_ID is set in .env, only listed user IDs are authorized."""
    mock_settings = MagicMock()
    mock_settings.telegram_allowed_user_id = "111222, 333444"
    monkeypatch.setattr(tb, "EngineSettings", lambda: mock_settings)

    assert tb.authorize_telegram_user(user_id=333444, chat_id=333444) == (True, False)
    assert tb.authorize_telegram_user(user_id=555666, chat_id=555666) == (False, False)


def test_split_telegram_message_respects_boundaries():
    """Verify long agent responses split cleanly below the 4096-character limit."""
    para_a = "A" * 2000
    para_b = "B" * 2200
    combined = f"{para_a}\n{para_b}"
    chunks = tb.split_telegram_message(combined, max_len=3800)
    assert len(chunks) == 2
    assert chunks[0] == para_a
    assert chunks[1] == para_b


def test_send_telegram_message_markdown_fallback_on_400(monkeypatch: pytest.MonkeyPatch):
    """Verify send_telegram_message retries without parse_mode if Telegram returns HTTP 400 on unmatched Markdown."""
    tb.save_bridge_state({"enrolled_user_id": 42, "enrolled_chat_id": 42, "last_update_id": 0, "message_thread_map": {}})

    calls: list[dict[str, Any]] = []

    class DummyResponse:
        def __init__(self, status_code: int, body: dict[str, Any]):
            self.status_code = status_code
            self._body = body
            self.headers = {"content-type": "application/json"}
            self.text = str(body)

        def json(self) -> dict[str, Any]:
            return self._body

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url: str, json: dict[str, Any]) -> DummyResponse:
            calls.append(dict(json))
            # Simulate HTTP 400 when parse_mode="Markdown" is present, then succeed on plain-text retry
            if "parse_mode" in json:
                return DummyResponse(400, {"ok": False, "description": "Bad Request: can't parse entities"})
            return DummyResponse(200, {"ok": True, "result": {"message_id": 501}})

    monkeypatch.setattr(tb.httpx, "Client", DummyClient)
    sent_ids = tb.send_telegram_message("Unmatched _underscore_ test", token="test_token")
    assert sent_ids == [501]
    assert len(calls) == 2
    assert calls[0].get("parse_mode") == "Markdown"
    assert "parse_mode" not in calls[1]


def test_transcribe_audio_bytes_via_whisper(monkeypatch: pytest.MonkeyPatch):
    """Verify Telegram voice notes are transcribed via OpenAI Whisper API when OPENAI_API_KEY is configured."""
    mock_settings = MagicMock()
    mock_settings.gemini_api_key = None
    mock_settings.google_api_key = None
    mock_settings.openai_api_key = "test_openai_key"
    monkeypatch.setattr(tb, "EngineSettings", lambda: mock_settings)

    mock_client = MagicMock()
    mock_tx = MagicMock()
    mock_tx.text = "Add apples and bananas to my shopping list."
    mock_client.audio.transcriptions.create.return_value = mock_tx

    with patch("openai.OpenAI", return_value=mock_client):
        transcript = tb.transcribe_audio_bytes(b"fake_audio_bytes", mime_type="audio/ogg", remote_path="voice/memo.oga")
        assert transcript == "Add apples and bananas to my shopping list."
        assert mock_client.audio.transcriptions.create.called
        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["model"] == "whisper-1"
        assert getattr(call_kwargs["file"], "name", "") == "voice_note.ogg"


def test_transcribe_audio_bytes_via_gemini(monkeypatch: pytest.MonkeyPatch):
    """Verify Telegram voice note bytes are base64-encoded and transcribed via Gemini Flash multimodal audio."""
    mock_settings = MagicMock()
    mock_settings.gemini_api_key = "test_gemini_key"
    mock_settings.google_api_key = None
    mock_settings.openai_api_key = None
    monkeypatch.setattr(tb, "EngineSettings", lambda: mock_settings)

    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = "Check my calendar for tomorrow afternoon and add a task to call Mom."
    mock_llm.invoke.return_value = mock_resp

    monkeypatch.setattr(tb, "get_chat_model", lambda tier, temperature: mock_llm)

    transcript = tb.transcribe_audio_bytes(b"OggS_fake_opus_bytes", mime_type="audio/ogg", remote_path="voice/file_1.oga")
    assert transcript == "Check my calendar for tomorrow afternoon and add a task to call Mom."
    assert mock_llm.invoke.called


def test_audio_document_detection(monkeypatch: pytest.MonkeyPatch):
    """Verify audio files forwarded or uploaded as documents are recognized as audio payloads."""
    mock_settings = MagicMock()
    mock_settings.telegram_bot_token = "test_token"
    mock_settings.telegram_allowed_user_id = "888"
    mock_settings.telegram_default_tier = "low"
    monkeypatch.setattr(tb, "EngineSettings", lambda: mock_settings)

    monkeypatch.setattr(tb, "send_chat_action", lambda *a, **kw: None)
    monkeypatch.setattr(tb, "download_telegram_file", lambda file_id, token=None: (b"wav_bytes", "documents/note.wav"))
    monkeypatch.setattr(tb, "transcribe_audio_bytes", lambda *a, **kw: "Document audio transcript")
    monkeypatch.setattr(tb, "send_telegram_message", lambda *a, **kw: [301])
    monkeypatch.setattr(tb, "log_run", lambda **kw: None)

    with patch("nexus.agent.api.run_nexus_agent_with_trace") as mock_run:
        mock_run.return_value = {
            "response": "Acknowledged audio document",
            "agent": "nexus",
            "domain": None,
            "confidence": 1.0,
            "model_tier": "low",
            "model_name": "gemini-4-hydrogen",
        }
        doc_msg = {
            "message_id": 105,
            "from": {"id": 888, "username": "willi"},
            "chat": {"id": 888},
            "document": {"file_id": "doc_wav", "file_name": "voice_recording.wav", "mime_type": "audio/wav"},
        }
        res = tb.process_telegram_message(doc_msg, token="test_token")
        assert res["status"] == "ok"
        assert res["transcribed_voice"] == "Document audio transcript"


def test_process_telegram_voice_and_swipe_reply_continuity(monkeypatch: pytest.MonkeyPatch):
    """Verify a voice note creates a new mobile chat thread, pings back with HITL details, and swipe-to-reply continues the same thread."""
    mock_settings = MagicMock()
    mock_settings.telegram_bot_token = "test_token"
    mock_settings.telegram_allowed_user_id = "888"
    mock_settings.telegram_default_tier = "low"
    monkeypatch.setattr(tb, "EngineSettings", lambda: mock_settings)

    # Stub network & transcription helpers
    monkeypatch.setattr(tb, "send_chat_action", lambda *a, **kw: None)
    monkeypatch.setattr(tb, "download_telegram_file", lambda file_id, token=None: (b"ogg_bytes", "voice/file_1.oga"))
    monkeypatch.setattr(tb, "transcribe_audio_bytes", lambda audio_bytes, mime_type="audio/ogg", **kw: "Add task to inspect Pilot radiator")
    monkeypatch.setattr(tb, "_generate_mobile_conversation_title", lambda cid, q, r="": "📱 Inspect Pilot Radiator")
    monkeypatch.setattr(
        tb,
        "get_pending_hitl_for_conversation",
        lambda cid: [{"id": 99, "action_type": "modify", "target_file": "Vault/Tasks.md", "destination_file": None}],
    )

    sent_payloads: list[dict[str, Any]] = []

    def fake_send(text: str, chat_id=None, reply_to_message_id=None, token=None) -> list[int]:
        sent_payloads.append({"text": text, "chat_id": chat_id, "reply_to": reply_to_message_id})
        return [200 + len(sent_payloads)]

    monkeypatch.setattr(tb, "send_telegram_message", fake_send)
    monkeypatch.setattr(tb, "log_run", lambda **kw: None)

    captured_threads: list[str] = []

    def fake_run_agent(query: str, thread_id: str, model_tier=None, images=None) -> dict[str, Any]:
        captured_threads.append(thread_id)
        return {
            "response": f"Staged task for: {query}",
            "agent": "nexus",
            "domain": "operations",
            "confidence": 1.0,
            "reasoning": "Test",
            "model_tier": "low",
            "model_name": "gemini-4-hydrogen",
            "tool_calls": [],
        }

    with patch("nexus.agent.api.run_nexus_agent_with_trace", side_effect=fake_run_agent):
        # 1. Incoming Telegram Voice Note (message_id=101)
        voice_msg = {
            "message_id": 101,
            "from": {"id": 888, "username": "willi"},
            "chat": {"id": 888},
            "voice": {"file_id": "voice_abc", "mime_type": "audio/ogg", "duration": 4},
        }
        res1 = tb.process_telegram_message(voice_msg, token="test_token")
        assert res1["status"] == "ok"
        assert res1["transcribed_voice"] == "Add task to inspect Pilot radiator"
        assert res1["hitl_staged_count"] == 1
        first_conv_id = res1["conversation_id"]

        # Verify ping-back contains voice transcript, agent response, and HITL staged notice
        assert len(sent_payloads) == 1
        ping_text = sent_payloads[0]["text"]
        assert "🎙️ _Add task to inspect Pilot radiator_" in ping_text
        assert "Staged task for: Add task to inspect Pilot radiator" in ping_text
        assert "HITL Staged (1)" in ping_text
        assert "Vault/Tasks.md" in ping_text

        # 2. User swipes-to-reply on the bot's ping-back message (message_id=201) with text
        followup_msg = {
            "message_id": 102,
            "from": {"id": 888, "username": "willi"},
            "chat": {"id": 888},
            "text": "Also mark it high priority",
            "reply_to_message": {"message_id": 201},
        }
        res2 = tb.process_telegram_message(followup_msg, token="test_token")
        assert res2["status"] == "ok"
        # Must reuse the exact same conversation_id!
        assert res2["conversation_id"] == first_conv_id
        assert captured_threads == [first_conv_id, first_conv_id]


def test_telegram_http_client_singleton_and_close():
    """Verify get_telegram_http_client returns a reusable singleton and closes cleanly."""
    c1 = tb.get_telegram_http_client()
    c2 = tb.get_telegram_http_client()
    assert c1 is c2
    assert not c1.is_closed

    tb.close_telegram_http_client()
    assert tb._http_client is None
    assert c1.is_closed


def test_download_telegram_file_retries_on_ssl_timeout_and_succeeds(monkeypatch: pytest.MonkeyPatch):
    """Verify download_telegram_file retries after transient SSL handshake timeouts and succeeds."""
    mock_settings = MagicMock()
    mock_settings.telegram_bot_token = "test_bot_token"
    monkeypatch.setattr(tb, "EngineSettings", lambda: mock_settings)
    monkeypatch.setattr(tb.time, "sleep", lambda s: None)

    attempts = {"getFile": 0, "download": 0}

    class DummyClient:
        def post(self, url: str, json: dict[str, Any]):
            attempts["getFile"] += 1
            if attempts["getFile"] == 1:
                # Simulate cold SSL handshake timeout (_ssl.c:993)
                raise httpx.ConnectTimeout("_ssl.c:993: The handshake operation timed out")
            # Attempt 2 succeeds
            resp = MagicMock()
            resp.raise_for_status = lambda: None
            resp.json = lambda: {"ok": True, "result": {"file_path": "voice/test.oga"}}
            return resp

        def get(self, url: str):
            attempts["download"] += 1
            resp = MagicMock()
            resp.raise_for_status = lambda: None
            resp.content = b"fake_audio_payload_bytes"
            return resp

    monkeypatch.setattr(tb, "get_telegram_http_client", lambda: DummyClient())

    content, remote_path = tb.download_telegram_file("voice_123", max_retries=3)
    assert content == b"fake_audio_payload_bytes"
    assert remote_path == "voice/test.oga"
    assert attempts["getFile"] == 2
    assert attempts["download"] == 1


def test_download_telegram_file_exhaustion_raises(monkeypatch: pytest.MonkeyPatch):
    """Verify download_telegram_file raises RuntimeError when retries are exhausted."""
    mock_settings = MagicMock()
    mock_settings.telegram_bot_token = "test_bot_token"
    monkeypatch.setattr(tb, "EngineSettings", lambda: mock_settings)
    monkeypatch.setattr(tb.time, "sleep", lambda s: None)

    class FailingClient:
        def post(self, url: str, json: dict[str, Any]):
            raise httpx.ConnectTimeout("_ssl.c:993: The handshake operation timed out")

    monkeypatch.setattr(tb, "get_telegram_http_client", lambda: FailingClient())

    with pytest.raises(RuntimeError) as exc_info:
        tb.download_telegram_file("voice_fail", max_retries=3)
    assert "exhausted 3 attempts" in str(exc_info.value) or "Failed to download Telegram file" in str(exc_info.value)


def test_process_telegram_message_distinguishes_download_failure(monkeypatch: pytest.MonkeyPatch):
    """Verify voice download errors are logged and pinged back as 'Voice Download Error' rather than transcription error."""
    mock_settings = MagicMock()
    mock_settings.telegram_bot_token = "test_token"
    mock_settings.telegram_allowed_user_id = "888"
    mock_settings.telegram_default_tier = "low"
    monkeypatch.setattr(tb, "EngineSettings", lambda: mock_settings)

    monkeypatch.setattr(tb, "send_chat_action", lambda *a, **kw: None)

    def failing_download(file_id, token=None):
        raise RuntimeError("Handshake timed out after 3 attempts")

    monkeypatch.setattr(tb, "download_telegram_file", failing_download)

    sent_alerts: list[str] = []

    def mock_send(text: str, chat_id=None, reply_to_message_id=None, token=None):
        sent_alerts.append(text)
        return [701]

    monkeypatch.setattr(tb, "send_telegram_message", mock_send)

    voice_msg = {
        "message_id": 303,
        "from": {"id": 888, "username": "willi"},
        "chat": {"id": 888},
        "voice": {"file_id": "bad_voice_file", "mime_type": "audio/ogg"},
    }
    res = tb.process_telegram_message(voice_msg, token="test_token")
    assert res["status"] == "error"
    assert res["phase"] == "download"
    assert "Handshake timed out" in res["error"]
    assert len(sent_alerts) == 1
    assert "Voice Download Error" in sent_alerts[0]
