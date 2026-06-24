/**
 * api.ts — Typed API client for the Nexus Engine FastAPI backend.
 * All fetch calls are routed through these functions for consistency.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// ── Types ─────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  engine: string;
  version: string;
}

export interface AgentStatus {
  name: string;
  display_name: string;
  status: "idle" | "running" | "waiting_hitl" | "not_built" | "error";
  last_run: string | null;
  error_count: number;
  description: string;
}

export interface AskResponse {
  response: string;
  agent: string;
  domain: string | null;
  confidence: number | null;
  reasoning: string | null;
  timestamp: string;
}

export interface ChatHistoryEntry {
  role: "user" | "assistant";
  content: string;
  agent?: string;
  domain?: string | null;
  confidence?: number | null;
  trace?: any[];
  timestamp: string;
}

export interface VaultStructureResponse {
  tree: string;
  path: string | null;
}

export interface NoteContentResponse {
  path: string;
  content: string;
}

export interface VaultEntry {
  name: string;
  path: string;
  type: "file" | "directory";
  size?: number;
  mtime?: number;
  has_audio: boolean;
}

// ── Helpers ───────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }

  return res.json() as Promise<T>;
}

// ── Endpoints ─────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/health");
}

export async function getAgentStatus(): Promise<AgentStatus[]> {
  return apiFetch<AgentStatus[]>("/api/agents/status");
}

export async function askBrain(query: string): Promise<AskResponse> {
  return apiFetch<AskResponse>("/api/agents/ask", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}

export async function getChatHistory(sessionId: string = "default"): Promise<ChatHistoryEntry[]> {
  return apiFetch<ChatHistoryEntry[]>(`/api/agents/ask/history?session_id=${encodeURIComponent(sessionId)}`);
}

// ── SSE Streaming Types & Client ──────────────────────────────

export interface TraceEvent {
  type:
    | "agent_start"
    | "agent_end"
    | "llm_call"
    | "llm_response"
    | "tool_call"
    | "tool_result"
    | "tool_error"
    | "route"
    | "delegate"
    | "info"
    | "done"
    | "error";
  agent?: string;
  color?: string;
  message: string;
  timestamp: string;
  data?: Record<string, unknown>;
  // Fields only on "done" events
  response?: string;
  domain?: string | null;
  confidence?: number | null;
  reasoning?: string | null;
}

/**
 * Streams trace events from POST /api/agents/ask/stream via SSE.
 * Uses fetch + ReadableStream (not EventSource) to support POST bodies.
 *
 * Returns an abort function to cancel the stream.
 */
export function askBrainStream(
  query: string,
  callbacks: {
    onTrace: (event: TraceEvent) => void;
    onDone: (event: TraceEvent) => void;
    onError: (error: string) => void;
  }
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/agents/ask/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const detail = await res.text();
        callbacks.onError(`API ${res.status}: ${detail}`);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        callbacks.onError("No response body");
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines: each event is "data: {...}\n\n"
        const lines = buffer.split("\n\n");
        // Keep the last incomplete chunk in the buffer
        buffer = lines.pop() ?? "";

        for (const block of lines) {
          for (const line of block.split("\n")) {
            if (!line.startsWith("data: ")) continue;

            const jsonStr = line.slice(6);
            try {
              const event: TraceEvent = JSON.parse(jsonStr);

              if (event.type === "done") {
                callbacks.onDone(event);
              } else if (event.type === "error") {
                callbacks.onError(event.message);
              } else {
                callbacks.onTrace(event);
              }
            } catch {
              // Ignore malformed JSON lines
            }
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        callbacks.onError(
          err instanceof Error ? err.message : "Stream connection failed"
        );
      }
    }
  })();

  return () => controller.abort();
}


export async function getVaultStructure(
  path?: string
): Promise<VaultStructureResponse> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch<VaultStructureResponse>(`/api/vault/structure${params}`);
}

export interface Transaction {
  id: number;
  agent_name: string;
  action_type: string;
  target_file: string;
  original_content: string | null;
  proposed_content: string;
  reasoning: string | null;
  status: string;
  created_at: string;
}

export async function getNote(path: string): Promise<NoteContentResponse> {
  return apiFetch<NoteContentResponse>(
    `/api/vault/note?path=${encodeURIComponent(path)}`
  );
}

export async function getPendingHitl(): Promise<Transaction[]> {
  return apiFetch<Transaction[]>("/api/hitl/pending");
}

export async function approveHitl(id: number): Promise<{status: string, message: string}> {
  return apiFetch<{status: string, message: string}>(`/api/hitl/${id}/approve`, { method: "POST" });
}

export async function rejectHitl(id: number): Promise<{status: string, message: string}> {
  return apiFetch<{status: string, message: string}>(`/api/hitl/${id}/reject`, { method: "POST" });
}

export async function listVault(path?: string): Promise<VaultEntry[]> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch<VaultEntry[]>(`/api/vault/list${params}`);
}

export async function generatePodcast(path: string, force: boolean = false): Promise<any> {
  return apiFetch<any>("/api/vault/podcast/generate", {
    method: "POST",
    body: JSON.stringify({ path, force }),
  });
}

export function getPodcastAudioUrl(path: string): string {
  return `${API_BASE}/api/vault/podcast/download?path=${encodeURIComponent(path)}`;
}
