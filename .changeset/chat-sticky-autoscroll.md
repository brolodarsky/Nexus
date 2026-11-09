---
type: patch
---

### Fixed
- **Chat Feed Sticky Auto-Scroll & Viewport Hijack Prevention (`gui/src/components/chat/ChatMessageThread.tsx`, `gui/src/app/chat/page.tsx`):** Resolved an issue where streaming telemetry events from `AgentTracer` repeatedly pulled the chat view to the bottom while an agent was working, preventing users from scrolling up to read earlier messages, notes, or execution steps. Introduced scroll-stickiness invariant tracking (`SCROLL_BOTTOM_THRESHOLD = 80px`) via `isAtBottomRef` and `onScroll` listener: incoming messages and live trace events now only scroll to bottom if the user was already pinned to the bottom. If the user scrolls up, auto-scroll is immediately disengaged, preserving their scroll position uninterrupted.
- **Scroll-to-Bottom Floating Affordance (`gui/src/components/chat/ChatMessageThread.tsx`):** Added a floating pill button that appears whenever the viewport is detached from the bottom. Features a pulsating cyan badge and `"New activity"` indicator when live telemetry arrives while scrolled up, and smoothly scrolls to bottom upon click while re-engaging sticky auto-scrolling.
- **ThinkingPanel Compact Scroll Guard (`gui/src/components/AgentTraceVisualizer.tsx`):** Added user scroll detection to `ThinkingPanel` in compact scroll mode (`fullHeight: false`) so inspecting earlier tool calls or thinking steps while an agent is live does not jump to the bottom on subsequent events.
