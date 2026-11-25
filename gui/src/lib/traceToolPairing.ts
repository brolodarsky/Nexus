/**
 * traceToolPairing.ts — Pure bidirectional pairing & signature formatting helpers for tool traces.
 * Correlates `tool_call` events with their matching `tool_result` or `tool_error` counterparts,
 * propagates argument signatures across both ends, and formats compact call IDs and durations.
 * Zero runtime imports so this module can be compiled and unit-tested directly in Node.js.
 */

import type { TraceEvent } from "@/lib/api/stream";

// ToolCallPairInfo: Describes the paired relationship and shared metadata for a single tool trace step.
export interface ToolCallPairInfo {
  role: "call" | "result" | "error";        // Whether this step is the invocation or outcome end
  stepIndex: number;                        // 0-based index of this event in the rendered events array
  counterpartIndex: number | null;          // 0-based index of the matching counterpart step, or null if unmatched
  counterpartRole: "call" | "result" | "error" | null; // Role of the paired counterpart step
  callId: string | null;                    // Full raw provider/LangChain call_id if emitted
  shortCallId: string | null;               // Compact collision-resistant display ID (e.g. "2b6a5234")
  toolName: string | null;                  // Name of the invoked tool (propagated if missing on one end)
  callArgs: Record<string, unknown> | null; // Structured arguments from the `tool_call` event
  legacyArgsStr: string | null;             // Fallback args string parsed from legacy `tool_call` messages
  durationMs: number | null;                // Elapsed execution time in milliseconds (result - call)
  durationLabel: string | null;             // Human-readable formatted duration (e.g. "42ms", "1.4s", "1m 12s")
  resultCharCount: number | null;           // Character count of the returned tool output or error string
  isError: boolean;                         // True when the paired outcome event is `tool_error`
}

/**
 * formatShortCallId — Produces a compact 8-character identifier for UI badges without losing uniqueness.
 * - callId: string | null | undefined — Raw call identifier (UUIDv4, Anthropic `toolu_01...`, OpenAI `call_...`, etc.).
 * - Returns: string | null — Compact 8-char slice, or null when empty/absent.
 */
export function formatShortCallId(callId: string | null | undefined): string | null {
  if (typeof callId !== "string") return null;
  const trimmed = callId.trim();
  if (!trimmed) return null;

  // Standard UUIDs pack high-entropy randomness in their leading 8 hex characters
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(trimmed)) {
    return trimmed.slice(0, 8);
  }

  // Strip shared provider prefixes (e.g. Anthropic `toolu_01...` or OpenAI `call_...`) before slicing
  const stripped = trimmed.replace(/^(?:toolu_|call_|fc_)/i, "");
  if (stripped.length <= 8) {
    return stripped;
  }

  // Use the trailing 8 characters for ULID/prefixed IDs whose leading bytes share constant timestamps/headers
  return stripped.slice(-8);
}

/**
 * formatCallDuration — Converts elapsed milliseconds into a concise human-readable duration label.
 * - durationMs: number | null | undefined — Elapsed time in milliseconds between call and result.
 * - Returns: string | null — Compact label ("42ms", "1.4s", "1m 12s"), or null if invalid/negative.
 */
export function formatCallDuration(durationMs: number | null | undefined): string | null {
  if (durationMs == null || !Number.isFinite(durationMs) || durationMs < 0) {
    return null;
  }
  if (durationMs < 1000) {
    return `${Math.round(durationMs)}ms`;
  }
  if (durationMs < 60_000) {
    return `${(durationMs / 1000).toFixed(1)}s`;
  }

  let mins = Math.floor(durationMs / 60_000);
  let remSecs = Math.round((durationMs % 60_000) / 1000);
  // Roll 60 rounded seconds cleanly into the next minute so we never emit "1m 60s"
  if (remSecs === 60) {
    mins += 1;
    remSecs = 0;
  }
  return `${mins}m ${remSecs}s`;
}

