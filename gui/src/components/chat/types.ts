/**
 * types.ts — Shared TypeScript interfaces, localStorage keys, fallback model catalog,
 * and trace inspection helpers for the Nexus Chat interface (`/chat`).
 */

import type { ChatHistoryEntry, ModelOption, TraceEvent } from "@/lib/api";

// Message: represents a single user prompt or assistant response rendered in the chat thread
// - role: union literal type restricting sender identity to "user" or "assistant"
// - content: raw UTF-8 Markdown text of the message
// - timestamp: JavaScript Date instance used for local HH:MM formatting
// - agent: optional backend agent identifier (e.g., "nexus", "career", "librarian")
// - domain: optional classified knowledge domain returned by the orchestrator
// - confidence: optional router confidence score (0.0 to 1.0)
// - modelTier: capability tier executed for this turn ("strong", "medium", "low")
// - modelName: concrete LLM identifier (e.g., "gemini-4-argon", "gemini-4-hydrogen")
// - costUsd: estimated USD inference cost for this execution turn
// - trace: optional array of lossless SSE TraceEvent payloads for ThinkingPanel inspection
// - hasTrace: whether this message has execution traces stored in message_traces (enables lazy on-demand load)
// - images: optional array of attached image asset URLs or paths rendered in user message bubbles
export interface Message {
  id?: number;
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
  hasTrace?: boolean;
  images?: string[];
}

// LocalStorage key for remembering the user's selected model tier across page reloads
export const MODEL_STORAGE_KEY = "nexus_chat_model_tier";

// Central migration table mapping retired/legacy model option IDs (in localStorage or legacy chats.db records) to current catalog IDs
export const RETIRED_MODEL_REPLACEMENTS: Record<string, string> = {
  "claude-sonnet-4-5": "claude-sonnet-5-5",
  "claude-sonnet-4.5": "claude-sonnet-5-5",
  "claude-opus-4-5": "claude-opus-5-5",
  "claude-opus-4.5": "claude-opus-5-5",
  "gemini-4-hydrogen": "medium",
};

// Local calendar cutoff for Gemini 4 Argon promotional pricing expiry (2026-12-01)
const ARGON_PROMO_END_MS = new Date(2026, 11, 1).getTime();

function isArgonStandardPricingActive(): boolean {
  return Date.now() >= ARGON_PROMO_END_MS;
}

// LocalStorage key for preserving unsubmitted chat prompt drafts across Nexus tab navigation and reloads (legacy single-draft key)
export const CHAT_DRAFT_STORAGE_KEY = "nexus_chat_input_draft";

// LocalStorage key for preserving unsubmitted chat drafts mapped by conversation ID (and "_new" for fresh threads)
export const CHAT_DRAFTS_STORAGE_KEY = "nexus_chat_drafts";

// Special draft dictionary key representing an unpersisted new chat draft
export const DRAFT_NEW_KEY = "_new";

// ChatDraftMap: Type alias for an unsubmitted draft dictionary mapping conversation ID strings (or "_new") to text content
export type ChatDraftMap = Record<string, string>;

/**
 * Loads the draft dictionary from localStorage, gracefully handling parsing errors,
 * restricted browser environments, and migrating legacy single-draft storage.
 * 
 * - Returns: `ChatDraftMap` containing all saved conversation drafts.
 */
export function loadPersistedDrafts(): ChatDraftMap {
  try {
    const raw = localStorage.getItem(CHAT_DRAFTS_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      // Ensure the parsed JSON is a non-null, non-array object
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as ChatDraftMap;
      }
    }
    // Backward compatibility: migrate legacy single-key draft if present
    const legacy = localStorage.getItem(CHAT_DRAFT_STORAGE_KEY);
    if (legacy && legacy.trim()) {
      const activeConv = localStorage.getItem(ACTIVE_CONV_STORAGE_KEY);
      const key = activeConv && activeConv !== "__new__" ? activeConv : DRAFT_NEW_KEY;
      const initial: ChatDraftMap = { [key]: legacy };
      try {
        localStorage.setItem(CHAT_DRAFTS_STORAGE_KEY, JSON.stringify(initial));
        localStorage.removeItem(CHAT_DRAFT_STORAGE_KEY);
      } catch {
        // Ignore quota/privacy errors in restricted contexts
      }
      return initial;
    }
  } catch {
    // Gracefully ignore storage quota / access errors in private browsing contexts
  }
  return {};
}

