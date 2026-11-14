---
type: patch
---

### Added
- **Click-to-Copy Conversation, Thread & Message IDs Under Chat UI Kebab Menus (`gui/src/components/chat/`):**
  - Added shared `formatShortId()` and LAN/Tailscale-safe `copyTextToClipboard()` (Async Clipboard API with offscreen `<textarea>` `execCommand("copy")` fallback for non-HTTPS origins) in `gui/src/components/chat/types.ts` (re-exported via `index.ts`).
  - Added a click-to-copy `Conv ID: <short>…` item (full UUID tooltip + transient `Copied!` feedback) to the existing header three-dots menu in `ChatHeader.tsx`.
  - Added a per-row kebab (`⋮`) menu to every conversation and child branch row in `ChatSidebar.tsx` displaying click-to-copy `Conv ID` / `Thread ID` (and `Parent ID` on child branches), moving row `overflow-hidden` to the title wrapper and stopping click propagation so copying never switches threads.
  - Added a per-message kebab (`⋮`) menu to `ChatMessageItem.tsx` (receiving `conversationId` from `ChatMessageThread.tsx`) with upward popover positioning and click-to-copy `Thread ID: #<id>` (or `turn-<N>` fallback) and `Conv ID: <short>…`.
