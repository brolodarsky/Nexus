---
type: patch
---
### Fixed
- **Zero-Lag Typing & Subtree Memoization Across Nexus GUI (`gui/src/app/chat/page.tsx`, `gui/src/components/chat/`, `gui/src/components/MarkdownMessage.tsx` & `gui/src/app/tools/page.tsx`):**
  - Isolated active keystroke buffers inside `ChatInputBar.tsx` (`localInput` synchronized via render-phase `inputSyncId` tracking) and `ResumeMarkdownEditor` (`gui/src/app/tools/page.tsx`), preventing per-character root page re-renders when typing prompts or editing resume markdown.
  - Wrapped `MarkdownMessage`, `ChatMessageThread`, `ChatMessageItem`, `ChatSidebar`, `ChatHeader`, `BlackboardDrawer`, `ThinkingPanel`, and `AgentGraphView` in `React.memo`, hoisted `REMARK_PLUGINS` (`[remarkGfm]`) and `MARKDOWN_COMPONENTS` to module scope, and memoized `preprocessObsidianMarkdown()` so historical chat messages never re-parse Markdown ASTs during typing.
  - Replaced post-render `useEffect` textarea height recalculations with inline event-handler resizing (`syncTextareaHeight`) to eliminate forced synchronous DOM reflows, debounced `localStorage` draft persistence (`persistDrafts`) by 300ms with `beforeunload`/unmount flush guarantees, added `useDeferredValue` to search inputs in `/audit`, `/tools`, and `PinNoteModal.tsx`, and scoped `.glass-card` CSS transitions in `gui/src/app/globals.css` to non-layout properties.

