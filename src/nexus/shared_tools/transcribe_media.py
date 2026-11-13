"""
transcribe_media.py — Agentic multimodal audio and video transcription tool for Nexus.

Uses Google GenAI SDK (`google.genai`) and the Gemini File API (configured low-tier model e.g. `gemini-3.8-flash` or `gemini-4-hydrogen`)
to transcribe arbitrary audio (.mp3, .wav, .m4a, .aac, .flac, .ogg, .opus, .webm)
and video (.mp4, .mov, .mkv, .avi, .webm) files verbatim into properly punctuated,
timestamped text. Supports automatic note saving into the Obsidian Vault.
"""
import argparse
import datetime
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from google import genai
from google.genai import errors, types

from nexus.core.config import settings
from nexus.core.constants import PROJECT_ROOT, VAULT_PATH


# ── Supported File Format & MIME Mappings ────────────────────────────────────

# Audio container mappings: Maps common audio file extensions to standard IANA media MIME types.
# Gemini natively ingests AAC, FLAC, MP3, M4A, OGG/Opus, WAV, and WebM audio streams.
SUPPORTED_AUDIO_EXTENSIONS: Dict[str, str] = {
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".m4a": "audio/m4a",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/opus",
    ".webm": "audio/webm",
    ".wma": "audio/x-ms-wma",
}

# Video container mappings: Maps common video file extensions to standard IANA video MIME types.
# Gemini File API accepts MP4, MOV, MKV, AVI, and WebM containers directly without pre-extracting audio tracks.
SUPPORTED_VIDEO_EXTENSIONS: Dict[str, str] = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".wmv": "video/x-ms-wmv",
    ".flv": "video/x-flv",
    ".3gp": "video/3gpp",
}


# ── File Path & Container Resolution Helpers ─────────────────────────────────

# `file_path: str | Path` raw user or agent input string pointing to an audio or video file.
# `-> Tuple[Path, str, str]` returns (resolved_absolute_path, mime_type, media_category: "audio" | "video").
def resolve_media_file(file_path: Union[str, Path]) -> Tuple[Path, str, str]:
    """Resolve an audio or video file path against the Vault, Project Root, or filesystem.

    Checks existence in order:
      1. As an absolute or direct relative path from current working directory.
      2. Relative to the Obsidian Vault (`VAULT_PATH / file_path`).
      3. Relative to the Vault Inbox (`VAULT_PATH / "0. Inbox" / file_path`).

    Raises:
        FileNotFoundError: If the file cannot be located on disk.
        ValueError: If the file extension is not a supported audio or video format or file is 0 bytes.
    """
    raw_path = Path(file_path).expanduser()

    # Search candidates ordered by specificity
    candidates = [
        raw_path if raw_path.is_absolute() else (PROJECT_ROOT / raw_path).resolve(),
        (VAULT_PATH / raw_path).resolve(),
        (VAULT_PATH / "0. Inbox" / raw_path).resolve(),
    ]

    target: Optional[Path] = None
    for cand in candidates:
        if cand.exists() and cand.is_file():
            target = cand
            break

    if target is None:
        raise FileNotFoundError(
            f"Media file not found: '{file_path}'. Checked working directory, Vault root, and 'Vault/0. Inbox/'."
        )

    # Check non-empty
    size_bytes = target.stat().st_size
    if size_bytes == 0:
        raise ValueError(f"Media file is empty (0 bytes): '{target}'")

    # Extension and MIME resolution
    ext = target.suffix.lower()
    if ext in SUPPORTED_AUDIO_EXTENSIONS:
        return target, SUPPORTED_AUDIO_EXTENSIONS[ext], "audio"
    if ext in SUPPORTED_VIDEO_EXTENSIONS:
        return target, SUPPORTED_VIDEO_EXTENSIONS[ext], "video"

    # Fallback to standard Python mimetypes library for unmapped extensions
    guessed_type, _ = mimetypes.guess_type(str(target))
    if guessed_type:
        if guessed_type.startswith("audio/"):
            return target, guessed_type, "audio"
        if guessed_type.startswith("video/"):
            return target, guessed_type, "video"

    raise ValueError(
        f"Unsupported media format '{ext}' for file '{target.name}'. "
        f"Supported audio: {list(SUPPORTED_AUDIO_EXTENSIONS.keys())}; "
        f"Supported video: {list(SUPPORTED_VIDEO_EXTENSIONS.keys())}."
    )


