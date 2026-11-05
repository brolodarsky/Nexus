---
type: patch
---
### Changed
- **Default Disclosure & Expand/Collapse Functionality for AgentTracer Telemetry Windows (`gui/src/components/AgentTraceVisualizer.tsx`):**
  - Updated individual trace step cards (`TraceStepCard`) to mount collapsed by default (`isOpen = false`), replacing forced wide-open disclosures that produced massive vertical walls of text during runs.
  - Fixed non-functional Expand/Collapse button on individual step cards: replaced static `forceExpanded || localOpen` boolean short-circuit with synchronized `useEffect` state updates and decoupled individual click handlers, allowing step details to expand or collapse freely.
  - Added dedicated, accessible Expand/Collapse toggle buttons (`▾ Collapse All` / `▸ Expand All`) to `AgentGraphView` (both for the active Node Deep-Dive Inspector and the chronological steps list), ensuring users inspecting DAG nodes can collapse or expand all execution payloads in a single click.
  - Made the initial task prompt card and final assistant synthesis card in `AgentGraphView` collapsible by default with functional `▾ Collapse` / `▸ Expand` controls and clamped 2-line preview fallbacks.
  - Updated `ThinkingPanel` to initialize `expandAllSteps = false` and wired the toolbar toggle to cascade collapse/expand triggers to all child trace cards.
