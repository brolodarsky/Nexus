/**
 * stream.ts — Server-Sent Events (SSE) streaming client and telemetry trace types for Nexus Agent execution.
 */

import { API_BASE } from "./client";

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
  modelTier?: string
): () => void {
  // AbortController allows canceling the fetch request if the user navigates away or cancels
  const controller = new AbortController();

  // Immediately-Invoked Async Function Expression (IIFE) to run async streaming logic
  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/agents/ask/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          conversation_id: conversationId,
          model_tier: modelTier,
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
            // SSE payload lines always start with "data: " prefix
            if (!line.startsWith("data: ")) continue;

            const jsonStr = line.slice(6); // Strip "data: " prefix to extract JSON string
            try {
              const event: TraceEvent = JSON.parse(jsonStr);

              // Route event to corresponding UI callback
              if (event.type === "done") {
                callbacks.onDone(event);
              } else if (event.type === "error") {
                callbacks.onError(event.message);
              } else {
                callbacks.onTrace(event); // Animate item into Thinking Panel
              }
            } catch {
              // Ignore malformed JSON chunks to prevent stream parser from crashing
            }
          }
        }
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

