/**
 * agents.ts — Chat operations, conversation history, model catalog, and run telemetry.
 * Connects to FastAPI `/api/agents` routes.
 */

import { apiFetch, getApiBase } from "./client";
import type { TraceEvent } from "./stream";

// Interface for synchronous chat response returned by POST /api/agents/ask
export interface AskResponse {
  response: string;           // Final generated markdown text from the agent
  agent: string;              // The specific agent that answered (e.g. "nexus")
  domain: string | null;      // Classified knowledge domain (e.g. "career", "general")
  confidence: number | null;  // Router confidence score between 0.0 and 1.0
  reasoning: string | null;   // Explanation of why the router selected this agent
  model_tier?: string | null; // Effective model tier used for this turn ("strong", "medium", "low")
  model_name?: string | null; // Concrete provider model identifier (e.g. "gemini-4-argon", "gemini-3.8-flash")
  cost_usd?: number | null;   // Estimated USD inference cost for this execution turn
  timestamp: string;          // ISO-8601 timestamp of response generation
}

// Interface describing a single selectable model/tier option in the Chat UI
export interface ModelOption {
  id: string;                 // Selection key passed as `model_tier` (e.g. "strong", "low", "claude-opus-4-5", "claude-sonnet-4-5")
  tier: "low" | "medium" | "strong" | string; // Capability/cost tier
  provider?: string;          // LLM provider family ("gemini", "anthropic", "openai")
  model_name: string;         // Concrete LLM identifier (e.g. "gemini-4-argon", "claude-opus-4-5")
  label: string;              // Full dropdown label (e.g. "Strong (gemini-4-argon)", "Opus 4.5 (claude-opus-4-5)")
  short_label: string;        // Compact pill label (e.g. "Strong", "Fast", "Opus 4.5", "Sonnet 4.5")
  description: string;        // Tooltip/helper description of model strength and role
}

// Interface for the model catalog returned by GET /api/agents/models
export interface ModelsCatalogResponse {
  default_tier: string;       // Default tier configured in `.env` (`NEXUS_PRIMARY_TIER`)
  default_model: string;      // Concrete model name for the default tier
  provider: string;           // Active LLM provider ("gemini" or "openai")
  models: ModelOption[];      // Ordered list of selectable model options for each turn
}

// Interface for individual chat messages loaded from SQLite chats.db
export interface ChatHistoryEntry {
  id?: number;                // SQLite primary key (`messages.id`) used as deterministic branch anchor
  role: "user" | "assistant"; // Sender identifier determining bubble alignment & styling
  content: string;            // Raw markdown text of the message
  agent?: string;             // Optional agent name if sent by an AI assistant
  domain?: string | null;     // Optional domain classification
  confidence?: number | null; // Optional routing confidence score
  trace?: TraceEvent[];       // Optional array of execution steps for post-run inspection
  timestamp: string;          // ISO-8601 timestamp of message creation
  images?: string[];          // Optional array of attached image URLs or relative asset paths
}

// Interface representing a persistent conversation thread in the sidebar (with DAG branching lineage)
export interface Conversation {
  id: string;                            // UUID primary key linking to chats.db
  title: string;                         // User-visible thread title (e.g. "Career Outreach")
  active_agent?: string | null;          // Legacy sticky session agent (retained as optional for backward compatibility)
  created_at: string;                    // ISO-8601 creation timestamp
  last_updated: string;                  // ISO-8601 timestamp of last user/assistant message
  parent_conversation_id?: string | null;// Optional parent conversation UUID if spawned as a branch
  parent_message_id?: number | null;     // Optional SQLite `messages.id` in the parent where the fork occurred
  branch_mode?: "tangent" | "fork" | string | null; // Branching mode ('tangent' fresh ALU vs 'fork' full clone)
  merged_at?: string | null;             // ISO-8601 timestamp when distilled and merged back to parent
}

