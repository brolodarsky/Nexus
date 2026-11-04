---
type: minor
---

### Added
- **Resizable Conversation History Sidebar (`gui/src/components/chat/ChatSidebar.tsx`):** Added a draggable right-border resize handle with native pointer coordinate tracking (`PointerEvent`), min/max boundary clamping (`200px` to `640px`), double-click reset to default width (`256px`), and smooth transition prevention during active drag.
- **Persistent Sidebar Width Storage (`gui/src/components/chat/types.ts`):** Added `CHAT_SIDEBAR_WIDTH_KEY` (`nexus_chat_sidebar_width`) to save custom sidebar width in `localStorage`, maintaining user sizing across tab navigation and reloads.

### Changed
- **Full-Width Conversation Titles with Floating Hover Actions (`gui/src/components/chat/ChatSidebar.tsx`):** Restructured conversation history items so titles take up 100% of available row width instead of reserving 70px of space for hidden action buttons. Action buttons (rename, AI auto-title, delete) now float seamlessly over the right edge on hover inside a backdrop-blurred pill container, avoiding text truncation.
