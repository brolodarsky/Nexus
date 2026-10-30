---
type: minor
---

### Added
- **Collapsible Nexus Message Bar (`gui/src/components/chat/ChatInputBar.tsx`):** Added collapsible state to the chat message composer bar. When minimized, collapses into a sleek, compact bottom rail displaying unsubmitted draft previews, the active model capability badge, and a click/keyboard expand toggle.
- **Header Toggle Control (`gui/src/components/chat/ChatHeader.tsx`):** Added a dedicated "Message Bar" collapse/expand toggle button in the top navigation header adjacent to the Subagent Board trigger.
- **Global '/' Keyboard Shortcut (`gui/src/app/chat/page.tsx`):** Added a global keyboard shortcut listening for `/` when viewing the conversation thread to automatically expand the message bar and focus the multiline textarea.
- **Persistent Storage (`gui/src/components/chat/types.ts`):** Added `CHAT_INPUT_COLLAPSED_KEY` (`nexus_chat_input_collapsed`) to persist the message bar's collapsed/expanded preference across page refreshes and tab navigations.
- **Auto-Expansion on Starter Prompts (`gui/src/app/chat/page.tsx`):** Selecting any empty-state starter suggestion prompt automatically expands the message bar and pre-fills the textarea.
