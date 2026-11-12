/**
 * stream.ts — Server-Sent Events (SSE) streaming client and telemetry trace types for Nexus Agent execution.
 */

import { getApiBase } from "./client";

// Discriminated union of trace events emitted during live agent graph execution
export interface TraceEvent {
  id?: string;                      // Unique 8-char step event identifier
  step?: number;                    // 1-indexed sequential step number within an agent's lifecycle
  type:
  | "agent_start"   // Agent began execution with initial context
  | "agent_end"     // Agent completed its graph cycle
  | "llm_call"      // Agent dispatched a prompt to the LLM
  | "llm_response"  // LLM returned text or tool invocation request
  | "tool_call"     // Graph invoked a specific Python tool with arguments
  | "tool_result"   // Tool returned stdout/data payload
  | "tool_error"    // Tool execution raised an exception
  | "route"         // Router made a domain classification decision
  | "delegate"      // Router passed execution to a domain subgraph
  | "info"          // Generic informational status message
  | "done"          // Execution complete; carries final output payload
  | "error"         // Fatal pipeline error
  | "sync_required";// Re-attach fallback telling UI the background turn already finished and to fetch history
  agent?: string;                   // Originating agent display name (e.g. "NexusAgent", "Subagent #1 (low)")
  agent_id?: string;                // Unique DAG node identifier (e.g. "nexus", "subagent-1")
  parent_id?: string | null;        // Parent DAG node identifier (e.g. "nexus" for spawned subagents, null for root)
  thread_id?: string | null;        // Target conversation/thread UUID for multi-tab pub/sub isolation
  color?: string;                   // Terminal/UI theme color (e.g. "yellow", "cyan", "magenta")
  message: string;                  // Full, untruncated log text for the Thinking Panel
  timestamp: string;                // ISO-8601 UTC event timestamp
  data?: Record<string, unknown>;   // Structured payload (e.g. full tool arguments, tool results, token counts, subagent prompts)
  // Payload fields populated only on the final "done" event:
  response?: string;                // Final Markdown answer from the assistant
  domain?: string | null;           // Routed domain category
  confidence?: number | null;       // Classification confidence
  reasoning?: string | null;        // Router rationale
  model_tier?: string | null;       // Effective model tier used on this turn ("strong", "medium", "low")
  model_name?: string | null;       // Concrete model identifier used on this turn (e.g. "gemini-4-argon")
  user_message_id?: number | null;  // SQLite `messages.id` assigned to the persisted user message
  assistant_message_id?: number | null; // SQLite `messages.id` assigned to the persisted assistant message
}

// BrainStreamCallbacks: event handlers invoked by SSE stream consumers as trace packets arrive
// - onTrace: receives intermediate execution telemetry (tool calls, LLM calls, subagent steps)
// - onDone: receives final completion packet carrying response markdown and persisted message IDs
// - onError: receives human-readable error message when stream fails or emits an error packet
// - onSyncRequired: optional handler fired on re-attach when the background run finished just before connecting
// - onActivity: optional heartbeat hook called whenever bytes arrive (traces, ': ping' keepalives, or terminal events)
export interface BrainStreamCallbacks {
  onTrace: (event: TraceEvent) => void;
  onDone: (event: TraceEvent) => void;
  onError: (error: string) => void;
  onSyncRequired?: () => void;
  onActivity?: () => void;
}

// Maximum silence tolerated between SSE chunks before treating the socket as half-open/stalled
// (Backend emits ': ping' every 10s when idle; 35s allows 3+ missed keepalives before auto-reattaching)
const SSE_HEARTBEAT_TIMEOUT_MS = 35_000;

/**
 * Shared SSE consumer reading `ReadableStream` chunks from either POST `/api/agents/ask/stream`
 * or GET `/api/agents/ask/stream/{conversationId}` and dispatching parsed `TraceEvent` payloads.
 *
 * - url: Target FastAPI SSE endpoint URL.
 * - init: `RequestInit` options (method, headers, optional JSON body) excluding `signal`.
 * - callbacks: `BrainStreamCallbacks` event listeners for trace updates, completion, and errors.
 * - Returns: An abort closure `() => void` that immediately closes the active HTTP stream via `AbortController`.
 */