/**
 * extractLegacyToolArgs — Parses raw inline arguments from older `tool_call` text messages lacking `data.args`.
 * - evt: TraceEvent — A trace event emitted by AgentTracer.
 * - Returns: string | null — Trimmed parameter substring inside parentheses, or null if absent.
 */
export function extractLegacyToolArgs(evt: TraceEvent): string | null {
  if (evt.type !== "tool_call" || !evt.message) return null;
  const match = evt.message.match(/Calling tool:\s*[\w_.-]+\(([\s\S]*)\)/);
  const extracted = match ? match[1].trim() : "";
  return extracted || null;
}

/**
 * Normalizes agent identity per event using the same resolution rule as TraceStepCard so
 * legacy FIFO fallback queues stay isolated between the Head Agent and parallel subagents.
 */
function resolveEventAgentKey(evt: TraceEvent): string {
  return (
    evt.agent_id ||
    (evt.agent?.toLowerCase().startsWith("subagent") ? "subagent" : (evt.agent || "nexus"))
  );
}

/**
 * buildToolCallPairMap — Correlates every `tool_call` event with its matching `tool_result` or `tool_error`.
 * Primary matching uses `data.call_id` (supporting concurrent and out-of-order batches); older traces
 * without `call_id` fall back to FIFO matching scoped by `(agentKey, toolName)`.
 *
 * - events: TraceEvent[] — Ordered trace event array rendered by TraceStepList.
 * - Returns: Map<number, ToolCallPairInfo> — Lookup keyed by 0-based event index.
 */
