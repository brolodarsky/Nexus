/**
 * api.ts — Typed API client for the Nexus Engine FastAPI backend.
 * All fetch calls are routed through these functions for consistency.
 */

// process.env: Node/Next.js environment variables. NEXT_PUBLIC_ prefix exposes the variable to the client-side browser.
// ?? (Nullish Coalescing): Falls back to default 'http://127.0.0.1:8000' if env variable is null or undefined.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// ── Types ─────────────────────────────────────────────────────

// Interface describing the health status payload returned by GET /api/health
export interface HealthResponse {
  status: string;  // e.g. "ok"
  engine: string;  // e.g. "Nexus"
  version: string; // e.g. "2.0.0"
}

// Interface representing an agent's operational state in the Engine Dashboard
export interface AgentStatus {
  name: string;                                                         // Unique machine identifier (e.g. "career", "librarian")
  display_name: string;                                                 // Human-readable label (e.g. "Career Agent")
  status: "idle" | "running" | "waiting_hitl" | "not_built" | "error";  // Strict union of allowed lifecycle states
  last_run: string | null;                                              // ISO-8601 UTC timestamp or null if never executed
  error_count: number;                                                  // Running count of exceptions encountered
  description: string;                                                  // Plain-text summary of agent capabilities
}

// Interface for synchronous chat response returned by POST /api/agents/ask
export interface AskResponse {
  response: string;         // Final generated markdown text from the agent
  agent: string;            // The specific agent that answered (e.g. "career", "librarian")
  domain: string | null;    // Classified knowledge domain (e.g. "career", "general")
  confidence: number | null;// Router confidence score between 0.0 and 1.0
  reasoning: string | null; // Explanation of why the router selected this agent
  timestamp: string;        // ISO-8601 timestamp of response generation
}

// Interface for individual chat messages loaded from SQLite chats.db
export interface ChatHistoryEntry {
  role: "user" | "assistant"; // Sender identifier determining bubble alignment & styling
  content: string;            // Raw markdown text of the message
  agent?: string;             // Optional agent name if sent by an AI assistant
  domain?: string | null;     // Optional domain classification
  confidence?: number | null; // Optional routing confidence score
  trace?: any[];              // Optional array of execution steps for post-run inspection
  timestamp: string;          // ISO-8601 timestamp of message creation
}

// Interface representing a persistent conversation thread in the sidebar
export interface Conversation {
  id: string;                 // UUID primary key linking to chats.db
  title: string;              // User-visible thread title (e.g. "Career Outreach")
  active_agent: string | null;// Sticky session agent (bypasses router if locked)
  created_at: string;         // ISO-8601 creation timestamp
  last_updated: string;       // ISO-8601 timestamp of last user/assistant message
}

// Interface for tree view representation of the Vault folder structure
export interface VaultStructureResponse {
  tree: string;               // Formatted ASCII/indented folder listing
  path: string | null;        // Scoped root directory path or null for entire vault
}

// Interface for raw markdown file content loaded from the Vault
export interface NoteContentResponse {
  path: string;               // Relative vault path (e.g. "3. Operations/My Skills.md")
  content: string;            // Full UTF-8 text content of the note
}

// Interface for directory entries when browsing the file system
export interface VaultEntry {
  name: string;               // Base file or folder name
  path: string;               // Relative path from vault root
  type: "file" | "directory"; // Discriminated union for folder vs file rendering
  size?: number;              // File size in bytes (omitted for directories)
  mtime?: number;             // Last modified timestamp in seconds since epoch
  has_audio: boolean;         // True if a companion synthesized podcast .mp3 exists
}

// ── Helpers ───────────────────────────────────────────────────

// Error subclass carrying the HTTP status + parsed FastAPI `detail`, so callers can branch on codes
// (e.g. HITL 409 `stale_base`) instead of string-matching messages. `extends Error` keeps `instanceof Error` true.
export class ApiError extends Error {
  status: number;   // HTTP status code (e.g. 404, 409)
  detail: unknown;  // Parsed `detail` field (string or structured object); `unknown` forces callers to narrow first
  constructor(status: number, detail: unknown, rawText: string) {
    super(`API ${status}: ${rawText}`); // Same message format as before, so existing error banners are unchanged
    this.status = status;
    this.detail = detail;
  }
}

