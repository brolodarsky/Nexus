---
type: patch
---

### Changed
- **Default Disclosure of Live Agent Execution (`gui/`):** Configured real-time agent trace visualization (`ThinkingPanel`) in `ChatMessageThread.tsx` to mount collapsed by default (`defaultExpanded={false}`), preventing UI jumpiness while streaming responses.
- **Trace Panel Disclosure Polishing (`gui/`):** Updated default prop value in `AgentTraceVisualizer.tsx` to `defaultExpanded = false` and removed extraneous bottom border when the control bar is in collapsed state.
