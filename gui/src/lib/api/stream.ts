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
  | "error";        // Fatal pipeline error
  agent?: string;                   // Originating agent display name (e.g. "NexusAgent", "Subagent #1 (low)")
  agent_id?: string;                // Unique DAG node identifier (e.g. "nexus", "subagent-1")
  parent_id?: string | null;        // Parent DAG node identifier (e.g. "nexus" for spawned subagents, null for root)
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
  callbacks: {
    onTrace: (event: TraceEvent) => void;
    onDone: (event: TraceEvent) => void;
    onError: (error: string) => void;
  },
  modelTier?: string,
  images?: string[]
): () => void {
  // AbortController allows canceling the fetch request if the user navigates away or cancels
  const controller = new AbortController();

  // Immediately-Invoked Async Function Expression (IIFE) to run async streaming logic
  (async () => {
    try {
      // getApiBase(): Dynamically targets the host's backend port (e.g. over LAN/Tailscale) without proxy buffering
      const res = await fetch(`${getApiBase()}/api/agents/ask/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          conversation_id: conversationId,
          model_tier: modelTier,
          images: images && images.length > 0 ? images : undefined,
        }),
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

      // Track whether a terminal packet ("done" or "error") was received to guard against abrupt disconnection
      let receivedTerminal = false;

      while (true) {
        // reader.read() blocks until the next byte chunk arrives from FastAPI
        const { done, value } = await reader.read();
        if (done) break; // HTTP connection closed by server

        // stream: true preserves multi-byte character state across chunks
        buffer += decoder.decode(value, { stream: true });

        // SSE standard separates events by double newlines (\n\n)
        const lines = buffer.split("\n\n");
        // Pop the last element: if the chunk ended mid-message, keep the remainder in the buffer
        buffer = lines.pop() ?? "";

        for (const block of lines) {
          for (const line of block.split("\n")) {
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

            try {
              // Route event to corresponding UI callback and flag terminal state
              if (event.type === "done") {
                receivedTerminal = true;
                callbacks.onDone(event);
              } else if (event.type === "error") {
                receivedTerminal = true;
                callbacks.onError(event.message);
              } else {
                callbacks.onTrace(event); // Animate item into Thinking Panel
              }
            } catch (cbErr) {
              console.error("Error executing SSE stream event callback:", cbErr);
            }
          }
        }
      }

      // Flush any trailing multi-byte characters remaining in the TextDecoder buffer
      buffer += decoder.decode();
      if (buffer.trim()) {
        for (const line of buffer.split("\n")) {
          // Ignore SSE comments
          if (!line.startsWith("data: ")) continue;
          const jsonStr = line.slice(6);
          let event: TraceEvent;
          try {
            event = JSON.parse(jsonStr);
          } catch {
            continue;
          }
          try {
            if (event.type === "done") {
              receivedTerminal = true;
              callbacks.onDone(event);
            } else if (event.type === "error") {
              receivedTerminal = true;
              callbacks.onError(event.message);
            } else {
              callbacks.onTrace(event);
            }
          } catch (cbErr) {
            console.error("Error executing trailing SSE stream event callback:", cbErr);
          }
        }
      }

      // If the HTTP connection closed (done: true) without emitting a terminal "done" or "error" packet,
      // and the stream was not intentionally cancelled by the user via AbortController,
      // trigger onError so the UI clears the thinking spinner and alerts the user (e.g. backend worker reload).
      if (!receivedTerminal && !controller.signal.aborted) {
        callbacks.onError(
          "Stream disconnected unexpectedly before agent finished. The backend process may have reloaded or encountered a network interruption."
        );
      }
    } catch (err) {
      // Ignore AbortError when cancellation was intentionally triggered by the user
      if ((err as Error).name !== "AbortError") {
        callbacks.onError(
          err instanceof Error ? err.message : "Stream connection failed"
        );
      }
    }
  })();

  // Return teardown closure that cancels the active stream
  return () => controller.abort();
}