/**
 * Persists the entire draft dictionary to localStorage, removing keys with empty values,
 * or removing the storage entry entirely if no drafts remain.
 * 
 * - drafts: `ChatDraftMap` containing current active drafts mapped by conversation ID or `_new`.
 */
export function persistDrafts(drafts: ChatDraftMap): void {
  try {
    // Clean up empty or whitespace-only drafts before serializing to minimize localStorage footprint
    const cleaned: ChatDraftMap = {};
    for (const [key, val] of Object.entries(drafts)) {
      if (val && val.trim().length > 0) {
        cleaned[key] = val;
      }
    }
    if (Object.keys(cleaned).length > 0) {
      localStorage.setItem(CHAT_DRAFTS_STORAGE_KEY, JSON.stringify(cleaned));
    } else {
      localStorage.removeItem(CHAT_DRAFTS_STORAGE_KEY);
    }
  } catch {
    // Gracefully ignore storage quota / access errors in private browsing contexts
  }
}

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

// Immediate fallback catalog rendered before GET /api/agents/models resolves (mirrors `constants.py` & `cost.py`)
export const FALLBACK_MODELS: ModelOption[] = [
  {
    id: "strong",
    tier: "strong",
    provider: "gemini",
    model_name: "gemini-4-argon",
    label: "Gemini 4 Argon",
    short_label: "Argon",
    description:
      "Deep multi-step reasoning, cross-document synthesis, and hard analytical problems.",
    pricing: isArgonStandardPricingActive()
      ? {
          input_per_m: 4.0,
          output_per_m: 20.0,
          cached_per_m: 0.2,
          summary: "$4 / $20",
          note: null,
        }
      : {
          input_per_m: 2.0,
          output_per_m: 10.0,
          cached_per_m: 0.1,
          summary: "$2 / $10",
          note: "$4/$20 Dec 1",
        },
  },
  {
    id: "medium",
    tier: "medium",
    provider: "gemini",
    model_name: "gemini-4-hydrogen",
    label: "Gemini 4 Hydrogen",
    short_label: "Hydrogen",
    description:
      "Everyday coding, fast tool loops, and large-context work at mid-tier cost.",
    pricing: {
      input_per_m: 1.5,
      output_per_m: 7.5,
      cached_per_m: 0.075,
      summary: "$1.50 / $7.50",
      note: null,
    },
  },
  {
    id: "low",
    tier: "low",
    provider: "gemini",
    model_name: "gemini-3.8-flash",
    label: "Gemini 3.8 Flash",
    short_label: "Flash",
    description:
      "Quick lookups, routine summaries, and fast multimodal tasks on Gemini.",
    pricing: {
      input_per_m: 0.75,
      output_per_m: 3.75,
      cached_per_m: 0.075,
      summary: "$0.75 / $3.75",
      note: "$1.50/$7.50 Jan 1",
    },
  },
  {
    id: "claude-opus-5-5",
    tier: "strong",
    provider: "anthropic",
    model_name: "claude-opus-5-5",
    label: "Claude Opus 5.5",
    short_label: "Opus 5.5",
    description:
      "Flagship autonomous coding, nuanced writing, and high-stakes tasks.",
    pricing: {
      input_per_m: 4.0,
      output_per_m: 20.0,
      cached_per_m: 0.2,
      summary: "$4 / $20",
      note: null,
    },
  },
  {
    id: "claude-sonnet-5-5",
    tier: "medium",
    provider: "anthropic",
    model_name: "claude-sonnet-5-5",
    label: "Claude Sonnet 5.5",
    short_label: "Sonnet 5.5",
    description:
      "Balanced everyday drafting, coding, and reasoning at half Opus cost.",
    pricing: {
      input_per_m: 2.0,
      output_per_m: 10.0,
      cached_per_m: 0.1,
      summary: "$2 / $10",
      note: null,
    },
  },
  {
    id: "claude-haiku-5-5",
    tier: "low",
    provider: "anthropic",
    model_name: "claude-haiku-5-5",
    label: "Claude Haiku 5.5",
    short_label: "Haiku 5.5",
    description:
      "Near-instant, ultra-cheap replies, formatting, tagging, and light search.",
    pricing: {
      input_per_m: 0.1,
      output_per_m: 0.5,
      cached_per_m: 0.01,
      summary: "$0.10 / $0.50",
      note: "5× >100K",
    },
  },
];

