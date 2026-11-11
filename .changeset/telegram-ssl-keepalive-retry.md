---
type: patch
---
### Fixed
- Fixed Telegram voice note download SSL handshake timeout (`_ssl.c:993`) by implementing a thread-safe singleton connection pool (`get_telegram_http_client` / `close_telegram_http_client`) with HTTP keepalive, connection limits, and granular timeouts in `src/nexus/shared_tools/telegram_bridge.py`.
- Reused established keepalive sockets across `download_telegram_file`, `send_chat_action`, `send_telegram_message`, and `verify_telegram_bot`, eliminating repeated TLS 1.3 renegotiation on Windows and dropping subsequent request latency from ~900ms to ~90ms.
- Added exponential backoff retry logic (up to 3 attempts with 0.5s base delay) in `download_telegram_file` for transient network errors, timeouts, and SSL handshake glitches (`TimeoutException`, `NetworkError`, `SSLError`, `ConnectionError`).
- Added retry resilience to `send_telegram_message` for outbound message delivery during transient connection blips.
- Differentiated voice note download errors from transcription errors in logs and Telegram ping-back responses (`❌ *Voice Download Error:*` vs. `❌ *Voice Transcription Error:*`) with full exception tracebacks in `logger.exception`.
- Added 4 unit tests in `tests/test_telegram_bridge.py` verifying connection pool singleton lifecycle, transient SSL timeout retries, retry exhaustion handling, and error differentiation.
