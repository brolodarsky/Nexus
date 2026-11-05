---
type: patch
---

### Fixed
- **Chat Page Initial Active Conversation Restoration (`gui/src/app/chat/page.tsx`):** Fixed race condition where active conversation state initialized to `null` on mount prematurely wrote `"__new__"` to `ACTIVE_CONV_STORAGE_KEY` before conversations resolved from SQLite, causing the chat page to always default to an empty screen rather than loading the most recent conversation (`convos[0]`). Guarded persistence effect with `isInitialLoadDoneRef`, ensured `savedActiveConv` is restored when valid, and defaulted to `convos[0].id` when refreshed or returned to.
- **Agent Responses Auto-Refresh & SSE Stream Keep-Alive (`src/nexus/api/routers/agents.py`, `gui/src/lib/api/stream.ts`, `gui/src/app/chat/page.tsx`):**
  - Upgraded `/api/agents/ask/stream` from blocking `queue.Queue.get(timeout=0.1)` to non-blocking `get_nowait()` with `await asyncio.sleep(0.05)`, and added RFC 8895 SSE keep-alive comment pings (`: ping\n\n`) every 10 seconds of idle wait to prevent proxy, browser Fetch, and OS TCP socket drops during long LLM/subagent turns.
  - Added `activeStreamConvIdRef` in `ChatPage` to prevent `useEffect([activeConvId])` from wiping messages or prematurely setting `loading = false` when an active SSE stream initiates a new conversation thread.
  - Added background reconciliation in `onError` and `visibilitychange` that polls/syncs `getChatHistory(targetConvId)` directly against SQLite `chats.db`, automatically recovering and displaying agent responses even if network hiccups or browser tab backgrounding severed the streaming transport.

