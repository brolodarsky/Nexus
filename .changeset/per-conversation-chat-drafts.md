---
type: patch
---

### Added
- **Per-Conversation Draft Persistence (`gui/src/components/chat/types.ts`):** Added `CHAT_DRAFTS_STORAGE_KEY` (`nexus_chat_drafts`), `DRAFT_NEW_KEY` (`_new`), and `loadPersistedDrafts` / `persistDrafts` helpers with automatic backward-compatibility migration for legacy single-draft storage.
- **Sidebar Draft Indicators (`gui/src/components/chat/ChatSidebar.tsx`):** Added visual `Draft` indicator pills next to conversation titles and on the "New Chat" button when unsubmitted drafts are saved, as well as cyan dot indicators on collapsed sidebar icons.

### Fixed
- **Per-Conversation Input Isolation (`gui/src/app/chat/page.tsx`):** Fixed chat input retaining the same global draft across conversation switches. Switching conversations now seamlessly saves the outgoing thread's draft, clears or restores the target thread's draft, preserves the "New Chat" draft independently, and clears drafts upon successful message submission or thread deletion.
