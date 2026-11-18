---
type: minor
---
### Added
- **Read-Only Conversation Cache Endpoints (`src/nexus/api/routers/agents.py`):** Added `GET /api/agents/ask/conversations/{conversation_id}/captures` (lightweight metadata list omitting `content`) and `GET /api/agents/ask/conversations/{conversation_id}/captures/item?key=...` (full verbatim capture detail with `400` blank-key validation and `404` per-conversation isolation).
- **Frontend Cache API Client (`gui/src/lib/api/agents.ts`):** Added `ConversationCaptureSummary`, `ConversationCaptureDetail`, `ConversationCapturesListResponse`, `getConversationCaptures()`, and `getConversationCaptureItem()`.
- **Chat Header Cache Button & Wide Centered Modal (`gui/src/components/chat/ChatHeader.tsx`, `gui/src/components/chat/ConversationCacheModal.tsx`, `gui/src/app/chat/page.tsx`):** Added a right-side `Cache` button with a live per-conversation capture count badge (refreshing on thread switches, mid-turn external capture tool results, turn completions, and Stop & Revert) and a read-only two-pane `ConversationCacheModal` rendering cached captures via `MarkdownMessage`, with keyboard `Escape` isolation during active streaming turns.
- **API Regression Tests (`tests/test_conversation_cache.py`):** Added `test_http_conversation_captures_list_item_isolation_and_validation()` verifying empty lists, metadata-only list responses, verbatim item reads, cross-conversation isolation, and error status codes.
