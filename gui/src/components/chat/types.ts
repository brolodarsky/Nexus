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
// - costUsd: estimated USD inference cost for this execution turn
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
  costUsd?: number | null;
  trace?: TraceEvent[];
}

// LocalStorage key for remembering the user's selected model tier across page reloads
export const MODEL_STORAGE_KEY = "nexus_chat_model_tier";

// LocalStorage key for preserving unsubmitted chat prompt drafts across Nexus tab navigation and reloads
export const CHAT_DRAFT_STORAGE_KEY = "nexus_chat_input_draft";

// LocalStorage key for remembering the active conversation ID across Nexus tab navigation
export const ACTIVE_CONV_STORAGE_KEY = "nexus_chat_active_conv_id";

// LocalStorage key for persisting whether the left conversation history menu is collapsed across page navigation
export const CHAT_SIDEBAR_COLLAPSED_KEY = "nexus_chat_sidebar_collapsed";

// LocalStorage key for persisting the custom width of the chat sidebar in pixels across navigation
export const CHAT_SIDEBAR_WIDTH_KEY = "nexus_chat_sidebar_width";

// Default and boundary constraints for the resizable chat sidebar in pixels
export const DEFAULT_CHAT_SIDEBAR_WIDTH = 256;
export const MIN_CHAT_SIDEBAR_WIDTH = 200;
export const MAX_CHAT_SIDEBAR_WIDTH = 640;

// LocalStorage key for persisting whether the bottom message input bar is collapsed across page navigation
export const CHAT_INPUT_COLLAPSED_KEY = "nexus_chat_input_collapsed";

// LocalStorage key for persisting whether the right Subagent Blackboard drawer is open across page navigation
export const CHAT_BOARD_OPEN_KEY = "nexus_chat_board_open";

// Immediate fallback catalog rendered before GET /api/agents/models resolves
export const FALLBACK_MODELS: ModelOption[] = [
  {
    id: "strong",
    tier: "strong",
    provider: "gemini",
    model_name: "gemini-4-argon",
    label: "Strong (gemini-4-argon)",
    short_label: "Strong",
    description: "Deep reasoning & complex synthesis — Argon (gemini-4-argon)",
  },
  {
    id: "low",
    tier: "low",
    provider: "gemini",
    model_name: "gemini-3.8-flash",
    label: "Fast (gemini-3.8-flash)",
    short_label: "Fast",
    description: "High-speed, low-cost execution — Flash (gemini-3.8-flash)",
  },
  {
    id: "claude-opus-4-5",
    tier: "strong",
    provider: "anthropic",
    model_name: "claude-opus-4-5",
    label: "Opus 4.5 (claude-opus-4-5)",
    short_label: "Opus 4.5",
    description: "Anthropic deep reasoning & synthesis — Claude Opus 4.5 (claude-opus-4-5)",
  },
  {
    id: "claude-sonnet-4-5",
    tier: "low",
    provider: "anthropic",
    model_name: "claude-sonnet-4-5",
    label: "Sonnet 4.5 (claude-sonnet-4-5)",
    short_label: "Sonnet 4.5",
    description: "Anthropic fast, low-cost execution — Claude Sonnet 4.5 (claude-sonnet-4-5)",
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

// Extracts or calculates the estimated turn inference cost from explicit metadata or trace info events
export function extractTurnCost(
  trace?: TraceEvent[],
  explicitCost?: number | null,
  modelName?: string | null,
  modelTier?: string | null
): number | null {
  if (typeof explicitCost === "number" && !isNaN(explicitCost) && explicitCost > 0) {
    return explicitCost;
  }
  if (!trace || trace.length === 0) {
    return null;
  }

  let totalCost = 0.0;
  let foundExplicit = false;
  let totalIn = 0;
  let totalOut = 0;
  let totalCached = 0;

  for (const evt of trace) {
    if (evt.type === "info" && evt.data) {
      const d = evt.data as Record<string, unknown>;
      if (typeof d.cost_usd === "number" && !isNaN(d.cost_usd) && d.cost_usd > 0) {
        totalCost += d.cost_usd;
        foundExplicit = true;
      }
      if (typeof d.input_tokens === "number") {
        totalIn += d.input_tokens;
      }
      if (typeof d.output_tokens === "number") {
        totalOut += d.output_tokens;
      }
      if (typeof d.cached_tokens === "number") {
        totalCached += d.cached_tokens;
      }
    }
    if (evt.type === "info" && typeof evt.message === "string") {
      const m = evt.message.match(/Tokens:\s*([\d,]+)\s*in\s*\(([\d,]+)\s*cached.*?\)\s*\|\s*([\d,]+)\s*out/i);
      if (m && totalIn === 0 && totalOut === 0) {
        totalIn += parseInt(m[1].replace(/,/g, ""), 10) || 0;
        totalCached += parseInt(m[2].replace(/,/g, ""), 10) || 0;
        totalOut += parseInt(m[3].replace(/,/g, ""), 10) || 0;
      }
      const costM = evt.message.match(/~\$([\d.]+)/);
      if (costM && !foundExplicit) {
        totalCost += parseFloat(costM[1]);
        foundExplicit = true;
      }
    }
  }

  if (foundExplicit && totalCost > 0) {
    return Math.round(totalCost * 10000) / 10000;
  }

  // Calculate from accumulated tokens if explicit cost wasn't logged in legacy trace
  if (totalIn > 0 || totalOut > 0) {
    const lowerName = (modelName || "").toLowerCase();
    const isOpus = lowerName.includes("opus");
    const isSonnet = lowerName.includes("sonnet");
    const isLow = (modelTier === "low") || lowerName.includes("flash") || isSonnet;

    // Resolve per-million-token pricing across Anthropic Claude and Google Gemini model families
    const inRate = isOpus ? 5.00 : isSonnet ? 3.00 : isLow ? 0.10 : 1.25;
    const cachedRate = isOpus ? 0.50 : isSonnet ? 0.30 : isLow ? 0.025 : 0.3125;
    const outRate = isOpus ? 25.00 : isSonnet ? 15.00 : isLow ? 0.40 : 5.00;

    const uncachedIn = Math.max(0, totalIn - totalCached);
    const cost = ((uncachedIn * inRate) + (totalCached * cachedRate) + (totalOut * outRate)) / 1000000;
    return Math.round(cost * 10000) / 10000;
  }

  return null;
}


