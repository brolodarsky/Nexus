---
type: patch
---

### Added
- **Chat Header Three-Dots Dropdown Menu (`ChatHeader.tsx`, `page.tsx`):** Folded the inline rename and AI auto-titling buttons into a unified three-dots (`•••`) menu button in the header bar. Added a destructive "Delete conversation" action with browser confirmation dialog and red styling. Added an accessible popover dropdown with outside-click and Escape key dismissal, plus an inline background "Titling..." badge to provide instant visual feedback during AI title generation.

### Changed & Cleaned Up
- **Sidepanel Hover Toolbar & Dead Code Removal (`ChatSidebar.tsx`, `page.tsx`):** Excised the hover action toolbar containing the sidepanel's edit (pencil), auto-title (sparkle), and delete (cross) buttons. In accordance with zero-vestige engineering standards, completely pruned obsolete inline editing states (`editingId`, `editTitle`, `editInputRef`, `handleStartEdit`, `handleSaveEdit`, `handleCancelEdit`) and unused props (`onDeleteChat`, `onAutoGenerateTitle`, `onUpdateTitle`) from `ChatSidebar`. Unlocked 100% full horizontal row width for conversation titles without hover popovers obscuring text or causing accidental taps on touch screens.
