---
type: patch
---

### Changed
- **Shared Chat Model Selector Dropdown (`gui/src/components/chat/ModelSelectorDropdown.tsx`, `ChatSidebar.tsx`, `ChatInputBar.tsx`, `gui/src/app/chat/page.tsx`):**
  - Extracted the per-turn model selector dropdown from `ChatInputBar.tsx` into a reusable `ModelSelectorDropdown` component (exported via `gui/src/components/chat/index.ts`) supporting `placement="up" | "down"` and `fullWidth`.
  - Replaced the 2-column quick preset button grid in `ChatSidebar.tsx` with `<ModelSelectorDropdown placement="down" fullWidth ... />` and wired both `ChatSidebar` and `ChatInputBar` to the same lifted `modelOptions`, `selectedModelTier`, and `handleSelectModelTier` state in `ChatPage`.
  - Removed vestigial inline dropdown state/JSX from `ChatInputBar.tsx`, removed the 2-column preset grid from `ChatSidebar.tsx`, and pruned the unused `initialTier` parameter from `ChatSidebarProps.onNewChat` and `handleNewChat`.
