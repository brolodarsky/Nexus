---
type: minor
---
### Added
- **Mobile Bottom Navigation Bar (`Sidebar.tsx` & `layout.tsx`):** Added a fixed `h-16` bottom navigation bar (`md:hidden`) with backdrop blur, iOS safe-area bottom inset padding, and compact icon+label tabs (`Home`, `Chat`, `Vault`, `Tools`, `HITL`, `Audit`), plus `pb-16 md:pb-0` on `<main>` while keeping the desktop collapsible `Sidebar` (`hidden md:flex`) 100% unchanged.
- **Mobile Slide-Over Conversation & Blackboard Drawers (`ChatHeader.tsx`, `ChatSidebar.tsx`, `BlackboardDrawer.tsx`, `chat/page.tsx`):** Added a mobile hamburger/threads trigger in `ChatHeader` that opens `ChatSidebar` as a slide-over overlay drawer with backdrop on `< 768px` viewports, defaulted the Blackboard drawer to closed on mobile (and rendered it as a slide-over overlay when opened), and set `ChatInputBar` to `text-base` (`16px`) on mobile to prevent iOS Safari viewport auto-zoom.

### Changed
- **Mobile-Responsive HITL Diff Reviewer (`hitl/page.tsx`) & Workspaces (`vault/page.tsx`, `audit/page.tsx`, `tools/page.tsx`, `PinnedNotesReader.tsx`):** Stacked HITL, Vault Explorer, and Audit Log queues vertically on mobile (`flex-col md:flex-row`), dynamically configured Monaco `DiffEditor` with `renderSideBySide: false` (inline unified diff) when viewport width `< 768px`, and made Approve / Reject / Rebase controls thumb-friendly on mobile screens.
