---
type: minor
---
### Added
- Enhanced `src/nexus/interfaces/telegram.py` with automatic 4,000-character message chunking (`_split_telegram_message`), non-blocking `asyncio.to_thread` execution with a live typing heartbeat (`_keep_typing`), per-chat conversation thread management (`/new`), and remote HITL queue commands (`/pending`, `/approve <id|all>`, `/reject <id>`).