// RunModelRef: lightweight metadata describing an active or fallback turn's model selection
// - tier: normalized capability tier ("strong" | "medium" | "low") or dropdown option ID (e.g. "claude-haiku-5-5")
// - name: concrete backend model identifier (e.g. "claude-haiku-5-5", "gemini-3.8-flash")
// - label: optional server-formatted display label (e.g. "Fast · claude-haiku-5-5")
export interface RunModelRef {
  tier?: string | null;
  name?: string | null;
  label?: string | null;
}

/**
 * Resolves a `ModelOption` from the catalog by prioritizing concrete model name over tier ID.
 * Why: Gemini entries use tier strings as their option `id` (`"strong"`, `"low"`), whereas Anthropic
 * entries use model IDs (`"claude-opus-5-5"`, `"claude-haiku-5-5"`) with `tier: "strong" | "low"`.
 * A single `.find()` checking `m.model_name === ref.name || m.id === ref.tier` short-circuits on
 * Gemini's `"low"` / `"strong"` entry first and mislabels Anthropic turns.
 *
 * - modelOptions: Ordered `ModelOption[]` catalog from `GET /api/agents/models` (or `FALLBACK_MODELS`).
 * - ref: Optional model reference carrying `name` and/or `tier` (`Pick<RunModelRef, "name" | "tier">`).
 * - Returns: Matching `ModelOption` if found, or `undefined`.
 */
export function resolveModelOption(
  modelOptions: ModelOption[],
  ref?: Pick<RunModelRef, "name" | "tier"> | null
): ModelOption | undefined {
  if (!ref) return undefined;
  // Pass 1: When a concrete model name is present, match only by `model_name` or `id` — never fall back to `tier`
  // so an unlisted/custom model is never misattributed to a different provider sharing the same capability tier.
  if (ref.name) {
    return modelOptions.find((m) => m.model_name === ref.name || m.id === ref.name);
  }
  // Pass 2: Only when no concrete model name exists, resolve by option `id` (e.g. `"strong"`, `"low"`).
  if (ref.tier) {
    return modelOptions.find((m) => m.id === ref.tier);
  }
  return undefined;
}

/**
 * Resolves a conversation's remembered `(modelName, modelTier)` to a selectable dropdown `ModelOption.id`.
 * Prioritizes concrete model names (plus retired 4.5 -> 5.5 migrations) and never falls back to `tier`
 * when an explicit `name` is present so unlisted/other-provider models are never misattributed.
 *
 * - modelOptions: Ordered `ModelOption[]` catalog from `GET /api/agents/models` (or `FALLBACK_MODELS`).
 * - ref: Optional remembered model reference (`Pick<RunModelRef, "name" | "tier">`).
 * - Returns: Matching `ModelOption.id` string (e.g. `"strong"`, `"gemini-4-hydrogen"`, `"claude-haiku-5-5"`), or `null`.
 */
