---
type: patch
---

### Fixed
- **Chat & External Note Links Opened in New Browser Tabs (`gui/src/components/MarkdownMessage.tsx`, `gui/src/components/chat/ChatMessageItem.tsx`, `gui/src/components/chat/BlackboardDrawer.tsx`, `gui/src/components/AgentTraceVisualizer.tsx`):** Resolved an issue where clicking Obsidian wiki-links (`[[Note]]`, `[[Note|Alias]]`) or backticked note titles (`` `Note.md` ``) rendered within chat message bubbles, subagent blackboard bulletins, or thinking trace panels performed Next.js in-app client-side navigation within the same window, abruptly replacing the active `/chat` workspace and interrupting ongoing SSE streams, conversation focus, or prompt drafts.
  - Enhanced `MarkdownMessage` and `VaultNotePill` to accept an `openInNewTab` policy via context and props (defaulting to `true` whenever an in-place `onWikiLinkClick` handler is not supplied).
  - Wired `target="_blank"` and `rel="noopener noreferrer"` attributes onto the underlying Next.js `<Link>` component for safe, isolated multi-tab browsing.
  - Added an external link glyph indicator (`↗`) with hover transition and clear tooltip (`Vault Note: <Target> (Click to open in new tab)`) to visually signal multi-tab navigation to the user.
  - Extended `ChatMessageItem` user message prompt rendering to use `MarkdownMessage` with preserved whitespace (`whitespace-pre-wrap`), enabling users to click note links referenced in their own prompt history into new tabs.
  - Intercepted standard Markdown links targeting `.md` files or `/vault?note=...` in `MARKDOWN_COMPONENTS.a`, automatically converting relative paths (e.g. `[Tasks](Vault/Tasks.md)` or `[Log](Log.md)`) into `VaultNotePill` badges that open into new tabs instead of failing with `/chat/*.md` 404 errors.
  - Sanitized target path resolution by cleanly stripping heading anchors (`#Heading`) from query parameters (`/vault?note=<baseTarget>`) so anchor links navigate directly to the target markdown note file.
- **Deep-Linked URL Search Parameter Sanitization (`gui/src/app/vault/page.tsx`):** Updated the initial URL query param listener on mount in the Vault explorer to strip heading anchors and automatically normalize `.md` extensions on linked target notes, preventing file resolution errors when opening notes with section anchors from external tabs.
