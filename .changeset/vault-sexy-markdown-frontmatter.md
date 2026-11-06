---
type: minor
---

### Added
- **Auto-Collapsing YAML Frontmatter Component (`gui/src/components/NoteFrontmatter.tsx`):**
  - Built a zero-dependency Obsidian frontmatter parser supporting strings, numbers, booleans, inline flow arrays (`[a, b]`), indented block lists (`- item`), and unquoted scalar fields.
  - Implemented an auto-collapsed metadata panel with a sleek, compact summary bar (showing note type, tags preview, last updated timestamp, and field counts).
  - Built an expanded inspector featuring tabs for a structured property definition table and a raw YAML syntax viewer with a one-click clipboard copy action.

### Changed
- **Rich Markdown Reading Surface in Vault Explorer (`gui/src/app/vault/page.tsx`):**
  - Replaced the plaintext `<pre>` block with a glassmorphic reader surface powered by `MarkdownMessage`.
  - Integrated auto-collapsed `NoteFrontmatter` at the top of notes containing YAML fences, resetting to collapsed on every note selection.
  - Added an interactive action toolbar with folder breadcrumbs, reading time and word count metrics, a raw/preview mode toggle (`Preview` vs `Raw`), one-click note markdown copy, and in-place Obsidian `[[Wiki-Link]]` switching.
- **Obsidian Callouts & Deep-Linking (`gui/src/components/MarkdownMessage.tsx`):**
  - Added support for Obsidian callout syntax (`> [!NOTE]`, `> [!TIP]`, `> [!WARNING]`, `> [!IMPORTANT]`, `> [!CAUTION]`, etc.) with themed accent borders, translucent backgrounds, and custom icons.
  - Connected `WikiLinkContext` so clicking note pills switches the active note in-place when inside the Vault Explorer or navigates via Next.js client router deep-linking from chat or other workspaces.
  - Refined task list item alignment so checkboxes (`- [ ]`, `- [x]`) do not duplicate bullet points.
- **Cleaned Home Page Pinned Notes Reader & Grid Cards (`gui/src/components/home/`):**
  - Updated `PinnedNotesReader.tsx` and `PinnedNoteCard.tsx` to strip tool header wrappers and auto-collapse YAML frontmatter, revealing note bodies cleanly.
