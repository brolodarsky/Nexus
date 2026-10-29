---
type: minor
---
### Added
- Created modular Home UI subcomponents under `gui/src/components/home/`:
  - `HomeHeader.tsx`: Title, active pinned note count badge, refresh disk content trigger, layout view mode segmented switcher (Grid vs Split Reader), and "+ Pin Note" launcher.
  - `HomeEmptyState.tsx`: Onboarding empty state container with quick-pin suggestions for default notes (`Tasks.md`, `Goals.md`) and Vault browse button.
  - `PinnedNoteCard.tsx`: Individual pinned note card in Grid view with header controls (re-ordering arrows, copy markdown with checkmark feedback, open in Vault explorer link, height expand/collapse toggle, unpin button), loading/error states, and word metrics footer.
  - `PinnedCardGrid.tsx`: Multi-column responsive grid container rendering pinned cards.
  - `PinnedNotesReader.tsx`: IDE-style split workspace reader with a left navigation rail and main document viewer pane.
  - `PinNoteModal.tsx`: Searchable note picker modal dialog with search filtering, folder category chips, keyboard Escape dismissal, and pin toggle actions.
  - `types.ts`: Shared data contracts, prop interfaces, storage keys, and fallback defaults.
  - `index.ts`: Clean barrel export for all home components and types.

### Changed
- Refactored `gui/src/app/page.tsx` from a monolithic 933-line file into a lean ~230-line route orchestrator delegating all presentation to `@/components/home`.
- Resolved all ESLint warnings and guarded initial hydration with `queueMicrotask` to avoid cascading renders in React 19.
- Updated `Project - Nexus GUI.md` and `Build Log - Nexus GUI.md` with the new component hierarchy.