# ── Core Transcription Engine ────────────────────────────────────────────────

# `file_path: str | Path` path to the audio or video file to transcribe.
# `output_note_path: Optional[str]` optional relative path in Vault to save Markdown transcript note.
# `include_timestamps: bool` whether to format transcript with [MM:SS] timestamps at speaker turns.
# `save_to_vault: bool` whether to persist the formatted transcript note into the Obsidian Vault.
# `model: Optional[str]` Gemini model override (defaults to configured `gemini_model_low` e.g. `gemini-3.8-flash`).
# `custom_prompt: Optional[str]` optional specialized instructions for the Gemini transcription model.
# `-> str` returns the complete verbatim transcript text.
def transcribe_media_file(
    file_path: Union[str, Path],
    output_note_path: Optional[str] = None,
    include_timestamps: bool = True,
    save_to_vault: bool = True,
    model: Optional[str] = None,
    custom_prompt: Optional[str] = None,
) -> str:
    """Transcribe an audio or video file verbatim using Google GenAI SDK and Gemini File API.

    Handles upload, async server-side processing for video/audio streams, full transcription
    generation up to 65,536 output tokens, automatic cloud artifact cleanup, and optional
    Obsidian Vault note archival with structured frontmatter.

    Returns the complete, unabridged transcript text.
    """
    # 1. Resolve API credentials from live settings
    api_key = settings.gemini_api_key or settings.google_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in .env. Cannot transcribe media.")

    # 2. Locate and validate media file
    resolved_file, mime_type, media_category = resolve_media_file(file_path)
    file_size_bytes = resolved_file.stat().st_size
    file_size_mb = round(file_size_bytes / (1024 * 1024), 2)

    # 3. Resolve active model identifier (defaults to fast low-tier model e.g. gemini-3.8-flash)
    effective_model = model or settings.gemini_model_low or "gemini-3.8-flash"
    if not effective_model.startswith("models/"):
        effective_model = f"models/{effective_model}"

    # 4. Instantiate Google GenAI client
    client = genai.Client(api_key=api_key)

    uploaded_file: Optional[types.File] = None
    try:
        # ── Phase A: Upload media to Gemini File API ──────────────────────────
        # UploadFileConfig sets MIME hint and display name so the backend selects proper audio/video demuxers.
        upload_config = types.UploadFileConfig(
            mime_type=mime_type,
            display_name=resolved_file.name,
        )
        uploaded_file = client.files.upload(
            file=resolved_file,
            config=upload_config,
        )

        # ── Phase B: Poll file processing status ──────────────────────────────
        # Video files and larger audio containers enter `PROCESSING` state while Google transcode servers
        # extract audio tracks, build index tables, and generate frame embeddings.
        poll_interval_sec = 2.0
        max_poll_seconds = 600.0  # 10 minutes timeout for multi-hundred megabyte video files
        elapsed = 0.0

        while uploaded_file.state == types.FileState.PROCESSING:
            if elapsed >= max_poll_seconds:
                raise TimeoutError(
                    f"Gemini server-side media processing timed out after {int(elapsed)}s for '{resolved_file.name}'."
                )
            time.sleep(poll_interval_sec)
            elapsed += poll_interval_sec
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state == types.FileState.FAILED:
            err = getattr(uploaded_file, "error", None) or "Unknown processing error"
            raise RuntimeError(f"Gemini media processing failed for '{resolved_file.name}': {err}")

        # Extract duration string if available from server video/audio metadata
        duration_str = "Unknown"
        if uploaded_file.video_metadata and uploaded_file.video_metadata.end_offset:
            duration_str = str(uploaded_file.video_metadata.end_offset)

        # ── Phase C: Prompt Formulation ───────────────────────────────────────
        if custom_prompt:
            prompt_instruction = custom_prompt.strip()
        elif include_timestamps:
            prompt_instruction = (
                "You are an expert audio and video transcriber. Transcribe the spoken audio from this media file "
                "verbatim into clean, accurate, properly punctuated text.\n\n"
                "Strict Directives:\n"
                "1. Include periodic timestamps (e.g., [MM:SS] or [HH:MM:SS]) at natural speaking transitions, "
                "speaker changes, or approximately every 30 to 60 seconds.\n"
                "2. Identify distinct speakers where discernible (e.g., 'Speaker 1:', 'Speaker 2:', or by name "
                "if names are introduced in the dialogue).\n"
                "3. Transcribe VERBATIM. Do NOT summarize, condense, synthesize, or omit any spoken words.\n"
                "4. Output ONLY the raw transcript text. Do NOT include any introductory pleasantries, explanations, "
                "preambles, or conversational commentary."
            )
        else:
            prompt_instruction = (
                "You are an expert audio and video transcriber. Transcribe all spoken audio from this media file "
                "verbatim into clean, accurate, properly punctuated text.\n\n"
                "Strict Directives:\n"
                "1. Identify distinct speakers where discernible (e.g., 'Speaker 1:', 'Speaker 2:', or by name "
                "if names are introduced in the dialogue).\n"
                "2. Transcribe VERBATIM. Do NOT summarize, condense, synthesize, or omit any spoken words.\n"
                "3. Output ONLY the raw transcript text. Do NOT include any introductory pleasantries, explanations, "
                "preambles, or conversational commentary."
            )

        # ── Phase D: Generate Verbatim Transcript ─────────────────────────────
        # max_output_tokens=65536 unlocks Gemini 4 Hydrogen's full output token window for long multi-hour recordings.
        gen_config = types.GenerateContentConfig(
            max_output_tokens=65536,
            temperature=0.0,  # Zero temperature for deterministic, hallucination-resistant transcription
            http_options=types.HttpOptions(timeout=600000),  # 10 minutes HTTP timeout
        )

        response = client.models.generate_content(
            model=effective_model,
            contents=[uploaded_file, prompt_instruction],
            config=gen_config,
        )

        raw_transcript = (response.text or "").strip()
        if not raw_transcript:
            raise RuntimeError(f"Gemini returned an empty transcript for '{resolved_file.name}'.")

        # ── Phase E: Optional Obsidian Vault Note Persistence ─────────────────
        saved_note_rel: Optional[str] = None
        if save_to_vault:
            # Determine destination note path in Vault
            if output_note_path:
                note_rel = output_note_path.strip().replace(chr(92), "/")
                if not note_rel.lower().endswith(".md"):
                    note_rel = f"{note_rel}.md"
                target_note = (VAULT_PATH / note_rel).resolve()
            else:
                # Default storage: Vault/0. Inbox/Transcripts/<filename>.md
                transcripts_dir = VAULT_PATH / "0. Inbox" / "Transcripts"
                transcripts_dir.mkdir(parents=True, exist_ok=True)
                clean_stem = resolved_file.stem
                target_note = transcripts_dir / f"Transcript — {clean_stem}.md"

            # Ensure parent directories exist
            target_note.parent.mkdir(parents=True, exist_ok=True)

            # Security check: must reside inside VAULT_PATH
            try:
                rel_to_vault = target_note.relative_to(VAULT_PATH)
                saved_note_rel = f"Vault/{str(rel_to_vault).replace(chr(92), '/')}"
            except ValueError:
                # If path escapes Vault, fall back to safe Inbox path
                target_note = (
                    VAULT_PATH / "0. Inbox" / "Transcripts" / f"Transcript — {resolved_file.stem}.md"
                )
                target_note.parent.mkdir(parents=True, exist_ok=True)
                saved_note_rel = f"Vault/0. Inbox/Transcripts/Transcript — {resolved_file.stem}.md"

            # Relative path of source file for frontmatter link
            try:
                source_display = str(resolved_file.relative_to(PROJECT_ROOT)).replace(chr(92), "/")
            except ValueError:
                source_display = resolved_file.name

            # Format structured Obsidian note with frontmatter metadata
            now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            note_content = (
                "---\n"
                f"aliases:\n"
                f"  - Transcript — {resolved_file.stem}\n"
                f"tags:\n"
                f"  - transcript\n"
                f"  - {media_category}\n"
                f"  - media\n"
                f"  - capture\n"
                f"type: transcript\n"
                f"source_file: \"{source_display}\"\n"
                f"media_type: \"{mime_type}\"\n"
                f"file_size_mb: {file_size_mb}\n"
                f"duration: \"{duration_str}\"\n"
                f"transcribed_at: {now_iso}\n"
                f"model: \"{effective_model}\"\n"
                "---\n\n"
                f"# Transcript — {resolved_file.stem}\n\n"
                f"**Source:** `{source_display}` ({file_size_mb} MB)  \n"
                f"**Transcribed:** {now_iso} via `{effective_model}`  \n"
                f"**Duration:** {duration_str}\n\n"
                "---\n\n"
                "## Verbatim Transcript\n\n"
                f"{raw_transcript}\n"
            )

            with open(target_note, "w", encoding="utf-8") as f:
                f.write(note_content)

        # Append optional receipt line pointing to the saved note so caller knows where it lives on disk
        if saved_note_rel:
            return f"{raw_transcript}\n\n---\n*Saved full transcript note to `{saved_note_rel}`.*"

        return raw_transcript

    finally:
        # ── Phase F: Cloud Artifact Cleanup ───────────────────────────────────
        # Always delete the uploaded file from Google AI Studio file storage to prevent orphaned cloud bloat.
        if uploaded_file and uploaded_file.name:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                # Suppress non-fatal deletion errors (e.g. transient network timeouts on cleanup)
                pass