// Generic fetch wrapper providing uniform error handling, JSON serialization, and typing
// <T>: Generic type parameter representing the expected shape of the response JSON (e.g., AgentStatus[], Conversation)
// RequestInit: Built-in TypeScript interface for fetch options (method, headers, body, signal)
// Promise<T>: Asynchronous handle that resolves with the parsed JSON data of type T
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  // await: Pauses function execution non-blockingly until the HTTP request completes
  // ...init: Object spread operator copying user-provided options into the request configuration
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  // res.ok: Returns true if HTTP status code is in the 200-299 range
  if (!res.ok) {
    const detail = await res.text(); // Read raw server error text (FastAPI error detail)
    let parsed: unknown = detail;
    // FastAPI errors are JSON `{"detail": ...}`; fall back to raw text if the body isn't JSON (e.g. proxy HTML)
    try { parsed = JSON.parse(detail)?.detail ?? detail; } catch { /* non-JSON body: keep raw text */ }
    throw new ApiError(res.status, parsed, detail);
  }

  // Type assertion 'as Promise<T>' casts the generic JSON result to the caller's expected interface
  return res.json() as Promise<T>;
}

// ── Endpoints ─────────────────────────────────────────────────

// Checks API liveness and engine version
export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/health");
}

// Retrieves runtime status for all registered swarm agents
export async function getAgentStatus(): Promise<AgentStatus[]> {
  return apiFetch<AgentStatus[]>("/api/agents/status");
}

// Synchronous one-shot query execution through the Content Router
export async function askBrain(query: string, conversationId: string): Promise<AskResponse> {
  return apiFetch<AskResponse>("/api/agents/ask", {
    method: "POST",
    body: JSON.stringify({ query, conversation_id: conversationId }),
  });
}

// Loads historical messages for a specific conversation thread
// encodeURIComponent: Sanitizes query params to prevent URL syntax breakage
export async function getChatHistory(conversationId: string): Promise<ChatHistoryEntry[]> {
  return apiFetch<ChatHistoryEntry[]>(`/api/agents/ask/history?conversation_id=${encodeURIComponent(conversationId)}`);
}

// Lists all active conversation threads for the UI sidebar
export async function getConversations(): Promise<Conversation[]> {
  return apiFetch<Conversation[]>("/api/agents/ask/conversations");
}

// Creates a new conversation thread entry in chats.db
export async function createConversation(title: string = "New Chat"): Promise<{ conversation_id: string }> {
  return apiFetch<{ conversation_id: string }>("/api/agents/ask/conversations", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

// Deletes a conversation thread and its associated message rows via cascade
export async function deleteConversation(conversationId: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/api/agents/ask/conversations/${conversationId}`, {
    method: "DELETE",
  });
}

// Updates the display title of an existing conversation thread
export async function updateConversationTitle(conversationId: string, title: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/api/agents/ask/conversations/${conversationId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

// Clears sticky agent routing for a conversation to force the next message back through the Content Router
export async function resetConversationRouting(conversationId: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/api/agents/ask/conversations/${conversationId}/reset`, {
    method: "POST",
  });
}

// ── SSE Streaming Types & Client ──────────────────────────────

// Discriminated union of trace events emitted during live agent graph execution
export interface TraceEvent {
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
  agent?: string;                   // Originating agent name (e.g. "Router", "CareerAgent")
  color?: string;                   // Terminal/UI theme color (e.g. "yellow", "cyan")
  message: string;                  // User-facing log text for the Thinking Panel
  timestamp: string;                // ISO-8601 UTC event timestamp
  data?: Record<string, unknown>;   // Optional structured payload (e.g. tool arguments)
  // Payload fields populated only on the final "done" event:
  response?: string;                // Final Markdown answer from the assistant
  domain?: string | null;           // Routed domain category
  confidence?: number | null;       // Classification confidence
  reasoning?: string | null;        // Router rationale
}

/**
 * Streams trace events from POST /api/agents/ask/stream via Server-Sent Events (SSE).
 * Uses fetch + ReadableStream (rather than standard browser EventSource) to allow sending JSON POST bodies.
 *
 * @param query The user's input prompt.
 * @param conversationId The target conversation UUID for sticky state and message persistence.
 * @param callbacks Event listeners for streaming updates, stream completion, and errors.
 * @returns An abort function that immediately terminates the active HTTP stream.
 */
export function askBrainStream(
  query: string,
  conversationId: string,
  callbacks: {
    onTrace: (event: TraceEvent) => void;
    onDone: (event: TraceEvent) => void;
    onError: (error: string) => void;
  }
): () => void {
  // AbortController allows canceling the fetch request if the user navigates away or cancels
  const controller = new AbortController();

  // Immediately-Invoked Async Function Expression (IIFE) to run async streaming logic
  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/agents/ask/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, conversation_id: conversationId }),
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

