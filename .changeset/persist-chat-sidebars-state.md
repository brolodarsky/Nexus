---
type: patch
---

### Added
- Persisted client storage keys `CHAT_SIDEBAR_COLLAPSED_KEY` and `CHAT_BOARD_OPEN_KEY` in `gui/src/components/chat/types.ts`.

### Changed
- Refactored `gui/src/app/chat/page.tsx` to restore and sync left conversation history menu (`ChatSidebar`) and right situational feed drawer (`BlackboardDrawer`) open/collapsed states via `localStorage`, ensuring user sidebar choices persist across Nexus page navigations.
