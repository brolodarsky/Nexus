---
type: minor
---
### Added
- Created modular Chat UI subcomponents under `gui/src/components/chat/` (`ChatSidebar.tsx`, `ChatHeader.tsx`, `ChatMessageThread.tsx`, `ChatMessageItem.tsx`, `ChatInputBar.tsx`, `BlackboardDrawer.tsx`, `types.ts`, and `index.ts`).
- Created the `/chat` route orchestrator in `gui/src/app/chat/page.tsx`.

### Changed
- Renamed the Next.js conversational route from `/ask` ("Ask Brain") to `/chat` ("Chat") in `gui/src/components/Sidebar.tsx` and across GUI components.
- Decomposed the 932-line monolithic chat page into focused, single-responsibility subcomponents and eliminated synchronous `setState`-in-effect lint errors.

### Removed
- Removed the legacy monolithic `gui/src/app/ask/page.tsx` route directory.

