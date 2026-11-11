---
type: minor
---
### Added
- Built the bidirectional Telegram Mobile Voice & Notification Bridge (`src/nexus/shared_tools/telegram_bridge.py`) supporting asynchronous long-polling queue draining (`getUpdates`), Pixel Gboard STT text, Telegram microphone `.ogg` Opus voice note transcription via Gemini Flash multimodal audio (with OpenAI Whisper fallback), camera photo ingestion, automatic first-user owner enrollment, `📱` conversation creation in `chats.db` with swipe-to-reply thread continuation, and structured HITL staging ping-backs.
- Added `@tool send_telegram_notification` in `src/nexus/shared_tools/shared.py` and bound it to `CORE_TOOLS` in `src/nexus/agent/graph.py` so `NexusAgent` can send proactive push notifications to the user's phone.
- Wired automatic background poller startup into FastAPI's `lifespan` in `src/nexus/api/main.py` (`/api/health` and `/api/telegram/status`), `start.ps1`, and Windows logon (`--install-autostart`) with cross-process `FileLock` coordination.
- Added 6 unit and integration tests in `tests/test_telegram_bridge.py`.