// Fetches the structured tree of vault directories
export async function getVaultStructure(
  path?: string
): Promise<VaultStructureResponse> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch<VaultStructureResponse>(`/api/vault/structure${params}`);
}

// Interface representing a pending file modification in the HITL transaction queue
export interface Transaction {
  id: number;                 // Auto-incrementing primary key in hitl.db
  agent_name: string;         // Agent that proposed the write (e.g. "CareerAgent")
  action_type: string;        // Type of modification (e.g. "write_file", "append_note")
  target_file: string;        // Absolute or vault-relative path to target file
  original_content: string | null; // Previous file content (for pre-commit diff preview)
  proposed_content: string;   // New content drafted by the agent
  reasoning: string | null;   // Plain-English explanation of why change is needed
  status: string;             // "pending" | "approved" | "rejected" | "rolled_back" | "superseded"
  created_at: string;         // ISO-8601 creation timestamp
}

// Structured 409 body returned when approve/rollback/rebase hits a commit-integrity conflict
export interface HitlConflictDetail {
  code: "stale_base" | "merge_conflict"; // stale_base = disk drifted; merge_conflict = rebase edits overlap
  message: string;                       // Human-readable explanation from the engine
  current_content?: string | null;       // Current disk text (stale_base only); null if the note was deleted
}

// Type guard: narrows an unknown `ApiError.detail` to HitlConflictDetail (`detail is X` tells TS the check's meaning)
export function isHitlConflict(detail: unknown): detail is HitlConflictDetail {
  return typeof detail === "object" && detail !== null && "code" in detail;
}

// Lightweight row from the `revisions` snapshot ledger, used for the Undo list
export interface HitlRevision {
  id: number;                 // Revision primary key
  tx_id: number;              // Transaction that produced this write
  target_file: string;        // Vault-relative path that was written
  rolled_back: number;        // 0 = live, 1 = already undone (SQLite has no boolean type)
  created_at: string;         // When the approval was applied
  rolled_back_at: string | null;
  agent_name: string;
  action_type: string;
  reasoning: string | null;
}

// Result returned by approve / rollback
interface HitlCommitResult {
  status: string;
  message: string;
  revision_id: number;
  target_file: string;
  forced: boolean;            // True only if a real conflict was overridden with force
}

// Loads full note content for display in the Vault Browser
export async function getNote(path: string): Promise<NoteContentResponse> {
  return apiFetch<NoteContentResponse>(
    `/api/vault/note?path=${encodeURIComponent(path)}`
  );
}

// Lists all uncommitted changes awaiting human approval in the HITL panel
export async function getPendingHitl(): Promise<Transaction[]> {
  return apiFetch<Transaction[]>("/api/hitl/pending");
}