// Interface representing an isolated subagent lifecycle within a structured run snapshot
export interface SubagentRunRecord {
  agent_id: string;                 // Unique subagent identifier (e.g. "subagent-1")
  agent_name: string;               // Display name (e.g. "Subagent #1 (low)")
  parent_id: string | null;         // Parent orchestrator ID (typically "nexus")
  color: string;                    // Theme color assigned to this subagent
  model_tier: string;               // Model tier ("low", "medium", "strong")
  task_prompt: string;              // Full, untruncated task_prompt passed to spawn_subagent
  started_at: string | null;        // ISO-8601 UTC start timestamp
  ended_at: string | null;          // ISO-8601 UTC completion timestamp
  final_response: string | null;    // Full synthesis returned by the subagent
  cost_usd?: number | null;         // Estimated USD cost for this subagent's execution
  input_tokens?: number;            // Total prompt tokens evaluated by this subagent
  output_tokens?: number;           // Total completion tokens generated by this subagent
  cached_tokens?: number;           // Prompt tokens served from cache
  tool_calls: Array<{
    call_id?: string;
    tool?: string;
    args?: Record<string, unknown>;
    result?: string;
    timestamp?: string;
  }>;
  steps: TraceEvent[];              // Complete ordered trace steps executed inside this subagent
}

// Interface for lightweight run summaries returned by GET /api/agents/runs
export interface RunSummary {
  run_id: string;                   // 8-char UUID run identifier
  filename: string;                 // JSON filename on disk in logs/runs/
  timestamp: string;                // ISO-8601 UTC execution timestamp
  thread_id: string;                // Conversation thread UUID
  agent_name: string;               // Root agent name (e.g. "nexus")
  domain: string | null;            // Domain classification if applicable
  input_query: string;              // Full user query text
  output_response: string;          // Full assistant markdown response
  query_preview: string;            // Retained for backward compatibility
  response_preview: string;         // Retained for backward compatibility
  latency_seconds: number | null;   // Wall-clock execution time in seconds
  cost_usd?: number | null;         // Estimated USD inference cost
  tool_calls_count: number;         // Number of root tool calls executed
  subagents_count?: number;         // Number of isolated subagents spawned during the run
  trace_events_count?: number;      // Total telemetry trace steps emitted
  metadata?: Record<string, unknown>;
}

// Interface for full run snapshot details returned by GET /api/agents/runs/{run_id}
export interface RunSnapshot {
  run_id: string;
  timestamp: string;
  thread_id: string;
  agent_name: string;
  domain: string | null;
  confidence: number | null;
  reasoning: string | null;
  input_query: string;
  output_response: string;
  cost_usd?: number | null;
  latency_seconds: number | null;
  dpfh_injected_files: string[];
  tool_calls: Array<{
    id?: string;
    name: string;
    args: Record<string, unknown>;
    result?: string | null;
  }>;
  subagents_count?: number;
  subagents?: SubagentRunRecord[];
  trace_events_count: number;
  trace_events: TraceEvent[];
  metadata: Record<string, unknown>;
}

// Fetches selectable per-turn model tiers and active provider catalog from GET /api/agents/models
export async function getAvailableModels(): Promise<ModelsCatalogResponse> {
  return apiFetch<ModelsCatalogResponse>("/api/agents/models");
}

