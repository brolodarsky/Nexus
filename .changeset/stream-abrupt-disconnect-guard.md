---
type: patch
---
### Fixed
- **SSE Stream Disconnect Recovery:** Hardened `gui/src/lib/api/stream.ts` to detect abrupt HTTP socket closures before a terminal `done` or `error` packet is emitted (e.g. backend reloads or network drops). Previously, an abrupt closure exited the read loop silently, leaving the chat UI permanently hung in a loading state. Now, it flushes trailing buffer data and invokes `callbacks.onError()` to cleanly stop the spinner and notify the user.