export function resolveConversationModelSelection(
  modelOptions: ModelOption[],
  ref?: Pick<RunModelRef, "name" | "tier"> | null
): string | null {
  if (!ref || modelOptions.length === 0) return null;
  const trimmedName = ref.name?.trim() || null;
  const trimmedTier = ref.tier?.trim() || null;
  if (!trimmedName && !trimmedTier) return null;

  // Pass 1: Direct name-first lookup via shared `resolveModelOption`
  const direct = resolveModelOption(modelOptions, { name: trimmedName, tier: trimmedTier });
  if (direct) return direct.id;

  // Pass 2: When a concrete name exists, check retired-model migrations and case-insensitive exact IDs;
  // deliberately return `null` on miss so cross-provider tier names never match the wrong provider
  if (trimmedName) {
    const lowerName = trimmedName.toLowerCase();
    const replaced = RETIRED_MODEL_REPLACEMENTS[lowerName];
    if (replaced) {
      const migrated = modelOptions.find((m) => m.model_name === replaced || m.id === replaced);
      if (migrated) return migrated.id;
    }
    const caseInsensitive = modelOptions.find(
      (m) => m.model_name.toLowerCase() === lowerName || m.id.toLowerCase() === lowerName
    );
    return caseInsensitive ? caseInsensitive.id : null;
  }

  // Pass 3: Tier-only legacy fallback (only reached when `trimmedName` is absent)
  if (trimmedTier) {
    const lowerTier = trimmedTier.toLowerCase();
    const replaced = RETIRED_MODEL_REPLACEMENTS[lowerTier];
    if (replaced) {
      const migrated = modelOptions.find((m) => m.model_name === replaced || m.id === replaced);
      if (migrated) return migrated.id;
    }
    const caseInsensitiveTier = modelOptions.find((m) => m.id.toLowerCase() === lowerTier);
    return caseInsensitiveTier ? caseInsensitiveTier.id : null;
  }

  return null;
}

/**
 * Scans raw `ChatHistoryEntry[]` in reverse chronological order to find the newest message
 * carrying model metadata (checking explicit SQLite columns first, then persisted trace events).
 * Skips trailing synthetic entries (`branch_merge`, `branch_context`) that have no model attribution.
 *
 * - history: Chronological `ChatHistoryEntry[]` loaded from `GET /api/agents/ask/history`.
 * - Returns: `{ name, tier }` of the last used model, or `null` if no message records model metadata.
 */
export function extractLastUsedModelFromHistory(
  history: ChatHistoryEntry[]
): Pick<RunModelRef, "name" | "tier"> | null {
  for (let i = history.length - 1; i >= 0; i--) {
    const entry = history[i];
    const extracted = extractTurnModelInfo(entry.trace);
    const modelName = entry.model_name ?? extracted.modelName;
    const modelTier = entry.model_tier ?? extracted.modelTier;
    if (modelName || modelTier) {
      return { name: modelName, tier: modelTier };
    }
  }
  return null;
}

/**
 * Resolves the human-readable model label displayed in the live streaming status banner.
 *
 * - activeRunModel: Active streaming/re-attached turn's model metadata, or `null` when idle.
 * - modelOptions: Ordered `ModelOption[]` catalog used to look up friendly UI labels.
 * - fallbackLabel: Selected composer model label used if no active run metadata is present.
 * - Returns: Human-readable model label (e.g. `"Claude Haiku 5.5"`).
 */
export function resolveLiveModelLabel(
  activeRunModel: RunModelRef | null,
  modelOptions: ModelOption[],
  fallbackLabel: string
): string {
  if (!activeRunModel) return fallbackLabel;
  const matched = resolveModelOption(modelOptions, activeRunModel);
  // Nullish coalescing (`??`) falls back through catalog label -> server label -> raw model name -> composer label
  return matched?.label ?? activeRunModel.label ?? activeRunModel.name ?? fallbackLabel;
}

