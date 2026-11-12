"""
test_transcribe_media.py — Comprehensive unit tests for the Gemini multimodal media transcription tool.

Tests file resolution, MIME detection, Gemini File API upload, processing polling,
verbatim transcript generation, Vault note persistence, error handling, LangChain @tool integration,
and CLI entrypoint behavior.
"""
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.genai import types

from nexus.core.constants import VAULT_PATH
from nexus.shared_tools.shared import transcribe_media
from nexus.shared_tools.transcribe_media import (
    main,
    resolve_media_file,
    transcribe_media_file,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_audio_file(tmp_path: Path) -> Path:
    """Create a temporary non-empty dummy audio file."""
    audio = tmp_path / "sample_recording.mp3"
    audio.write_bytes(b"\xFF\xFB\x90\x04" + b"\x00" * 512)
    return audio


@pytest.fixture
def temp_video_file(tmp_path: Path) -> Path:
    """Create a temporary non-empty dummy video file."""
    video = tmp_path / "sample_video.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 1024)
    return video


# ── 1. File & Container Resolution Tests ─────────────────────────────────────

def test_resolve_media_file_audio(temp_audio_file: Path):
    """Verifies that resolve_media_file correctly locates audio files and returns audio MIME type."""
    resolved, mime, category = resolve_media_file(temp_audio_file)
    assert resolved == temp_audio_file.resolve()
    assert mime == "audio/mp3"
    assert category == "audio"


def test_resolve_media_file_video(temp_video_file: Path):
    """Verifies that resolve_media_file correctly locates video files and returns video MIME type."""
    resolved, mime, category = resolve_media_file(temp_video_file)
    assert resolved == temp_video_file.resolve()
    assert mime == "video/mp4"
    assert category == "video"


def test_resolve_media_file_not_found():
    """Verifies FileNotFoundError is raised when target path cannot be found."""
    with pytest.raises(FileNotFoundError, match="Media file not found"):
        resolve_media_file("non_existent_recording_file_12345.mp3")


def test_resolve_media_file_empty(tmp_path: Path):
    """Verifies ValueError is raised for 0-byte media files."""
    empty_file = tmp_path / "empty.wav"
    empty_file.write_bytes(b"")
    with pytest.raises(ValueError, match="Media file is empty"):
        resolve_media_file(empty_file)


def test_resolve_media_file_unsupported_extension(tmp_path: Path):
    """Verifies ValueError is raised for unsupported file types."""
    bad_file = tmp_path / "notes.txt"
    bad_file.write_bytes(b"some text content")
    with pytest.raises(ValueError, match="Unsupported media format"):
        resolve_media_file(bad_file)


# ── 2. Transcription Engine & Mocked Gemini API Tests ────────────────────────

@patch("nexus.shared_tools.transcribe_media.genai.Client")
@patch("nexus.shared_tools.transcribe_media.settings")
def test_transcribe_media_file_success(
    mock_settings: MagicMock,
    mock_client_class: MagicMock,
    temp_audio_file: Path,
    tmp_path: Path,
):
    """Verifies end-to-end transcription: upload -> generate -> cleanup -> note write."""
    mock_settings.gemini_api_key = "fake_gemini_key"
    mock_settings.google_api_key = None
    mock_settings.gemini_model_low = "gemini-4-hydrogen"

    # Mock client and file upload
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_file = MagicMock()
    mock_file.name = "files/test_audio_file_id"
    mock_file.state = types.FileState.ACTIVE
    mock_file.video_metadata = None
    mock_client.files.upload.return_value = mock_file

    expected_full_transcript = (
        "[00:00] Speaker 1: Good afternoon, thanks for jumping on this call today.\n"
        "[00:05] Speaker 2: Absolutely, happy to be here. Excited to dive into the architecture."
    )
    mock_response = MagicMock()
    mock_response.text = expected_full_transcript
    mock_client.models.generate_content.return_value = mock_response

    custom_output_note = "0. Inbox/Transcripts/Custom_Audio_Test.md"
    result = transcribe_media_file(
        file_path=temp_audio_file,
        output_note_path=custom_output_note,
        include_timestamps=True,
        save_to_vault=True,
    )

    # 1. Assert return contains the full transcript
    assert expected_full_transcript in result
    assert "Saved full transcript note" in result

    # 2. Assert client upload called with correct file and MIME
    mock_client.files.upload.assert_called_once()
    upload_kwargs = mock_client.files.upload.call_args[1]
    assert upload_kwargs["file"] == temp_audio_file.resolve()
    assert upload_kwargs["config"].mime_type == "audio/mp3"

    # 3. Assert generate_content was called with prompt and uploaded file
    mock_client.models.generate_content.assert_called_once()
    gen_args = mock_client.models.generate_content.call_args
    assert gen_args.kwargs["model"] == "models/gemini-4-hydrogen"
    assert gen_args.kwargs["contents"][0] == mock_file
    assert "VERBATIM" in gen_args.kwargs["contents"][1]

    # 4. Assert uploaded file was cleaned up from Gemini server in finally block
    mock_client.files.delete.assert_called_once_with(name="files/test_audio_file_id")

    # 5. Assert markdown note was persisted to disk in Vault
    saved_note_path = VAULT_PATH / custom_output_note
    try:
        assert saved_note_path.exists()
        content = saved_note_path.read_text(encoding="utf-8")
        assert "type: transcript" in content
        assert "## Verbatim Transcript" in content
        assert expected_full_transcript in content
    finally:
        if saved_note_path.exists():
            saved_note_path.unlink()


@patch("nexus.shared_tools.transcribe_media.genai.Client")
@patch("nexus.shared_tools.transcribe_media.settings")
def test_transcribe_media_processing_poll(
    mock_settings: MagicMock,
    mock_client_class: MagicMock,
    temp_video_file: Path,
):
    """Verifies that transcribe_media_file polls files.get while state is PROCESSING until ACTIVE."""
    mock_settings.gemini_api_key = "fake_gemini_key"
    mock_settings.google_api_key = None
    mock_settings.gemini_model_low = "gemini-4-hydrogen"

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    # 1st state PROCESSING, 2nd state ACTIVE
    file_step1 = MagicMock()
    file_step1.name = "files/test_video_poll"
    file_step1.state = types.FileState.PROCESSING
    file_step1.video_metadata = None

    file_step2 = MagicMock()
    file_step2.name = "files/test_video_poll"
    file_step2.state = types.FileState.ACTIVE
    file_step2.video_metadata = None

    mock_client.files.upload.return_value = file_step1
    mock_client.files.get.return_value = file_step2

    mock_response = MagicMock()
    mock_response.text = "Video dialogue transcript."
    mock_client.models.generate_content.return_value = mock_response

    with patch("time.sleep", return_value=None):
        result = transcribe_media_file(
            file_path=temp_video_file,
            save_to_vault=False,  # Skip vault note writing
        )

    assert result == "Video dialogue transcript."
    mock_client.files.get.assert_called_once_with(name="files/test_video_poll")
    mock_client.files.delete.assert_called_once_with(name="files/test_video_poll")


@patch("nexus.shared_tools.transcribe_media.genai.Client")
@patch("nexus.shared_tools.transcribe_media.settings")
def test_transcribe_media_failed_state(
    mock_settings: MagicMock,
    mock_client_class: MagicMock,
    temp_video_file: Path,
):
    """Verifies RuntimeError is raised if server-side processing fails."""
    mock_settings.gemini_api_key = "fake_gemini_key"
    mock_settings.google_api_key = None
    mock_settings.gemini_model_low = "gemini-4-hydrogen"

    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    failed_file = MagicMock()
    failed_file.name = "files/failed_file"
    failed_file.state = types.FileState.FAILED
    failed_file.error = "Corrupted container"

    mock_client.files.upload.return_value = failed_file

    with pytest.raises(RuntimeError, match="Gemini media processing failed"):
        transcribe_media_file(temp_video_file)

    # Cleanup must still run
    mock_client.files.delete.assert_called_once_with(name="files/failed_file")


@patch("nexus.shared_tools.transcribe_media.settings")
def test_transcribe_media_missing_api_key(
    mock_settings: MagicMock,
    temp_audio_file: Path,
):
    """Verifies ValueError is raised if GEMINI_API_KEY is not configured."""
    mock_settings.gemini_api_key = None
    mock_settings.google_api_key = None

    with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
        transcribe_media_file(temp_audio_file)


# ── 3. LangChain @tool Integration Tests ─────────────────────────────────────

@patch("nexus.shared_tools.transcribe_media.transcribe_media_file")
def test_transcribe_media_tool_wrapper(mock_transcribe: MagicMock):
    """Verifies the @tool transcribe_media executes cleanly and returns verbatim text."""
    mock_transcribe.return_value = "Verbatim speech from tool wrapper."

    res = transcribe_media.invoke({"file_path": "meeting.mp4"})
    assert res == "Verbatim speech from tool wrapper."
    mock_transcribe.assert_called_once_with(
        file_path="meeting.mp4",
        output_note_path=None,
        include_timestamps=True,
        save_to_vault=True,
    )


@patch("nexus.shared_tools.transcribe_media.transcribe_media_file")
def test_transcribe_media_tool_wrapper_handles_error(mock_transcribe: MagicMock):
    """Verifies the @tool catches exceptions and returns an informative error string."""
    mock_transcribe.side_effect = RuntimeError("Quota exhausted")

    res = transcribe_media.invoke({"file_path": "recording.mp3"})
    assert "Error transcribing media file" in res
    assert "Quota exhausted" in res


# ── 4. CLI Execution Tests ───────────────────────────────────────────────────

@patch("nexus.shared_tools.transcribe_media.transcribe_media_file")
def test_cli_main_success(mock_transcribe: MagicMock, capsys: pytest.CaptureFixture):
    """Verifies CLI entrypoint parses flags and outputs transcript."""
    mock_transcribe.return_value = "CLI transcript result"

    with patch.object(
        sys,
        "argv",
        [
            "transcribe_media.py",
            "Vault/0. Inbox/test.mp4",
            "--no-timestamps",
            "--no-save",
            "--model",
            "gemini-4-hydrogen",
        ],
    ):
        main()

    captured = capsys.readouterr()
    assert "CLI transcript result" in captured.out
    mock_transcribe.assert_called_once_with(
        file_path="Vault/0. Inbox/test.mp4",
        output_note_path=None,
        include_timestamps=False,
        save_to_vault=False,
        model="gemini-4-hydrogen",
        custom_prompt=None,
    )