// Commits a pending transaction to disk (Phase 2 of Two-Phase Commit)
// force=true overrides a 409 stale_base conflict (prior disk content is still snapshotted for Undo)
export async function approveHitl(id: number, force = false): Promise<HitlCommitResult> {
  return apiFetch<HitlCommitResult>(`/api/hitl/${id}/approve${force ? "?force=true" : ""}`, { method: "POST" });
}

// Discards a pending transaction without applying changes to disk
export async function rejectHitl(id: number): Promise<{ status: string, message: string }> {
  return apiFetch<{ status: string, message: string }>(`/api/hitl/${id}/reject`, { method: "POST" });
}

// Restores an approved note to its pre-approval snapshot (409 if edited since approval unless force=true)
export async function rollbackHitl(id: number, force = false): Promise<HitlCommitResult> {
  return apiFetch<HitlCommitResult>(`/api/hitl/${id}/rollback${force ? "?force=true" : ""}`, { method: "POST" });
}

// Re-stages a stale pending edit on top of the current disk text via 3-way merge (409 merge_conflict on overlap)
export async function rebaseHitl(id: number): Promise<{ status: string; rebased: boolean; message: string }> {
  return apiFetch<{ status: string; rebased: boolean; message: string }>(`/api/hitl/${id}/rebase`, { method: "POST" });
}

// Lists recently applied revisions (newest first) for the Undo list
export async function getRecentRevisions(limit = 10): Promise<HitlRevision[]> {
  return apiFetch<HitlRevision[]>(`/api/hitl/revisions/recent?limit=${limit}`);
}

// Lists files and subfolders within a specific vault directory path
export async function listVault(path?: string): Promise<VaultEntry[]> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch<VaultEntry[]>(`/api/vault/list${params}`);
}

// Triggers background TTS podcast audio generation for a specific markdown note
export async function generatePodcast(path: string, force: boolean = false): Promise<any> {
  return apiFetch<any>("/api/vault/podcast/generate", {
    method: "POST",
    body: JSON.stringify({ path, force }),
  });
}

// Formats direct audio streaming URL for playing note podcasts in the browser
export function getPodcastAudioUrl(path: string): string {
  return `${API_BASE}/api/vault/podcast/download?path=${encodeURIComponent(path)}`;
}

// ── Shared Inter-Agent Blackboard / Bulletin Board (`/api/board`) ───────

// Interface representing a single bulletin posted by a Flash subagent or Astra on `blackboard.db`
export interface BoardBulletin {
  id: number;                 // Auto-incrementing primary key in `blackboard.db`
  author: string;             // Originating agent label (e.g. "Subagent (low)", "Flash: Gmail Sweep", "Astra")
  channel: string;            // Semantic channel tag ("email", "calendar", "vault", "mission", "general")
  title: string;              // Concise summary headline
  content: string;            // Full Markdown findings payload
  pinned: number;             // 1 if pinned to top of board, else 0
  created_at: string;         // SQLite UTC/local timestamp string
}

// Fetches recent bulletins from the Shared Agent Blackboard, optionally filtered by channel
export async function getBoardBulletins(channel?: string, limit: number = 25): Promise<{ bulletins: BoardBulletin[]; count: number }> {
  const params = new URLSearchParams();
  if (channel && channel !== "all") params.set("channel", channel);
  params.set("limit", String(limit));
  return apiFetch<{ bulletins: BoardBulletin[]; count: number }>(`/api/board?${params.toString()}`);
}

// Deletes a single bulletin by ID
export async function deleteBoardBulletin(bulletinId: number): Promise<{ status: string; deleted_id: number }> {
  return apiFetch<{ status: string; deleted_id: number }>(`/api/board/${bulletinId}`, {
    method: "DELETE",
  });
}

// Clears unpinned bulletins (or all bulletins in a specific channel)
export async function clearBoardBulletins(channel?: string): Promise<{ status: string; deleted_count: number }> {
  const query = channel && channel !== "all" ? `?channel=${encodeURIComponent(channel)}` : "";
  return apiFetch<{ status: string; deleted_count: number }>(`/api/board${query}`, {
    method: "DELETE",
  });
}
