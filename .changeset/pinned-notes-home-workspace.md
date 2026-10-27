---
type: minor
---
### Added
- **Pinned Notes Home Workspace (`gui/src/app/page.tsx`)**: Replaced the legacy Mission Control and Agent Fleet dashboard with a personal, distraction-free Pinned Notes workspace. Supports both a multi-column Cards Grid view and an IDE-style Split Workspace Reader with full Markdown rendering, code blocks, checklists, and Obsidian wiki-links.
- **Pin / Unpin Note Modal**: Added a searchable, keyboard-friendly dialog enabling one-click pinning across all 300+ Vault notes with category chips for top-level folders, live search, and pin/unpin toggles.
- **Vault Flat Notes API (`GET /api/vault/notes`)**: Added FastAPI endpoint and TypeScript client wrapper `getAllVaultNotes()` returning sorted markdown note summaries (title, path, folder, size, mtime) for rapid client-side search.
- **Bi-directional Vault Pinning (`gui/src/app/vault/page.tsx`)**: Added a direct "Pin to Home" toggle to the Brain Explorer note header, and support for the `?note=...` query parameter to link straight from pinned cards into Brain Explorer.

### Changed
- **Home Navigation & Layout**: Renamed the primary navigation destination from "Mission Control" to "Home" (`📌`) across `Sidebar.tsx` and updated page metadata in `layout.tsx`.