// Human-readable display labels for retired or non-catalog model identifiers stored in historical message records
const LEGACY_MODEL_LABELS: Record<string, string> = {
  "claude-opus-4-5": "Claude Opus 4.5",
  "claude-sonnet-4-5": "Claude Sonnet 4.5",
  "gpt-5.6-sol": "GPT-5.6 Sol",
  "gpt-5.6-terra": "GPT-5.6 Terra",
  "gpt-5.4-mini": "GPT-5.4 Mini",
};

/**
 * Formats a concrete model name or tier into a clean uppercase badge label for message metadata pills.
 * Resolves catalog labels via `resolveModelOption` first, then legacy aliases, then slug humanization.
 *
 * - modelName: Concrete backend model identifier (e.g., `"claude-haiku-5-5"`).
 * - modelTier: Capability tier fallback (`"strong"`, `"medium"`, `"low"`) when `modelName` is absent.
 * - modelOptions: Ordered `ModelOption[]` catalog used for friendly label lookup (defaults to `FALLBACK_MODELS`).
 * - Returns: Uppercase display label (e.g., `"CLAUDE HAIKU 5.5"`), or `null` when both inputs are empty.
 */
export function formatModelBadgeLabel(
  modelName?: string | null,
  modelTier?: string | null,
  modelOptions: ModelOption[] = FALLBACK_MODELS
): string | null {
  if (!modelName && !modelTier) return null;

  // Match concrete model name first so cross-provider tiers (e.g. Anthropic "low" vs Gemini "low") never collide
  const matched = resolveModelOption(modelOptions, { name: modelName, tier: modelTier });
  if (matched?.label) {
    return matched.label.toUpperCase();
  }

  const trimmedName = modelName?.trim();
  if (trimmedName) {
    const legacyLabel = LEGACY_MODEL_LABELS[trimmedName.toLowerCase()];
    if (legacyLabel) {
      return legacyLabel.toUpperCase();
    }
    // Convert dashed version suffixes (`-2-5`) to dotted notation (` 2.5`) and remaining separators to spaces
    return trimmedName
      .replace(/-(\d+)-(\d+)(?=$|-)/g, " $1.$2")
      .replace(/[-_]+/g, " ")
      .toUpperCase();
  }

  const trimmedTier = modelTier?.trim();
  return trimmedTier ? trimmedTier.toUpperCase() : null;
}

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
    const isOpus45 = lowerName.includes("opus-4") || lowerName.includes("opus 4");
    const isOpus = lowerName.includes("opus");
    const isSonnet45 = lowerName.includes("sonnet-4") || lowerName.includes("sonnet 4");
    const isSonnet = lowerName.includes("sonnet");
    const isHaiku = lowerName.includes("haiku");
    // Default active "low" tier to Gemini 3.8 Flash ($0.75/$0.075/$3.75), "medium" to Hydrogen ($1.50/$0.075/$7.50),
    // and "strong" to Argon (promo $2/$0.10/$10 before Dec 1, 2026; standard $4/$0.20/$20 starting Dec 1).
    const isHydrogen =
      lowerName.includes("hydrogen") ||
      (!lowerName && modelTier === "medium");
    const isFlash = lowerName.includes("flash") || (modelTier === "low" && !isHydrogen && !isSonnet && !isOpus && !isHaiku);

    // Claude Haiku 5.5 steps up 5x above 100k input tokens ($0.10/$0.01/$0.50 -> $0.50/$0.05/$2.50)
    const isHaikuLongContext = isHaiku && totalIn > 100000;
    const haikuInRate = isHaikuLongContext ? 0.50 : 0.10;
    const haikuCachedRate = isHaikuLongContext ? 0.05 : 0.01;
    const haikuOutRate = isHaikuLongContext ? 2.50 : 0.50;
    const argonInRate = isArgonStandardPricingActive() ? 4.00 : 2.00;
    const argonCachedRate = isArgonStandardPricingActive() ? 0.20 : 0.10;
    const argonOutRate = isArgonStandardPricingActive() ? 20.00 : 10.00;

    // Resolve per-million-token pricing across Anthropic Claude and Google Gemini model families
    const inRate = isOpus45 ? 5.00 : isOpus ? 4.00 : isSonnet45 ? 3.00 : isSonnet ? 2.00 : isHaiku ? haikuInRate : isFlash ? 0.75 : isHydrogen ? 1.50 : argonInRate;
    const cachedRate = isOpus45 ? 0.50 : isOpus ? 0.20 : isSonnet45 ? 0.30 : isSonnet ? 0.10 : isHaiku ? haikuCachedRate : isFlash ? 0.075 : isHydrogen ? 0.075 : argonCachedRate;
    const outRate = isOpus45 ? 25.00 : isOpus ? 20.00 : isSonnet45 ? 15.00 : isSonnet ? 10.00 : isHaiku ? haikuOutRate : isFlash ? 3.75 : isHydrogen ? 7.50 : argonOutRate;

    const uncachedIn = Math.max(0, totalIn - totalCached);
    const cost = ((uncachedIn * inRate) + (totalCached * cachedRate) + (totalOut * outRate)) / 1000000;
    return Math.round(cost * 10000) / 10000;
  }

  return null;
}

