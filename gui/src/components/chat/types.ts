/**
 * types.ts — Shared TypeScript interfaces, localStorage keys, fallback model catalog,
 * and trace inspection helpers for the Nexus Chat interface (`/chat`).
 */

import type { ModelOption, TraceEvent } from "@/lib/api";

// Message: represents a single user prompt or assistant response rendered in the chat thread
// - role: union literal type restricting sender identity to "user" or "assistant"
// - content: raw UTF-8 Markdown text of the message
// - timestamp: JavaScript Date instance used for local HH:MM formatting
// - agent: optional backend agent identifier (e.g., "nexus", "career", "librarian")
// - domain: optional classified knowledge domain returned by the orchestrator
// - confidence: optional router confidence score (0.0 to 1.0)
// - modelTier: capability tier executed for this turn ("strong", "medium", "low")
// - modelName: concrete LLM identifier (e.g., "gemini-4-argon", "gemini-3.8-flash")
// - trace: optional array of lossless SSE TraceEvent payloads for ThinkingPanel inspection
export interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  agent?: string;
  domain?: string | null;
  confidence?: number | null;
  modelTier?: string | null;
  modelName?: string | null;
  trace?: TraceEvent[];
}

// LocalStorage key for remembering the user's selected model tier across page reloads
export const MODEL_STORAGE_KEY = "nexus_chat_model_tier";

// LocalStorage key for preserving unsubmitted chat prompt drafts across Nexus tab navigation and reloads
export const CHAT_DRAFT_STORAGE_KEY = "nexus_chat_input_draft";

// LocalStorage key for remembering the active conversation ID across Nexus tab navigation
export const ACTIVE_CONV_STORAGE_KEY = "nexus_chat_active_conv_id";

// Immediate fallback catalog rendered before GET /api/agents/models resolves
export const FALLBACK_MODELS: ModelOption[] = [
  {
    id: "strong",
    tier: "strong",
    model_name: "gemini-4-argon",
    label: "Strong (gemini-4-argon)",
    short_label: "Strong",
    description: "Deep reasoning & complex synthesis — Astra (gemini-4-argon)",
  },
  {
    id: "low",
    tier: "low",
    model_name: "gemini-3.8-flash",
    label: "Fast (gemini-3.8-flash)",
    short_label: "Fast",
    description: "High-speed, low-cost execution — Flash (gemini-3.8-flash)",
  },
];

// Extracts the model tier and model name executed during a turn from either explicit fields or persisted trace events
export function extractTurnModelInfo(
  trace?: TraceEvent[],
  explicitTier?: string | null,
  explicitModel?: string | null
): { modelTier: string | null; modelName: string | null } {
  // Fast-path: if explicit tier or model name metadata is already provided on the payload, return it directly
  // Uses nullish coalescing (`??`) to normalize `undefined` values to `null`
  if (explicitTier || explicitModel) {
    return { modelTier: explicitTier ?? null, modelName: explicitModel ?? null };
  }
  if (!trace || trace.length === 0) {
    return { modelTier: null, modelName: null };
  }
  // Inspect root NexusAgent `agent_start` or `llm_call` trace events for `model_tier` and `model_name` metadata
  for (const evt of trace) {
    const isRoot =
      !evt.parent_id &&
      (evt.agent_id === "nexus" || evt.agent === "NexusAgent" || !evt.agent_id);
    if (isRoot && (evt.type === "agent_start" || evt.type === "llm_call") && evt.data) {
      const tier = typeof evt.data.model_tier === "string" ? evt.data.model_tier : null;
      const name = typeof evt.data.model_name === "string" ? evt.data.model_name : null;
      if (tier || name) {
        return { modelTier: tier, modelName: name };
      }
    }
  }
  return { modelTier: null, modelName: null };
}