export function buildToolCallPairMap(events: TraceEvent[]): Map<number, ToolCallPairInfo> {
  // Map<number, ToolCallPairInfo> stores bidirectional pairing metadata keyed by 0-based step index
  const pairMap = new Map<number, ToolCallPairInfo>();
  // Pending `tool_call` indices indexed by `${agentKey}::${callId}` for strict per-agent correlation
  const pendingByScopedCallId = new Map<string, number>();
  // Fallback lookup by bare `callId` in case an event's agent label differed between emission points
  const pendingByBareCallId = new Map<string, number>();
  // FIFO queues keyed by `${agentKey}::${toolName}` for legacy traces emitted before `call_id` existed
  const pendingLegacyQueue = new Map<string, number[]>();

  for (let idx = 0; idx < events.length; idx += 1) {
    const evt = events[idx];
    const data = (evt.data ?? {}) as Record<string, unknown>;
    const agentKey = resolveEventAgentKey(evt);
    const toolName = typeof data.tool === "string" ? data.tool : null;
    const rawCallId = typeof data.call_id === "string" && data.call_id.trim()
      ? data.call_id.trim()
      : null;
    const shortCallId = formatShortCallId(rawCallId);

    if (evt.type === "tool_call") {
      // Only treat plain non-array dictionaries as structured keyword arguments
      const rawArgs = data.args;
      const callArgs =
        rawArgs && typeof rawArgs === "object" && !Array.isArray(rawArgs)
          ? (rawArgs as Record<string, unknown>)
          : null;
      const hasStructuredArgs = Boolean(callArgs && Object.keys(callArgs).length > 0);
      const legacyArgsStr = hasStructuredArgs ? null : extractLegacyToolArgs(evt);

      pairMap.set(idx, {
        role: "call",
        stepIndex: idx,
        counterpartIndex: null,
        counterpartRole: null,
        callId: rawCallId,
        shortCallId,
        toolName,
        callArgs: hasStructuredArgs ? callArgs : null,
        legacyArgsStr,
        durationMs: null,
        durationLabel: null,
        resultCharCount: null,
        isError: false,
      });

      if (rawCallId) {
        pendingByScopedCallId.set(`${agentKey}::${rawCallId}`, idx);
        pendingByBareCallId.set(rawCallId, idx);
      } else if (toolName) {
        const legacyKey = `${agentKey}::${toolName}`;
        const queue = pendingLegacyQueue.get(legacyKey);
        if (queue) {
          queue.push(idx);
        } else {
          pendingLegacyQueue.set(legacyKey, [idx]);
        }
      }
      continue;
    }

    if (evt.type === "tool_result" || evt.type === "tool_error") {
      const isErr = evt.type === "tool_error";
      const outcomeRole: "result" | "error" = isErr ? "error" : "result";
      const resultCharCount =
        typeof data.result === "string"
          ? data.result.length
          : typeof data.error === "string"
            ? data.error.length
            : null;

      let matchedCallIdx: number | undefined;

      // 1. Primary correlation: exact `call_id` match (scoped to agent first, then bare `call_id`)
      if (rawCallId) {
        const scopedKey = `${agentKey}::${rawCallId}`;
        const scopedMatch = pendingByScopedCallId.get(scopedKey);
        if (scopedMatch !== undefined) {
          matchedCallIdx = scopedMatch;
          pendingByScopedCallId.delete(scopedKey);
          pendingByBareCallId.delete(rawCallId);
        } else {
          const bareMatch = pendingByBareCallId.get(rawCallId);
          if (bareMatch !== undefined) {
            matchedCallIdx = bareMatch;
            pendingByBareCallId.delete(rawCallId);
            const matchedAgentKey = resolveEventAgentKey(events[bareMatch]);
            pendingByScopedCallId.delete(`${matchedAgentKey}::${rawCallId}`);
          }
        }
      }

      // 2. Legacy FIFO fallback: correlate oldest pending call for `(agentKey, toolName)` when `call_id` is absent
      if (matchedCallIdx === undefined && toolName) {
        const legacyKey = `${agentKey}::${toolName}`;
        const queue = pendingLegacyQueue.get(legacyKey);
        if (queue && queue.length > 0) {
          matchedCallIdx = queue.shift();
        }
      }

      if (matchedCallIdx !== undefined) {
        const callInfo = pairMap.get(matchedCallIdx);
        const callEvt = events[matchedCallIdx];
        const startMs = callEvt?.timestamp ? Date.parse(callEvt.timestamp) : NaN;
        const endMs = evt.timestamp ? Date.parse(evt.timestamp) : NaN;
        const durationMs =
          Number.isFinite(startMs) && Number.isFinite(endMs) && endMs >= startMs
            ? endMs - startMs
            : null;
        const durationLabel = formatCallDuration(durationMs);

        if (callInfo) {
          callInfo.counterpartIndex = idx;
          callInfo.counterpartRole = outcomeRole;
          callInfo.durationMs = durationMs;
          callInfo.durationLabel = durationLabel;
          callInfo.resultCharCount = resultCharCount;
          callInfo.isError = isErr;
        }

        pairMap.set(idx, {
          role: outcomeRole,
          stepIndex: idx,
          counterpartIndex: matchedCallIdx,
          counterpartRole: "call",
          callId: rawCallId ?? callInfo?.callId ?? null,
          shortCallId: shortCallId ?? callInfo?.shortCallId ?? null,
          toolName: toolName ?? callInfo?.toolName ?? null,
          callArgs: callInfo?.callArgs ?? null,
          legacyArgsStr: callInfo?.legacyArgsStr ?? null,
          durationMs,
          durationLabel,
          resultCharCount,
          isError: isErr,
        });
      } else {
        // Standalone/orphan result or error when the originating `tool_call` is outside this slice
        pairMap.set(idx, {
          role: outcomeRole,
          stepIndex: idx,
          counterpartIndex: null,
          counterpartRole: null,
          callId: rawCallId,
          shortCallId,
          toolName,
          callArgs: null,
          legacyArgsStr: null,
          durationMs: null,
          durationLabel: null,
          resultCharCount,
          isError: isErr,
        });
      }
    }
  }

  return pairMap;
}
