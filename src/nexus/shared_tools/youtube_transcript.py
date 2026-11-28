"""
youtube_transcript.py — YouTube transcript downloader for Nexus.
Downloads and formats transcripts from YouTube videos into Obsidian-ready markdown notes
and caches captures in the active conversation cache (`cache://youtube/<video_id>`).
"""
import datetime
from pathlib import Path
import re
import sys
from typing import Optional

import requests
from youtube_transcript_api import YouTubeTranscriptApi

from nexus.core.constants import VAULT_PATH


def get_transcript(video_id: str):
    """Fetch transcript snippets for a YouTube video ID; route errors to stderr."""
    try:
        # The API in this version requires an instance and uses fetch()
        return YouTubeTranscriptApi().fetch(video_id)
    except Exception as e:
        print(f"Error fetching transcript: {e}", file=sys.stderr)
        return None


def extract_video_id(url: str) -> str:
    """Extract the 11-char video ID from standard watch, youtu.be, or shorts URLs."""
    cleaned = (url or "").strip()
    if "v=" in cleaned:
        return cleaned.split("v=", 1)[1].split("&", 1)[0]
    if "youtu.be/" in cleaned:
        return cleaned.split("youtu.be/", 1)[1].split("?", 1)[0].split("/", 1)[0]
    if "/shorts/" in cleaned:
        return cleaned.split("/shorts/", 1)[1].split("?", 1)[0].split("/", 1)[0]
    return cleaned


def get_video_title(video_id: str) -> str:
    """Fetch the sanitized YouTube video title, falling back to `video_id` on error."""
    try:
        response = requests.get(f"https://www.youtube.com/watch?v={video_id}", timeout=10)
        match = re.search(r"<title>(.*?)</title>", response.text)
        if match:
            title = match.group(1).replace(" - YouTube", "").strip()
            # Clean title for filename safety across Windows and POSIX filesystems
            return re.sub(r'[\\/*?:"<>|]', "", title) or video_id
    except Exception as e:
        print(f"Note: Could not fetch video title: {e}", file=sys.stderr)
    return video_id


def _resolve_vault_output_path(output_note_path: str) -> Path:
    """Validate that `output_note_path` stays strictly inside `VAULT_PATH.resolve()`."""
    clean = (output_note_path or "").strip().replace("\\", "/").lstrip("/")
    if clean.startswith("Vault/"):
        clean = clean[len("Vault/"):]
    if not clean:
        raise ValueError("Error: `output_note_path` cannot be empty.")
    if re.match(r"^[a-zA-Z]:", clean):
        raise ValueError(f"Error: Absolute paths are not allowed: '{output_note_path}'")

    resolved_vault = VAULT_PATH.resolve()
    candidate = (resolved_vault / clean).resolve()
    if not candidate.is_relative_to(resolved_vault):
        raise ValueError(f"Error: Refusing to write outside the Vault: '{output_note_path}'")
    return candidate


# Signature breakdown:
# - url_or_id: YouTube watch/short URL or bare video ID string.
# - save_to_inbox: bool = False writes a formatted Obsidian note to `Vault/0. Inbox/YouTube - <title>.md` (or `output_note_path`).
# - output_note_path: Optional[str] = None overrides the destination path inside `Vault/` (must stay inside `VAULT_PATH`).
# - Returns str: Formatted Markdown transcript prefixed with its `cache://youtube/<video_id>` handle (or an error string).
def fetch_youtube_transcript(
    url_or_id: str,
    save_to_inbox: bool = False,
    output_note_path: Optional[str] = None,
) -> str:
    """Download, cache (`cache://youtube/<id>`), and optionally save a YouTube transcript."""
    video_id = extract_video_id(url_or_id)
    if not video_id:
        return "Error: Could not parse a YouTube video ID from input."

    transcript = get_transcript(video_id)
    if not transcript:
        return f"Error: Failed to retrieve transcript for video ID '{video_id}'. Ensure subtitles are available."

    title = get_video_title(video_id)
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    transcript_lines = [str(getattr(snippet, "text", snippet)) for snippet in transcript]
    body_text = "\n".join(transcript_lines)

    markdown_note = (
        f"---\n"
        f'aliases: ["{title}"]\n'
        f"tags: [youtube, transcript, inbox]\n"
        f"type: capture\n"
        f"video_id: {video_id}\n"
        f"url: {watch_url}\n"
        f"captured_at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"**Source:** [YouTube]({watch_url})\n\n"
        f"## Transcript\n\n"
        f"{body_text}\n"
    )

    # Persist into the active conversation capture cache so `read_file("cache://...")` and `{{cache:...}}` work identically
    cache_key: Optional[str] = None
    try:
        from nexus.core.conversation_cache import get_active_conversation_id, put_capture

        cache_key = put_capture(
            conversation_id=get_active_conversation_id(),
            source_type="youtube",
            title=title,
            content=markdown_note,
            source_url=watch_url,
            cache_key=f"cache://youtube/{video_id}",
        )
    except Exception:
        cache_key = None

    saved_rel: Optional[str] = None
    if save_to_inbox or output_note_path:
        try:
            if output_note_path:
                out_file = _resolve_vault_output_path(output_note_path)
            else:
                out_file = (VAULT_PATH / "0. Inbox" / f"YouTube - {title}.md").resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(markdown_note, encoding="utf-8")
            saved_rel = f"Vault/{str(out_file.relative_to(VAULT_PATH.resolve())).replace(chr(92), '/')}"
        except Exception as exc:
            return f"Error saving YouTube transcript note: {exc}"

    header_bits: list[str] = []
    if cache_key:
        short_key = cache_key[len("cache://"):] if cache_key.startswith("cache://") else cache_key
        header_bits.append(f"- **Cache Key:** `{cache_key}` *(embed verbatim via `{{{{cache:{short_key}}}}}`)*")
    if saved_rel:
        header_bits.append(f"- **Saved Note:** `{saved_rel}`")

    prefix = ("\n".join(header_bits) + "\n\n") if header_bits else ""
    return f"{prefix}# {title}\n\n**Source:** [YouTube]({watch_url})\n\n## Transcript\n\n{body_text}"


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        print("Usage: python -m nexus.shared_tools.youtube_transcript <youtube_url_or_id> [output_file]")
        sys.exit(1)

    url_arg = sys.argv[1]
    out_arg = sys.argv[2] if len(sys.argv) > 2 else None
    result = fetch_youtube_transcript(url_arg, save_to_inbox=True, output_note_path=out_arg)
    if result.startswith("Error:"):
        print(result, file=sys.stderr)
        sys.exit(1)
    print(result)
