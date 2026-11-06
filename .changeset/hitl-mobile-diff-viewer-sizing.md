---
type: patch
---

### Fixed
- **Mobile HITL Diff Viewer Container Collapse (`gui/src/app/hitl/page.tsx`):** Resolved an issue where Monaco `DiffEditor` collapsed to a 0px / 18px tiny sliver on mobile screens (< 768px). Because outer flex containers used unconstrained `min-h-[...]` rather than definite CSS heights on mobile, Monaco's internal percentage height wrapper resolved to 0px. Configured explicit responsive container and editor heights (`62vh` / `min-h-[460px]` for diff review, `60vh` / `min-h-[420px]` for 3-way conflict view), enabled `automaticLayout: true` in Monaco options, tuned mobile typography (`fontSize: 12`, `lineNumbersMinChars: 3`, `padding: 8px`), added viewport-keyed remounting, and auto-collapsed the queue sidebar and reasoning cards on mobile viewports to grant full screen real estate to the active unified diff.