// Synchronous one-shot query execution through NexusAgent with optional per-turn model tier override
export async function askBrain(
  query: string,
  conversationId: string,
  modelTier?: string
): Promise<AskResponse> {
  return apiFetch<AskResponse>("/api/agents/ask", {
    method: "POST",
    body: JSON.stringify({
      query,
      conversation_id: conversationId,
      model_tier: modelTier,
    }),
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
// - conversationId: UUID string linking to chats.db record
// - title: new user-specified or edited thread title string
// Promise settles with `{ status: "updated", conversation_id, title }` on success
export async function updateConversationTitle(
  conversationId: string,
  title: string
): Promise<{ status: string; conversation_id?: string; title?: string }> {
  return apiFetch<{ status: string; conversation_id?: string; title?: string }>(
    `/api/agents/ask/conversations/${conversationId}`,
    {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }
  );
}

// Automatically generates a concise 3-6 word topic title using the low-tier model (Flash / Sonnet)
// - conversationId: target conversation thread to summarize and update in SQLite chats.db
// Promise settles with `{ status: "updated", conversation_id, title }`
export async function autoGenerateConversationTitle(
  conversationId: string
): Promise<{ status: string; conversation_id?: string; title?: string; fallback?: boolean }> {
  return apiFetch<{ status: string; conversation_id?: string; title?: string; fallback?: boolean }>(
    `/api/agents/ask/conversations/${conversationId}/auto-title`,
    {
      method: "POST",
    }
  );
}

// Fetches recent structured run summaries from logs/runs/
export async function getAgentRuns(limit = 50, agent?: string): Promise<RunSummary[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (agent) params.set("agent", agent);
  return apiFetch<RunSummary[]>(`/api/agents/runs?${params.toString()}`);
}

// Fetches a single complete, untruncated run snapshot by run_id or filename
export async function getAgentRun(runId: string): Promise<RunSnapshot> {
  return apiFetch<RunSnapshot>(`/api/agents/runs/${encodeURIComponent(runId)}`);
}

// Interface describing the JSON metadata returned by POST /api/agents/upload
// Supports single images as well as rasterized multi-page PDF documents
export interface UploadImageResponse {
  url: string;           // Relative URL endpoint (e.g. /api/agents/uploads/<uuid>.png)
  filename: string;      // Unique disk filename in logs/uploads/
  mime_type: string;     // MIME type (e.g. image/png, application/pdf)
  width: number;         // Resized/verified pixel width
  height: number;        // Resized/verified pixel height
  page_urls?: string[];  // For multi-page PDFs: array of all rendered page image URLs
  page_count?: number;   // Total page count for PDF documents
}

// Resolves a relative upload path, absolute URL, or base64 data URI to an absolute URL for <img> tags
export function resolveImageUrl(urlOrPath: string): string {
  if (!urlOrPath) return "";
  if (
    urlOrPath.startsWith("http://") ||
    urlOrPath.startsWith("https://") ||
    urlOrPath.startsWith("data:") ||
    urlOrPath.startsWith("blob:")
  ) {
    return urlOrPath;
  }
  const base = getApiBase();
  return `${base}${urlOrPath.startsWith("/") ? "" : "/"}${urlOrPath}`;
}

// Uploads a binary image file via multipart/form-data to POST /api/agents/upload
export async function uploadImage(file: File): Promise<UploadImageResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const base = getApiBase();
  const res = await fetch(`${base}/api/agents/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Upload failed (${res.status}): ${errText}`);
  }
  return res.json();
}

// Interface describing the JSON response returned by POST /api/agents/stop-and-revert
export interface StopAndRevertResponse {
  status: string;                  // Outcome status (e.g. "stopped_and_reverted")
  restored_query: string;          // User prompt text restored from the reverted turn
  restored_images?: string[];      // Attached image URLs restored from the reverted turn
  cancelled_hitl_count: number;    // Count of unapproved HITL mutations cancelled
  reverted_messages_count: number; // Count of messages purged from chats.db
}

/**
 * Halts any active agent execution for the target thread and rolls back all state:
 *   1. Signals the backend worker thread and LangGraph nodes to immediately stop.
 *   2. Cancels all unapproved pending HITL transactions (file creations, edits, moves, deletions).
 *   3. Rolls back LangGraph checkpointer SQLite database (`memory.sqlite`) to pre-turn state.
 *   4. Purges the turn's user and assistant messages from SQLite `chats.db`.
 *   5. Cleans up thread-scoped blackboard bulletins posted during the aborted turn.
 *   6. Restores the user's prompt text and attached images for immediate composer recovery.
 *
 * @param conversationId The UUID of the conversation thread to stop and revert.
 * @returns A promise resolving to the StopAndRevertResponse payload.
 */
export async function stopAndRevertTurn(
  conversationId: string
): Promise<StopAndRevertResponse> {
  return apiFetch<StopAndRevertResponse>("/api/agents/stop-and-revert", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId }),
  });
}



