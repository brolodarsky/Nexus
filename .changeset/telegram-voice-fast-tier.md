---
type: patch
---
### Fixed
- Fixed Telegram Mobile Bridge default model tier: changed `telegram_default_tier` in `src/nexus/core/config.py` from `"strong"` to `"low"`, enabling sub-second mobile turns on `gemini-3.8-flash` with >99% cost reduction while preserving `/strong` or `/argon` per-turn overrides.
- Enhanced voice note and audio memo transcription in `src/nexus/shared_tools/telegram_bridge.py`: prioritized ultra-fast OpenAI Whisper API (`whisper-1`, ~1.2s latency) with automatic fallback to Gemini Flash multimodal audio (`gemini-3.8-flash`), and normalized audio extensions and clean MIME types.
- Expanded Telegram media ingestion to recognize audio payloads across native voice notes (`message.voice`), audio tracks (`message.audio`), circular video notes (`message.video_note`), and audio files uploaded as documents (`message.document`).
- Extended background `'typing...'` status heartbeat across the entire turn lifecycle (audio download, speech-to-text transcription, and agent reasoning) to eliminate silent timeouts on mobile devices.
- Hardened Loguru console logging on Windows in `src/nexus/core/logger.py` with UTF-8 stream reconfiguration to prevent `charmap` `UnicodeEncodeError` exceptions on emoji log messages.