/**
 * Converts an array of raw `ChatHistoryEntry` records from `GET /api/agents/ask/history`
 * into enriched `Message` UI objects (preserving SQLite `id`, extracted model tier/name, and USD cost).
 */
export function mapHistoryEntriesToMessages(history: ChatHistoryEntry[]): Message[] {
  return history.map((entry) => {
    // Prefer explicit column values populated directly from SQLite messages row;
    // fall back to scanning entry.trace if working with legacy unmigrated payloads
    const extractedModel = extractTurnModelInfo(entry.trace);
    const modelTier = entry.model_tier ?? extractedModel.modelTier;
    const modelName = entry.model_name ?? extractedModel.modelName;
    const costUsd =
      (typeof entry.cost_usd === "number" ? entry.cost_usd : null) ??
      extractTurnCost(entry.trace, null, modelName, modelTier);
    const hasTrace = Boolean(entry.has_trace || (entry.trace && entry.trace.length > 0));

    return {
      id: entry.id,
      role: entry.role,
      content: entry.content,
      images: entry.images || [],
      agent: entry.agent,
      domain: entry.domain,
      confidence: entry.confidence,
      modelTier,
      modelName,
      costUsd,
      trace: entry.trace,
      hasTrace,
      timestamp: new Date(entry.timestamp),
    };
  });
}

/**
 * Formats a UUID or numeric database ID for compact display inside menu items.
 * - id: string | number — Full conversation UUID or numeric SQLite message ID.
 * - maxLen: number — Maximum character prefix before appending an ellipsis (`…`).
 * - Returns: Unchanged string if `<= maxLen`, otherwise `<prefix>…`.
 */
export function formatShortId(id: string | number, maxLen: number = 8): string {
  const raw = String(id);
  return raw.length <= maxLen ? raw : `${raw.slice(0, maxLen)}…`;
}

/**
 * Copies text to the system clipboard with a legacy `execCommand` fallback.
 * Why: `navigator.clipboard` requires a secure context (HTTPS or localhost), so plain HTTP
 * LAN / Tailscale sessions (`http://192.168.x.x:3000`, `http://100.x.x.x:3000`) fall back to an
 * offscreen `<textarea>` selection.
 * - text: string — Exact raw ID or text string to place on the clipboard.
 * - Returns: `Promise<boolean>` resolving to `true` if either copy strategy succeeded.
 */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  // Primary path: modern async Clipboard API (`Promise<void>` on secure contexts)
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall through to offscreen textarea fallback if permissions or origin checks fail
    }
  }

  // Fallback path: mount an offscreen textarea outside viewport to copy without layout shift
  if (typeof document === "undefined") return false;
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  textarea.style.left = "-9999px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);

  // Preserve previously focused element so keyboard focus is not stolen during copy
  const activeEl = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  try {
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(textarea);
    activeEl?.focus();
  }
}