# ── Command Line Interface (CLI) Entrypoint ──────────────────────────────────

def main() -> None:
    """CLI entrypoint for standalone media transcription."""
    parser = argparse.ArgumentParser(
        description="Transcribe audio or video files into verbatim text using Gemini File API."
    )
    parser.add_argument(
        "file_path",
        help="Path to the audio or video file (e.g. 'Vault/0. Inbox/meeting.mp4' or 'recording.mp3')",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_note",
        default=None,
        help="Optional relative path in Vault to save Markdown transcript note (e.g. '0. Inbox/MyTranscript.md')",
    )
    parser.add_argument(
        "--no-timestamps",
        action="store_true",
        help="Omit periodic [MM:SS] timestamps from the output transcript.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Skip saving the transcript note to the Obsidian Vault; prints transcript to stdout only.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Gemini model override (e.g. 'gemini-4-hydrogen'). Defaults to configured gemini_model_low.",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Custom prompt instructions for the Gemini transcription model.",
    )

    args = parser.parse_args()

    try:
        sys.stderr.write(f"Transcribing media file '{args.file_path}' via Gemini API...\n")
        transcript = transcribe_media_file(
            file_path=args.file_path,
            output_note_path=args.output_note,
            include_timestamps=not args.no_timestamps,
            save_to_vault=not args.no_save,
            model=args.model,
            custom_prompt=args.prompt,
        )
        print(transcript)
    except Exception as exc:
        sys.stderr.write(f"Error transcribing media file: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
