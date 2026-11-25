---
type: patch
---

Clean up assistant message header pills in `gui/src/components/chat/ChatMessageItem.tsx`: hide the redundant default `"Head Agent"` badge and legacy `confidence` (`100%`) percentage on regular chat turns (while preserving synthetic `branch_context` / `branch_merge` badges), and replace the emoji-prefixed slug model pill with a clean uppercase, no-emoji badge powered by `formatModelBadgeLabel` in `gui/src/components/chat/types.ts`.