function consumeBrainSseStream(
  url: string,
  init: Omit<RequestInit, "signal">,
  callbacks: BrainStreamCallbacks
): () => void {
  // AbortController allows canceling the fetch request if the user navigates away or switches conversations
  const controller = new AbortController();
  // Distinguishes internal heartbeat timeout aborts from intentional caller cancellations
  let timedOut = false;
  let heartbeatTimer: ReturnType<typeof setTimeout> | null = null;

  const clearHeartbeatTimer = () => {
    if (heartbeatTimer !== null) {
      clearTimeout(heartbeatTimer);
      heartbeatTimer = null;
    }
  };

  const resetHeartbeatTimer = () => {
    clearHeartbeatTimer();
    if (controller.signal.aborted) return;
    heartbeatTimer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, SSE_HEARTBEAT_TIMEOUT_MS);
  };

  // Helper dispatching a single parsed SSE event packet to the appropriate callback
  const dispatchPacket = (event: TraceEvent): boolean => {
    try {
      // Route event to corresponding UI callback and flag terminal state
      if (event.type === "done") {
        callbacks.onDone(event);
        return true;
      } else if (event.type === "error") {
        callbacks.onError(event.message);
        return true;
      } else if (event.type === "sync_required") {
        if (callbacks.onSyncRequired) {
          callbacks.onSyncRequired();
        } else {
          callbacks.onError("Active run already completed; refresh chat history.");
        }
        return true;
      } else {
        callbacks.onTrace(event); // Animate item into Thinking Panel
        return false;
      }
    } catch (cbErr) {
      console.error("Error executing SSE stream event callback:", cbErr);
      return false;
    }
  };

  // Immediately-Invoked Async Function Expression (IIFE) to run async streaming logic
  (async () => {
    try {
      const res = await fetch(url, {
        ...init,
        signal: controller.signal, // Connects the abort signal to the fetch request
      });

      if (!res.ok) {
        const detail = await res.text();
        callbacks.onError(`API ${res.status}: ${detail}`);
        return;
      }

      // res.body.getReader() gives low-level access to the incoming byte stream
      const reader = res.body?.getReader();
      if (!reader) {
        callbacks.onError("No response body");
        return;
      }

      // TextDecoder converts raw binary Uint8Array chunks into UTF-8 text strings
      const decoder = new TextDecoder();
      let buffer = ""; // Temporary buffer to assemble split SSE packets across chunk boundaries

      // Track whether a terminal packet ("done", "error", or "sync_required") was received to guard against abrupt disconnection
      let receivedTerminal = false;
      callbacks.onActivity?.();
      resetHeartbeatTimer();

      while (true) {
        // reader.read() blocks until the next byte chunk arrives from FastAPI
        const { done, value } = await reader.read();
        if (done) break; // HTTP connection closed by server

        callbacks.onActivity?.();
        resetHeartbeatTimer();

        // stream: true preserves multi-byte character state across chunks
        buffer += decoder.decode(value, { stream: true });

        // SSE standard separates events by blank lines (\n\n or \r\n\r\n)
        const lines = buffer.split(/\r?\n\r?\n/);
        // Pop the last element: if the chunk ended mid-message, keep the remainder in the buffer
        buffer = lines.pop() ?? "";

        for (const block of lines) {
          for (const line of block.split(/\r?\n/)) {
            // Ignore SSE keepalive comments (': ping') and non-data lines per RFC 8895
            if (!line.startsWith("data: ")) continue;

            const jsonStr = line.slice(6); // Strip "data: " prefix to extract JSON string
            let event: TraceEvent;
            try {
              event = JSON.parse(jsonStr);
            } catch {
              // Ignore malformed JSON chunks to prevent stream parser from crashing
              continue;
            }

            if (dispatchPacket(event)) {
              receivedTerminal = true;
            }
          }
        }
      }

      clearHeartbeatTimer();

      // Flush any trailing multi-byte characters remaining in the TextDecoder buffer
      buffer += decoder.decode();
      if (buffer.trim()) {
        for (const line of buffer.split(/\r?\n/)) {
          // Ignore SSE comments
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6);
          let event: TraceEvent;
          try {
            event = JSON.parse(jsonStr);
          } catch {
            continue;
          }
          if (dispatchPacket(event)) {
            receivedTerminal = true;
          }
        }
      }

      // If the HTTP connection closed (done: true) without emitting a terminal "done" or "error" packet,
      // and the stream was not intentionally cancelled by the user via AbortController,
      // trigger onError so the UI clears the thinking spinner and recovers from server history.
      if (!receivedTerminal && (!controller.signal.aborted || timedOut)) {
        callbacks.onError(
          "Stream disconnected unexpectedly before agent finished. The backend process may have reloaded or encountered a network interruption."
        );
      }
    } catch (err) {
      // Surface watchdog heartbeat timeouts through onError while ignoring caller-initiated aborts
      if (timedOut) {
        callbacks.onError("Stream connection stalled waiting for server heartbeat.");
      } else if ((err as Error).name !== "AbortError") {
        callbacks.onError(
          err instanceof Error ? err.message : "Stream connection failed"
        );
      }
    } finally {
      clearHeartbeatTimer();
    }
  })();

  // Return teardown closure that cancels the active stream
  return () => controller.abort();
}

/**
 * Streams trace events from POST /api/agents/ask/stream via Server-Sent Events (SSE).
 * Uses fetch + ReadableStream (rather than standard browser EventSource) to allow sending JSON POST bodies.
 *
 * @param query The user's input prompt.
 * @param conversationId The target conversation UUID for sticky state and message persistence.
 * @param callbacks Event listeners for streaming updates, stream completion, and errors.
 * @param modelTier Optional per-turn model tier or model identifier ("strong", "medium", "low").
 * @param images Optional array of uploaded image URLs or asset paths for multimodal vision execution.
 * @returns An abort function that immediately terminates the active HTTP stream.
 */
export function askBrainStream(
  query: string,
  conversationId: string,
  callbacks: BrainStreamCallbacks,
  modelTier?: string,
  images?: string[]
): () => void {
  // getApiBase(): Dynamically targets the host's backend port (e.g. over LAN/Tailscale) without proxy buffering
  return consumeBrainSseStream(
    `${getApiBase()}/api/agents/ask/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        conversation_id: conversationId,
        model_tier: modelTier,
        images: images && images.length > 0 ? images : undefined,
      }),
    },
    callbacks
  );
}

/**
 * Re-attaches to an already running backend turn via GET /api/agents/ask/stream/{conversationId}.
 * Replays buffered trace events emitted while the client was away, then continues streaming live steps.
 *
 * @param conversationId UUID of the conversation thread whose active run should be resumed in the UI.
 * @param callbacks Event listeners for trace replay, completion, sync fallback, and connection errors.
 * @returns An abort function that closes the client SSE connection without halting the backend turn.
 */
export function attachBrainStream(
  conversationId: string,
  callbacks: BrainStreamCallbacks
): () => void {
  return consumeBrainSseStream(
    `${getApiBase()}/api/agents/ask/stream/${encodeURIComponent(conversationId)}`,
    { method: "GET" },
    callbacks
  );
}

