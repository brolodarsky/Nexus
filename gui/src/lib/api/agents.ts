/**
 * agents.ts — Agent status, chat operations, conversation history, model catalog, and run telemetry.
 * Connects to FastAPI `/api/agents` routes.
 */

import { apiFetch } from "./client";
import type { TraceEvent } from "./stream";

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
  response: string;           // Final generated markdown text from the agent
  agent: string;              // The specific agent that answered (e.g. "nexus")
  domain: string | null;      // Classified knowledge domain (e.g. "career", "general")
  confidence: number | null;  // Router confidence score between 0.0 and 1.0
  reasoning: string | null;   // Explanation of why the router selected this agent
  model_tier?: string | null; // Effective model tier used for this turn ("strong", "medium", "low")
  model_name?: string | null; // Concrete provider model identifier (e.g. "gemini-4-argon", "gemini-3.8-flash")
  timestamp: string;          // ISO-8601 timestamp of response generation
}

// Interface describing a single selectable model/tier option in the Chat UI
export interface ModelOption {
  id: string;                 // Selection key passed as `model_tier` (e.g. "strong", "medium", "low")
  tier: "low" | "medium" | "strong" | string; // Capability/cost tier
  model_name: string;         // Concrete LLM identifier (e.g. "gemini-4-argon", "gemini-3.8-flash")
  label: string;              // Full dropdown label (e.g. "Strong (gemini-4-argon)")
  short_label: string;        // Compact pill label (e.g. "Strong", "Fast")
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

// Retrieves runtime status for all registered swarm agents
export async function getAgentStatus(): Promise<AgentStatus[]> {
  return apiFetch<AgentStatus[]>("/api/agents/status");
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

