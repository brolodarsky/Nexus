---
type: patch
---
### Fixed
- **Subtree Max-Recency Sorting & Optimistic Send Bump in Chat Sidebar (`gui/src/components/chat/ChatSidebar.tsx`, `gui/src/app/chat/page.tsx`):**
  - Added safe ISO-8601 epoch millisecond parsing (`parseTimestampMs`) and memoized `sortedConversations` in `ChatSidebar.tsx` so both the collapsed rail and the expanded tree operate on consistent `last_updated DESC` ordering.
  - Updated `treeRows` in `ChatSidebar.tsx` to compute each conversation's subtree maximum `last_updated` (with cycle-safe DFS memoization) and sort both root threads and sibling branches descending by subtree recency, preventing active child branches off older parent threads from being buried down the sidebar.
  - Added an optimistic `last_updated` bump and index-0 promotion on `conversations` inside `handleSubmit` (`gui/src/app/chat/page.tsx`) for existing threads so sending a message immediately moves the active thread (or its parent tree) to the top before the turn finishes.

