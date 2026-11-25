---
type: minor
---
### Added
- Created pure bidirectional tool-call pairing and signature formatting utilities in `gui/src/lib/traceToolPairing.ts` (`buildToolCallPairMap`, `formatShortCallId`, `formatCallDuration`, `extractLegacyToolArgs`).
- Added clickable tool-call signatures and bidirectional jump badges (`↳ Result #N` / `↳ Error #N` / `↰ Call #N` with short `call_id` tags and elapsed duration pills) plus expanded-footer jump links in `gui/src/components/AgentTraceVisualizer.tsx`, powering both the `/audit` view and in-chat `ThinkingPanel`.
- Jumping between paired tool ends smoothly scrolls the counterpart step card into view, auto-expands its payload, and flashes a temporary highlight ring.
- Added Node.js regression test suite `tests/test_trace_tool_pairing.js` covering out-of-order `call_id` correlation, `tool_error` pairing, legacy FIFO fallback, pending/orphan events, collision-resistant short IDs, and duration formatting.

### Changed
- Updated `TraceStepCard` so `tool_result` and `tool_error` step headers display the full argument signature inherited from their paired `tool_call` instead of empty parentheses.
- Added compact `#shortCallId` badges to tool execution cards in the Subagent Swarm tab of `gui/src/app/audit/page.tsx`.
