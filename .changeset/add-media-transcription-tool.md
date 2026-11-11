---
type: minor
---
### Added
- Created `src/nexus/shared_tools/transcribe_media.py` implementing verbatim multimodal audio (.mp3, .wav, .m4a, .aac, .ogg, .flac) and video (.mp4, .mov, .mkv, .avi) transcription via the Google GenAI File API (`gemini-3.8-flash` with 65,536 output tokens).
- Added support for files up to 2GB directly without local audio extraction, PyTorch, or FFmpeg dependencies on Windows.
- Added asynchronous polling loop for server-side transcode/index states (`PROCESSING` -> `ACTIVE`) with 10-minute timeout and automatic cloud file deletion (`client.files.delete` in `finally:` block).
- Added structured Obsidian Vault note persistence to `Vault/0. Inbox/Transcripts/` with YAML frontmatter (tags, source file, duration, file size, transcription model, timestamp).
- Added LangChain `@tool transcribe_media` in `src/nexus/shared_tools/shared.py` and bound it to `CORE_TOOLS` in `src/nexus/agent/graph.py` returning the full verbatim transcript.
- Added standalone CLI entrypoint (`python -m nexus.shared_tools.transcribe_media`).
- Authored 12 unit tests in `tests/test_transcribe_media.py` covering path resolution, MIME detection, API mocking, poll states, error handling, LangChain `@tool` execution, and CLI flags (212/212 total pytest suite passing).
