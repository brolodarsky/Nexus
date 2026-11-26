"use client";

import { useState, useMemo, useRef, useEffect, useCallback, memo } from "react";
import type { TraceEvent } from "@/lib/api";
import {
  getMessageTrace,
  getTraceBlobContent,
  getTraceBlobsBatch,
  type ContextManifestEntry,
  type ContextSummary,
} from "@/lib/api/agents";
import MarkdownMessage from "@/components/MarkdownMessage";
import { buildToolCallPairMap, type ToolCallPairInfo } from "@/lib/traceToolPairing";

// Deterministic character-to-token estimator matching backend `approx_token_count()` (ceil(chars / 4))
export function estimateTokensFromChars(chars: number): number {
  if (!Number.isFinite(chars) || chars <= 0) return 0;
  return Math.ceil(chars / 4);
}

// Formats character length together with estimated token count (e.g. "31,424 chars · ~7,856 tok")
export function formatCharsAndTokens(chars: number): string {
  const safeChars = Number.isFinite(chars) && chars > 0 ? Math.floor(chars) : 0;
  return `${safeChars.toLocaleString()} chars · ~${estimateTokensFromChars(safeChars).toLocaleString()} tok`;
}

// ── Icon & Color Maps ────────────────────────────────────────────────────────

// Maps trace event discriminators to visual glyphs for timeline rows and graph nodes
export const TRACE_ICONS: Record<string, string> = {
  agent_start: "▶",
  agent_end: "■",
  llm_call: "🤖",
  llm_thinking: "🧠",
  llm_response: "💬",
  tool_call: "🔧",
  tool_result: "✅",
  tool_error: "❌",
  route: "🔀",
  delegate: "📤",
  info: "ℹ️",
};

// Maps backend ANSI color names to Tailwind text, border, and background classes
export const AGENT_THEME: Record<
  string,
  { text: string; border: string; bg: string; badge: string; stroke: string }
> = {
  cyan: {
    text: "text-cyan-400",
    border: "border-cyan-500/35",
    bg: "bg-cyan-500/10",
    badge: "bg-cyan-500/20 text-cyan-300 border-cyan-400/40",
    stroke: "#38bdf8",
  },
  magenta: {
    text: "text-fuchsia-400",
    border: "border-fuchsia-500/35",
    bg: "bg-fuchsia-500/10",
    badge: "bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-400/40",
    stroke: "#e879f9",
  },
  yellow: {
    text: "text-amber-400",
    border: "border-amber-500/35",
    bg: "bg-amber-500/10",
    badge: "bg-amber-500/20 text-amber-300 border-amber-400/40",
    stroke: "#fbbf24",
  },
  green: {
    text: "text-emerald-400",
    border: "border-emerald-500/35",
    bg: "bg-emerald-500/10",
    badge: "bg-emerald-500/20 text-emerald-300 border-emerald-400/40",
    stroke: "#34d399",
  },
  blue: {
    text: "text-blue-400",
    border: "border-blue-500/35",
    bg: "bg-blue-500/10",
    badge: "bg-blue-500/20 text-blue-300 border-blue-400/40",
    stroke: "#60a5fa",
  },
  red: {
    text: "text-rose-400",
    border: "border-rose-500/35",
    bg: "bg-rose-500/10",
    badge: "bg-rose-500/20 text-rose-300 border-rose-400/40",
    stroke: "#fb7185",
  },
  white: {
    text: "text-zinc-300",
    border: "border-zinc-500/35",
    bg: "bg-zinc-500/10",
    badge: "bg-zinc-500/20 text-zinc-300 border-zinc-400/40",
    stroke: "#a1a1aa",
  },
};

// ── Graph Data Model & Reconstruction Engine ─────────────────────────────────

// Represents an individual agent or spawned subagent node in the execution DAG
export interface AgentGraphNode {
  id: string;                     // Unique node key (e.g. "nexus", "subagent-1")
  label: string;                  // Human-readable agent name (e.g. "NexusAgent", "Subagent #1 (low)")
  parentId: string | null;        // Parent node ID ("nexus" for subagents, null for root)
  color: string;                  // Theme color key ("cyan", "magenta", "yellow", etc.)
  modelTier?: string;             // Model tier ("low", "medium", "strong")
  taskPrompt: string;             // Full untruncated prompt or initial query context
  contextManifest?: ContextManifestEntry[]; // Content-addressed boot manifest from `agent_start`
  contextSummary?: ContextSummary;          // Total chars / ~tokens summary from `agent_start`
  finalResponse: string | null;   // Final output synthesis emitted by this agent
  status: "running" | "done" | "error";
  startedAt: string | null;
  endedAt: string | null;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  costUsd: number;
  toolCallsCount: number;
  events: TraceEvent[];           // All trace steps belonging to this specific agent instance
}

/**
 * Reconstructs the parent-child Agent Execution Graph (DAG) from a flat array of TraceEvents.
 * Handles both modern traces (with explicit `agent_id` & `parent_id`) and legacy historical traces
 * (where all subagents shared `agent: "Subagent"` without `agent_id`) by correlating `spawn_subagent`
 * calls and `agent_start` boundaries.
 */
export function buildAgentExecutionGraph(events: TraceEvent[]): {
  nodes: AgentGraphNode[];
  rootNode: AgentGraphNode | null;
  subagentNodes: AgentGraphNode[];
} {
  const nodeMap = new Map<string, AgentGraphNode>();
  // Queue of active legacy subagent IDs for older traces that didn't emit explicit `agent_id`
  let legacySubCounter = 0;
  const activeLegacySubIds: string[] = [];
  // Pending `spawn_subagent` prompts emitted by NexusAgent so legacy subagent nodes still get their full untruncated `task_prompt`!
  const pendingSpawnPrompts: Array<{ prompt: string; tier: string }> = [];

  const getOrCreateNode = (
    id: string,
    label: string,
    parentId: string | null,
    color: string
  ): AgentGraphNode => {
    const existing = nodeMap.get(id);
    if (existing) return existing;
    const created: AgentGraphNode = {
      id,
      label,
      parentId,
      color: color || (id === "nexus" ? "cyan" : "magenta"),
      taskPrompt: "",
      finalResponse: null,
      status: "running",
      startedAt: null,
      endedAt: null,
      inputTokens: 0,
      outputTokens: 0,
      cachedTokens: 0,
      costUsd: 0,
      toolCallsCount: 0,
      events: [],
    };
    nodeMap.set(id, created);
    return created;
  };

  for (const evt of events) {
    const rawAgent = evt.agent ?? "NexusAgent";
    const data = (evt.data ?? {}) as Record<string, unknown>;

    // Capture full `spawn_subagent` prompts emitted by the parent agent so we can enrich child nodes
    if (evt.type === "tool_call" && data.tool === "spawn_subagent") {
      const args = (data.args ?? {}) as Record<string, unknown>;
      if (typeof args.task_prompt === "string") {
        pendingSpawnPrompts.push({
          prompt: args.task_prompt,
          tier: typeof args.model_tier === "string" ? args.model_tier : "low",
        });
      }
    }

    // Resolve unique node ID for this event
    let nodeId = evt.agent_id;
    let parentId = evt.parent_id ?? null;
    let displayLabel = rawAgent === "NexusAgent" || rawAgent === "nexus" ? "Head Agent" : rawAgent;
    let color = evt.color ?? "cyan";

    if (!nodeId) {
      // Legacy fallback for historical runs before `agent_id` was added
      const isSub = rawAgent.toLowerCase().startsWith("subagent");
      if (!isSub) {
        nodeId = "nexus";
        parentId = null;
        displayLabel = "Head Agent";
      } else {
        parentId = "nexus";
        if (evt.type === "agent_start") {
          legacySubCounter += 1;
          nodeId = `subagent-${legacySubCounter}`;
          activeLegacySubIds.push(nodeId);
          displayLabel = `Subagent #${legacySubCounter}`;
          const palette = ["magenta", "yellow", "green", "blue"];
          color = palette[(legacySubCounter - 1) % palette.length];
        } else {
          // Route step to active legacy subagent (or create #1 if missing start)
          if (activeLegacySubIds.length === 0) {
            legacySubCounter += 1;
            activeLegacySubIds.push(`subagent-${legacySubCounter}`);
          }
          nodeId = activeLegacySubIds[0];
          const existing = nodeMap.get(nodeId);
          displayLabel = existing?.label ?? `Subagent #${legacySubCounter}`;
          color = existing?.color ?? "magenta";
          if (evt.type === "agent_end" && activeLegacySubIds.length > 1) {
            activeLegacySubIds.shift();
          }
        }
      }
    }

    const node = getOrCreateNode(nodeId, displayLabel, parentId, color);
    node.events.push(evt);
    if (!node.startedAt && evt.timestamp) {
      node.startedAt = evt.timestamp;
    }

    // Enrich node metadata based on event type
    if (evt.type === "agent_start") {
      if (Array.isArray(data.context_manifest)) {
        node.contextManifest = data.context_manifest as ContextManifestEntry[];
      }
      if (data.context_summary && typeof data.context_summary === "object") {
        node.contextSummary = data.context_summary as ContextSummary;
      }
      const fullPromptFromData =
        typeof data.task_prompt === "string"
          ? data.task_prompt
          : typeof data.query === "string"
            ? data.query
            : typeof data.context === "string"
              ? data.context
              : evt.message;
      // If this is a subagent and pendingSpawnPrompts has a fuller prompt than a legacy truncated context, use it
      if (nodeId.startsWith("subagent") && pendingSpawnPrompts.length > 0) {
        const spawned = pendingSpawnPrompts.shift()!;
        node.taskPrompt =
          spawned.prompt.length >= fullPromptFromData.length
            ? spawned.prompt
            : fullPromptFromData;
        node.modelTier =
          (typeof data.model_tier === "string" ? data.model_tier : undefined) ??
          spawned.tier;
      } else {
        node.taskPrompt = fullPromptFromData;
        if (typeof data.model_tier === "string") {
          node.modelTier = data.model_tier;
        }
      }
    } else if (evt.type === "tool_call") {
      node.toolCallsCount += 1;
    } else if (evt.type === "llm_response") {
      const respText =
        typeof data.response === "string" ? data.response : evt.message;
      node.finalResponse = respText;
    } else if (evt.type === "info") {
      // Parse token and cost metrics from either structured `data` or `"Tokens: 13,625 in (0 cached, 0%) | 371 out · ~$0.0042"`
      if (typeof data.cost_usd === "number") {
        node.costUsd = (node.costUsd ?? 0) + data.cost_usd;
      } else if (evt.message?.includes("~$")) {
        const costMatch = evt.message.match(/~\$([\d.]+)/);
        if (costMatch) {
          node.costUsd = (node.costUsd ?? 0) + parseFloat(costMatch[1]);
        }
      }

      if (typeof data.input_tokens === "number") {
        node.inputTokens += data.input_tokens;
        node.outputTokens += typeof data.output_tokens === "number" ? data.output_tokens : 0;
        node.cachedTokens += typeof data.cached_tokens === "number" ? data.cached_tokens : 0;
      } else if (evt.message?.startsWith("Tokens:")) {
        const match = evt.message.match(
          /Tokens:\s*([\d,]+)\s*in\s*\(([\d,]+)\s*cached.*?\)\s*\|\s*([\d,]+)\s*out/i
        );
        if (match) {
          node.inputTokens += parseInt(match[1].replace(/,/g, ""), 10) || 0;
          node.cachedTokens += parseInt(match[2].replace(/,/g, ""), 10) || 0;
          node.outputTokens += parseInt(match[3].replace(/,/g, ""), 10) || 0;
        }
      }
    } else if (evt.type === "tool_error" || evt.type === "error") {
      node.status = "error";
    } else if (evt.type === "agent_end") {
      node.endedAt = evt.timestamp;
      if (node.status !== "error") {
        node.status = "done";
      }
    }
  }

  const nodes = Array.from(nodeMap.values());
  const rootNode =
    nodes.find((n) => n.id === "nexus" || n.parentId === null) ??
    nodes[0] ??
    null;
  const subagentNodes = nodes.filter((n) => n !== rootNode);

  return { nodes, rootNode, subagentNodes };
}

// ── Individual Uncut Step Row ────────────────────────────────────────────────

/**
 * formatHeaderArgValue — Formats an arbitrary tool argument value for compact inline display in the step header.
 * - val: unknown — The argument value (string, number, boolean, array, or object) passed to the tool.
 * - maxLen: number — Maximum character length threshold before truncating with an ellipsis (default: 80).
 * Strings are sanitized of carriage returns and newlines so multi-line inputs do not disrupt the header line layout.
 */
export function formatHeaderArgValue(val: unknown, maxLen = 80): string {
  if (val === null) return "null";
  if (val === undefined) return "undefined";
  if (typeof val === "string") {
    // Replace newline breaks with single spaces to keep header text inline and clean
    const singleLine = val.replace(/\r?\n/g, " ").trim();
    if (singleLine.length > maxLen) {
      return `"${singleLine.slice(0, maxLen)}…"`;
    }
    return `"${singleLine}"`;
  }
  if (typeof val === "number" || typeof val === "boolean") {
    return String(val);
  }
  try {
    const json = JSON.stringify(val);
    if (json.length > maxLen) {
      return `${json.slice(0, maxLen)}…`;
    }
    return json;
  } catch {
    return String(val);
  }
}

// Role badge styling lookup for folded `ContextManifestEntry` rows
const MANIFEST_ROLE_BADGE: Record<string, string> = {
  system: "bg-cyan-500/20 text-cyan-300 border-cyan-400/40",
  protocol: "bg-indigo-500/20 text-indigo-300 border-indigo-400/40",
  tools: "bg-amber-500/20 text-amber-300 border-amber-400/40",
  prehydrated: "bg-emerald-500/20 text-emerald-300 border-emerald-400/40",
  history: "bg-zinc-500/20 text-zinc-300 border-zinc-400/40",
  prompt: "bg-fuchsia-500/20 text-fuchsia-300 border-fuchsia-400/40",
};

/**
 * ContextManifestInspector — Lazy-loaded, folded-by-default viewer for content-addressed `agent_start`
 * and `llm_call` context injection manifests. Supports per-block lazy fetching (`GET /trace-blobs/{hash}`)
 * and one-click `Summon Full Context` (`POST /trace-blobs/batch`) reconstruction.
 */
function ContextManifestInspector({
  manifest,
  summary,
  title = "Injected Context",
}: {
  manifest: ContextManifestEntry[];
  summary?: ContextSummary;
  title?: string;
}) {
  const [openRows, setOpenRows] = useState<Record<number, boolean>>({});
  const [loadedBlobs, setLoadedBlobs] = useState<Record<string, string>>({});
  const [loadingHashes, setLoadingHashes] = useState<Record<string, boolean>>({});
  const [blobErrors, setBlobErrors] = useState<Record<string, string>>({});
  const [showFullContext, setShowFullContext] = useState(false);
  const [loadingFull, setLoadingFull] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const totalChars = useMemo(
    () =>
      summary?.total_chars ??
      manifest.reduce((acc, item) => acc + (item.chars || 0), 0),
    [manifest, summary]
  );

  const toggleRow = async (idx: number, hash: string) => {
    const nextOpen = !openRows[idx];
    setOpenRows((prev) => ({ ...prev, [idx]: nextOpen }));
    if (nextOpen && loadedBlobs[hash] === undefined && !loadingHashes[hash]) {
      setLoadingHashes((prev) => ({ ...prev, [hash]: true }));
      setBlobErrors((prev) => {
        const copy = { ...prev };
        delete copy[hash];
        return copy;
      });
      try {
        const text = await getTraceBlobContent(hash);
        setLoadedBlobs((prev) => ({ ...prev, [hash]: text }));
      } catch (err) {
        setBlobErrors((prev) => ({
          ...prev,
          [hash]: err instanceof Error ? err.message : "Failed to load blob",
        }));
      } finally {
        setLoadingHashes((prev) => ({ ...prev, [hash]: false }));
      }
    }
  };

  const assembleFullText = (blobsMap: Record<string, string>) =>
    manifest
      .map(
        (entry, i) =>
          `=== [${i + 1}/${manifest.length}] ${entry.label} (${formatCharsAndTokens(entry.chars)}) ===\n${
            blobsMap[entry.hash] ?? loadedBlobs[entry.hash] ?? "(blob unavailable)"
          }`
      )
      .join("\n\n");

  const handleSummonFullContext = async () => {
    if (showFullContext) {
      setShowFullContext(false);
      return;
    }
    const hashes = manifest.map((m) => m.hash).filter(Boolean);
    const missing = hashes.filter((h) => loadedBlobs[h] === undefined);
    if (missing.length > 0) {
      setLoadingFull(true);
      try {
        const fetched = await getTraceBlobsBatch(hashes);
        setLoadedBlobs((prev) => ({ ...prev, ...fetched }));
      } catch (err) {
        console.error("Failed to batch-load trace blobs:", err);
      } finally {
        setLoadingFull(false);
      }
    }
    setShowFullContext(true);
  };

  const handleCopy = (key: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey((prev) => (prev === key ? null : prev)), 1500);
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[0.65rem] font-mono uppercase tracking-wider text-accent-cyan flex items-center gap-1.5 flex-wrap">
          <span>{title}</span>
          <span className="text-text-muted font-normal normal-case">
            ({manifest.length} block{manifest.length === 1 ? "" : "s"} · {formatCharsAndTokens(totalChars)})
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              handleSummonFullContext();
            }}
            disabled={loadingFull}
            className="text-[0.65rem] font-mono px-2 py-0.5 rounded border border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors cursor-pointer disabled:opacity-50"
          >
            {loadingFull
              ? "Summoning..."
              : showFullContext
                ? "Hide Full Context"
                : "Summon Full Context"}
          </button>
          {showFullContext && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleCopy("full", assembleFullText(loadedBlobs));
              }}
              className="text-[0.65rem] font-mono px-2 py-0.5 rounded border border-border-subtle bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors cursor-pointer"
            >
              {copiedKey === "full" ? "Copied!" : "Copy Full Context"}
            </button>
          )}
        </div>
      </div>

      {showFullContext && (
        <pre className="p-3 rounded-lg bg-bg-secondary/95 border border-accent-cyan/35 text-text-primary font-mono text-[0.72rem] leading-relaxed whitespace-pre-wrap break-words max-h-[30rem] overflow-y-auto">
          {assembleFullText(loadedBlobs)}
        </pre>
      )}

      <div className="space-y-1">
        {manifest.map((item, idx) => {
          const isRowOpen = Boolean(openRows[idx]);
          const badgeClass =
            MANIFEST_ROLE_BADGE[item.role] ?? "bg-bg-tertiary text-text-secondary border-border-subtle";
          const content = loadedBlobs[item.hash];
          const isLoading = Boolean(loadingHashes[item.hash]);
          const err = blobErrors[item.hash];

          return (
            <div
              key={`${item.hash}-${idx}`}
              className="rounded-lg border border-border-subtle/80 bg-bg-secondary/70 overflow-hidden"
            >
              <div
                onClick={(e) => {
                  e.stopPropagation();
                  toggleRow(idx, item.hash);
                }}
                className="flex items-center justify-between gap-2 px-2.5 py-1.5 cursor-pointer select-none hover:bg-bg-tertiary/50 transition-colors font-mono text-[0.68rem]"
              >
                <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                  <span className="text-text-muted">{isRowOpen ? "▾" : "▸"}</span>
                  <span className={`px-1.5 py-0.2 rounded border text-[0.6rem] uppercase font-semibold shrink-0 ${badgeClass}`}>
                    {item.role}
                  </span>
                  <span className="text-text-primary font-medium truncate">
                    {item.label}
                  </span>
                  {item.context_files && item.context_files.length > 0 && (
                    <span className="text-[0.6rem] text-emerald-300/80">
                      [{item.context_files.length} file{item.context_files.length === 1 ? "" : "s"}]
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0 text-[0.64rem] text-text-muted">
                  <span>{formatCharsAndTokens(item.chars)}</span>
                  <span className="opacity-60" title={`SHA-256: ${item.hash}`}>
                    #{item.hash.slice(0, 7)}
                  </span>
                </div>
              </div>

              {isRowOpen && (
                <div className="border-t border-border-subtle/60 p-2.5 bg-bg-primary/60 space-y-1.5">
                  {isLoading ? (
                    <div className="text-[0.68rem] font-mono text-text-muted animate-pulse">
                      Fetching blob #{item.hash.slice(0, 8)}...
                    </div>
                  ) : err ? (
                    <div className="text-[0.68rem] font-mono text-rose-300">
                      Error loading blob: {err}
                    </div>
                  ) : (
                    <>
                      <div className="flex justify-end">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (content !== undefined) handleCopy(`row-${idx}`, content);
                          }}
                          className="text-[0.62rem] font-mono px-1.5 py-0.5 rounded bg-bg-tertiary text-text-secondary hover:text-text-primary cursor-pointer"
                        >
                          {copiedKey === `row-${idx}` ? "Copied!" : "Copy Block"}
                        </button>
                      </div>
                      <pre className="p-2.5 rounded bg-bg-secondary/90 border border-border-subtle text-text-primary font-mono text-[0.72rem] leading-relaxed whitespace-pre-wrap break-words max-h-96 overflow-y-auto">
                        {content ?? ""}
                      </pre>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TraceStepCard({
  evt,
  index,
  forceExpanded,
  expandVersion,
  pairInfo,
  isLive,
  onJumpToStep,
  isHighlighted,
  jumpExpandNonce,
  cardRef,
}: {
  evt: TraceEvent;
  index: number;
  forceExpanded?: boolean;
  expandVersion?: number;
  pairInfo?: ToolCallPairInfo;          // Bidirectional pairing metadata linking tool_call <-> tool_result/tool_error
  isLive?: boolean;                     // Distinguishes live streaming pending calls from finished runs
  onJumpToStep?: (targetIndex: number) => void; // Callback to scroll to, auto-expand, and flash the paired step
  isHighlighted?: boolean;              // True briefly after jumping to draw focus to the target card
  jumpExpandNonce?: number;             // Incremented when jumped to; triggers auto-expand even if clicked repeatedly
  cardRef?: (el: HTMLDivElement | null) => void; // Ref callback registering this card's DOM node in TraceStepList
}) {
  // isOpen: controls individual disclosure of this specific step card's payload body; defaults to false (collapsed by default)
  const [isOpen, setIsOpen] = useState(false);

  // Synchronize local open state whenever parent triggers an explicit expand/collapse command or updates expandVersion
  useEffect(() => {
    if (typeof forceExpanded === "boolean") {
      queueMicrotask(() => setIsOpen(forceExpanded));
    }
  }, [forceExpanded, expandVersion]);

  // Auto-expand this card whenever a counterpart step jumps to it (queued via microtask to satisfy React 19 lint rules)
  useEffect(() => {
    if (jumpExpandNonce && jumpExpandNonce > 0) {
      queueMicrotask(() => setIsOpen(true));
    }
  }, [jumpExpandNonce]);

  const icon = TRACE_ICONS[evt.type] ?? "·";
  const theme = AGENT_THEME[evt.color ?? "cyan"] ?? AGENT_THEME.white;
  const data = (evt.data ?? {}) as Record<string, unknown>;

  // Extract structured args/results so nothing is ever cut off
  const toolName = typeof data.tool === "string" ? data.tool : null;
  const toolArgs =
    data.args && typeof data.args === "object"
      ? (data.args as Record<string, unknown>)
      : null;
  const toolResult = typeof data.result === "string" ? data.result : null;
  const toolError = typeof data.error === "string" ? data.error : null;
  const fullTaskPrompt =
    typeof data.task_prompt === "string"
      ? data.task_prompt
      : typeof data.context === "string"
        ? data.context
        : null;
  const fullLlmThinking =
    typeof data.thinking === "string"
      ? data.thinking
      : evt.type === "llm_thinking" && evt.message
        ? evt.message
        : null;
  const fullLlmResponse =
    typeof data.response === "string" ? data.response : null;
  const contextManifest = Array.isArray(data.context_manifest)
    ? (data.context_manifest as ContextManifestEntry[])
    : null;
  const contextSummary =
    data.context_summary && typeof data.context_summary === "object"
      ? (data.context_summary as ContextSummary)
      : undefined;

  // Extract legacy arguments string from message if structured data.args is missing in older traces
  const legacyArgsStr = useMemo(() => {
    if (toolArgs && Object.keys(toolArgs).length > 0) return null;
    if (evt.type !== "tool_call" || !evt.message) return null;
    const match = evt.message.match(/Calling tool:\s*[\w_.-]+\(([\s\S]*)\)/);
    return match ? match[1].trim() : null;
  }, [toolArgs, evt.type, evt.message]);

  // Propagate tool name & arguments from the paired `tool_call` so `tool_result` / `tool_error` headers show full signatures
  const effectiveToolName = toolName ?? pairInfo?.toolName ?? null;
  const effectiveArgs =
    toolArgs && Object.keys(toolArgs).length > 0
      ? toolArgs
      : (pairInfo?.callArgs ?? null);
  const effectiveLegacyArgs = legacyArgsStr ?? pairInfo?.legacyArgsStr ?? null;
  const counterpartIdx = pairInfo?.counterpartIndex ?? null;
  const canJumpToCounterpart = Boolean(counterpartIdx !== null && onJumpToStep);

  // Build descriptive hover tooltip summarizing call_id, counterpart step, execution duration, and output size
  const jumpTargetLabel =
    pairInfo?.counterpartRole === "call"
      ? `Tool Call (Step #${(counterpartIdx ?? 0) + 1})`
      : pairInfo?.isError
        ? `Tool Error (Step #${(counterpartIdx ?? 0) + 1})`
        : `Tool Result (Step #${(counterpartIdx ?? 0) + 1})`;
  const badgeTitle = [
    pairInfo?.callId ? `Call ID: ${pairInfo.callId}` : null,
    counterpartIdx !== null ? `Click to jump to ${jumpTargetLabel}` : null,
    pairInfo?.durationLabel ? `Duration: ${pairInfo.durationLabel}` : null,
    pairInfo?.resultCharCount != null
      ? `Output: ${formatCharsAndTokens(pairInfo.resultCharCount)}`
      : null,
  ]
    .filter(Boolean)
    .join(" • ");

  // agentId: Unique machine/DAG identifier for the agent (e.g. "nexus", "subagent-1", "subagent-2")
  // Resolves explicit `evt.agent_id` first, falling back to heuristic parsing for legacy historical traces
  const agentId =
    evt.agent_id ||
    (evt.agent?.toLowerCase().startsWith("subagent") ? "subagent" : (evt.agent || "nexus"));

  // displayAgent: Human-readable agent badge label.
  // The primary commander ("nexus" / "NexusAgent") is rendered as "Head Agent"; subagents retain their serial IDs ("subagent-1", "subagent-2")
  const displayAgent =
    agentId === "nexus" || evt.agent === "NexusAgent" || evt.agent === "Head Agent"
      ? "Head Agent"
      : agentId;

  const hasStructuredPayload = Boolean(
    (toolArgs && Object.keys(toolArgs).length > 0) ||
    toolResult ||
    toolError ||
    (contextManifest && contextManifest.length > 0) ||
    fullTaskPrompt ||
    fullLlmThinking ||
    fullLlmResponse
  );

  const timeLabel = evt.timestamp
    ? new Date(evt.timestamp).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
    : "";

  const highlightClasses = isHighlighted
    ? evt.type === "tool_error"
      ? "ring-2 ring-rose-400/80 border-rose-400 shadow-[0_0_20px_rgba(251,113,133,0.28)]"
      : "ring-2 ring-accent-cyan/80 border-accent-cyan shadow-[0_0_20px_rgba(56,189,248,0.28)]"
    : theme.border;

  const signatureContent = effectiveToolName ? (
    <>
      <span className="text-accent-cyan font-semibold shrink-0">
        {effectiveToolName}
      </span>
      <span className="text-text-muted">(</span>
      {effectiveArgs && Object.keys(effectiveArgs).length > 0 ? (
        Object.entries(effectiveArgs).map(([key, val], idx, arr) => (
          <span key={key} className="inline-flex items-baseline">
            <span className="text-cyan-300/80 font-medium">{key}</span>
            <span className="text-text-muted">=</span>
            <span
              className="text-text-primary"
              title={typeof val === "string" ? val : JSON.stringify(val, null, 2)}
            >
              {formatHeaderArgValue(val)}
            </span>
            {idx < arr.length - 1 && (
              <span className="text-text-muted mr-1.5">,</span>
            )}
          </span>
        ))
      ) : effectiveLegacyArgs ? (
        <span className="text-text-primary" title={effectiveLegacyArgs}>
          {effectiveLegacyArgs.length > 100
            ? `${effectiveLegacyArgs.slice(0, 100)}…`
            : effectiveLegacyArgs}
        </span>
      ) : null}
      <span className="text-text-muted">)</span>
    </>
  ) : null;

  return (
    <div
      ref={cardRef}
      className={`rounded-lg border ${highlightClasses} bg-bg-primary/60 p-2.5 transition-all duration-300`}
    >
      {/* Header bar for the step: clicking toggles payload disclosure if structured data exists */}
      <div
        onClick={() => {
          if (hasStructuredPayload) {
            setIsOpen((prev) => !prev);
          }
        }}
        className={`flex items-start justify-between gap-2 select-none ${hasStructuredPayload ? "cursor-pointer" : ""
          }`}
      >
        <div className="flex items-start gap-2 min-w-0 flex-1 font-mono text-xs flex-wrap">
          <span className="shrink-0 text-text-muted text-[0.65rem] pt-0.5">
            #{index + 1}
          </span>
          <span className="shrink-0 w-4 text-center">{icon}</span>
          <span
            className={`shrink-0 px-1.5 py-0.2 rounded border text-[0.65rem] font-mono font-semibold ${theme.badge}`}
            title={`Agent: ${displayAgent} • ID: ${agentId}`}
          >
            {displayAgent}
          </span>
          <span className="px-1.5 py-0.2 rounded bg-bg-tertiary text-text-secondary text-[0.62rem] uppercase tracking-wider shrink-0">
            {evt.type}
          </span>

          {/* Tool Call signature and parameters in header (clickable to jump when paired) */}
          {effectiveToolName ? (
            canJumpToCounterpart ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onJumpToStep!(counterpartIdx!);
                }}
                title={badgeTitle || `Jump to ${jumpTargetLabel}`}
                className="text-left inline-flex items-baseline gap-0.5 flex-wrap min-w-0 rounded px-1 -mx-1 hover:bg-accent-cyan/10 hover:underline decoration-accent-cyan/60 underline-offset-2 transition-colors cursor-pointer"
              >
                {signatureContent}
              </button>
            ) : (
              <div className="inline-flex items-baseline gap-0.5 flex-wrap min-w-0">
                {signatureContent}
              </div>
            )
          ) : (
            !hasStructuredPayload && (
              <span className="text-text-primary whitespace-pre-wrap break-words">
                {evt.message}
              </span>
            )
          )}

          {/* Compact wire-level context footprint badge on collapsed llm_call headers */}
          {evt.type === "llm_call" && contextSummary && contextSummary.approx_tokens > 0 && (
            <span className="px-1.5 py-0.2 rounded bg-accent-cyan/10 border border-accent-cyan/25 text-accent-cyan text-[0.62rem] font-mono shrink-0">
              ctx: ~{contextSummary.approx_tokens.toLocaleString()} tok ({contextSummary.section_count} blocks)
            </span>
          )}

          {/* Bidirectional pairing badge: short call_id, counterpart step jump link, and elapsed duration */}
          {canJumpToCounterpart && pairInfo ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onJumpToStep!(counterpartIdx!);
              }}
              title={badgeTitle}
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[0.62rem] font-mono transition-colors cursor-pointer shrink-0 ${
                pairInfo.role === "call"
                  ? pairInfo.isError
                    ? "bg-rose-500/15 border-rose-500/35 text-rose-300 hover:bg-rose-500/25"
                    : "bg-emerald-500/15 border-emerald-500/35 text-emerald-300 hover:bg-emerald-500/25"
                  : "bg-cyan-500/15 border-cyan-500/35 text-cyan-300 hover:bg-cyan-500/25"
              }`}
            >
              {pairInfo.shortCallId && (
                <span className="text-text-muted">#{pairInfo.shortCallId}</span>
              )}
              <span>
                {pairInfo.role === "call"
                  ? pairInfo.isError
                    ? `↳ Error #${counterpartIdx! + 1}`
                    : `↳ Result #${counterpartIdx! + 1}`
                  : `↰ Call #${counterpartIdx! + 1}`}
              </span>
              {pairInfo.durationLabel && (
                <span className="text-text-secondary">· {pairInfo.durationLabel}</span>
              )}
            </button>
          ) : pairInfo?.role === "call" ? (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-border-subtle/70 bg-bg-tertiary/60 text-text-muted text-[0.62rem] font-mono shrink-0"
              title={pairInfo.callId ? `Call ID: ${pairInfo.callId}` : undefined}
            >
              {pairInfo.shortCallId && <span>#{pairInfo.shortCallId}</span>}
              <span>{isLive ? "⏳ pending" : "no result"}</span>
            </span>
          ) : pairInfo?.shortCallId ? (
            <span
              className="inline-flex items-center px-1.5 py-0.5 rounded border border-border-subtle/70 bg-bg-tertiary/60 text-text-muted text-[0.62rem] font-mono shrink-0"
              title={pairInfo.callId ? `Call ID: ${pairInfo.callId}` : undefined}
            >
              #{pairInfo.shortCallId}
            </span>
          ) : null}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {timeLabel && (
            <span className="text-[0.62rem] font-mono text-text-muted">
              {timeLabel}
            </span>
          )}
          {hasStructuredPayload && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setIsOpen((prev) => !prev);
              }}
              className="text-[0.65rem] text-text-muted hover:text-text-primary transition-colors flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-bg-tertiary"
              title={isOpen ? "Collapse step details" : "Expand step details"}
              aria-expanded={isOpen}
            >
              <span>{isOpen ? "▾" : "▸"}</span>
              <span>{isOpen ? "Collapse" : "Expand"}</span>
            </button>
          )}
        </div>
      </div>

      {/* Full Uncut Body / Structured Payload */}
      {hasStructuredPayload && isOpen && (
        <div className="mt-2 pt-2 border-t border-border-subtle/50 space-y-2 text-xs">
          {/* Content-Addressed Context Injection Manifest (agent_start & llm_call) */}
          {contextManifest && contextManifest.length > 0 && (
            <ContextManifestInspector
              manifest={contextManifest}
              summary={contextSummary}
              title={
                evt.type === "llm_call"
                  ? "Wire-Level LLM Input Context"
                  : "Full Injected Agent Context"
              }
            />
          )}

          {/* Legacy Agent Start / Subagent Task Prompt fallback when no content-addressed manifest exists */}
          {(!contextManifest || contextManifest.length === 0) && fullTaskPrompt && (
            <div>
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-text-muted mb-1">
                Initial Query / Task Prompt ({formatCharsAndTokens(fullTaskPrompt.length)}):
              </div>
              <pre className="p-2.5 rounded-lg bg-bg-secondary/90 border border-border-subtle text-text-primary font-mono text-[0.72rem] leading-relaxed whitespace-pre-wrap break-words overflow-x-auto">
                {fullTaskPrompt}
              </pre>
            </div>
          )}

          {/* Tool Arguments (including full spawn_subagent task_prompt or modify_file target/replacement) */}
          {toolArgs && Object.keys(toolArgs).length > 0 && (
            <div className="space-y-1.5">
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-text-muted">
                Tool Arguments:
              </div>
              {Object.entries(toolArgs).map(([k, v]) => {
                const formattedVal =
                  typeof v === "string" ? v : JSON.stringify(v, null, 2);
                return (
                  <div
                    key={k}
                    className="rounded-lg bg-bg-secondary/90 border border-border-subtle p-2"
                  >
                    <div className="text-[0.68rem] font-mono font-semibold text-accent-cyan mb-1">
                      {k}{" "}
                      <span className="text-text-muted font-normal">
                        ({formatCharsAndTokens(formattedVal.length)})
                      </span>
                    </div>
                    <pre className="text-text-primary font-mono text-[0.72rem] leading-relaxed whitespace-pre-wrap break-words overflow-x-auto">
                      {formattedVal}
                    </pre>
                  </div>
                );
              })}
            </div>
          )}

          {/* Tool Result */}
          {toolResult && (
            <div>
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-emerald-400 mb-1">
                Tool Output ({formatCharsAndTokens(toolResult.length)}):
              </div>
              <pre className="p-2.5 rounded-lg bg-bg-secondary/90 border border-emerald-500/20 text-text-primary font-mono text-[0.72rem] leading-relaxed whitespace-pre-wrap break-words overflow-x-auto">
                {toolResult}
              </pre>
            </div>
          )}

          {/* Tool Error */}
          {toolError && (
            <div>
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-rose-400 mb-1">
                Tool Error:
              </div>
              <pre className="p-2.5 rounded-lg bg-rose-950/30 border border-rose-500/30 text-rose-200 font-mono text-[0.72rem] leading-relaxed whitespace-pre-wrap break-words">
                {toolError}
              </pre>
            </div>
          )}

          {/* Full Model Reasoning / Thinking Summary */}
          {fullLlmThinking && (
            <div>
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-amber-300/90 mb-1">
                Model Reasoning ({formatCharsAndTokens(fullLlmThinking.length)}):
              </div>
              <div className="p-3 rounded-lg bg-amber-500/5 border border-amber-500/20 text-text-primary">
                <MarkdownMessage content={fullLlmThinking} openInNewTab={true} />
              </div>
            </div>
          )}

          {/* Full LLM Response */}
          {fullLlmResponse && (
            <div>
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-purple-300 mb-1">
                LLM Output ({formatCharsAndTokens(fullLlmResponse.length)}):
              </div>
              <div className="p-3 rounded-lg bg-bg-secondary/90 border border-border-subtle text-text-primary">
                {/* Render LLM trace output; note links click into new tabs to prevent interrupting active inspection */}
                <MarkdownMessage content={fullLlmResponse} openInNewTab={true} />
              </div>
            </div>
          )}

          {/* Expanded Footer Jump Action: allows jumping straight to the paired end after inspecting arguments/output */}
          {canJumpToCounterpart && pairInfo && (
            <div className="pt-1 flex justify-end">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onJumpToStep!(counterpartIdx!);
                }}
                className="text-[0.65rem] font-mono px-2 py-1 rounded-md border border-border-subtle bg-bg-secondary/80 text-accent-cyan hover:bg-accent-cyan/15 hover:border-accent-cyan/40 transition-colors cursor-pointer"
              >
                {pairInfo.role === "call"
                  ? `Jump to ${pairInfo.isError ? "Tool Error" : "Tool Result"} (#${counterpartIdx! + 1}${pairInfo.durationLabel ? ` · ${pairInfo.durationLabel}` : ""}) ↓`
                  : `↑ Jump to Tool Call (#${counterpartIdx! + 1}${pairInfo.durationLabel ? ` · ${pairInfo.durationLabel}` : ""})`}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Fallback preview message when collapsed for non-tool-call events (omitted for tool_call since parameters are now displayed in the header) */}
      {hasStructuredPayload && !isOpen && evt.type !== "tool_call" && evt.message && (
        <div className="mt-1 text-[0.7rem] font-mono text-text-muted whitespace-pre-wrap break-words line-clamp-2">
          {evt.message}
        </div>
      )}
    </div>
  );
}

/**
 * TraceStepList — Memoized chronological step container that pairs tool calls with their results/errors
 * and manages local DOM refs for collision-free smooth scrolling, auto-expansion, and highlight flashing.
 */
const TraceStepList = memo(function TraceStepList({
  events,
  isLive = false,
  forceExpanded,
  expandVersion,
}: {
  events: TraceEvent[];
  isLive?: boolean;
  forceExpanded?: boolean;
  expandVersion?: number;
}) {
  // Build bidirectional `tool_call <-> tool_result/tool_error` index once per events array update
  const pairMap = useMemo(() => buildToolCallPairMap(events), [events]);

  // Per-list DOM ref map keyed by step index (avoids global HTML `id` collisions across multiple chat drawers)
  const cardRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const [highlightedIndex, setHighlightedIndex] = useState<number | null>(null);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Tracks which card was jumped to plus an incrementing nonce so repeated jumps re-open a collapsed card
  const [jumpExpandTarget, setJumpExpandTarget] = useState<{
    index: number;
    nonce: number;
  } | null>(null);

  // Clear pending highlight timeout on unmount so stale timers never fire after navigation
  useEffect(() => {
    return () => {
      if (highlightTimerRef.current) {
        clearTimeout(highlightTimerRef.current);
      }
    };
  }, []);

  const registerCardRef = useCallback((idx: number, el: HTMLDivElement | null) => {
    if (el) {
      cardRefs.current.set(idx, el);
    } else {
      cardRefs.current.delete(idx);
    }
  }, []);

  const handleJumpToStep = useCallback((targetIndex: number) => {
    setJumpExpandTarget((prev) => ({
      index: targetIndex,
      nonce: (prev?.nonce ?? 0) + 1,
    }));
    setHighlightedIndex(targetIndex);

    if (highlightTimerRef.current) {
      clearTimeout(highlightTimerRef.current);
    }
    highlightTimerRef.current = setTimeout(() => {
      setHighlightedIndex(null);
    }, 1800);

    // Wait one animation frame so auto-expansion layout settles before scrolling smoothly to the counterpart
    requestAnimationFrame(() => {
      const el = cardRefs.current.get(targetIndex);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, []);

  return (
    <div className="space-y-2">
      {events.map((evt, idx) => (
        <TraceStepCard
          key={evt.id ? `${evt.id}-${idx}` : `step-${idx}`}
          evt={evt}
          index={idx}
          forceExpanded={forceExpanded}
          expandVersion={expandVersion}
          pairInfo={pairMap.get(idx)}
          isLive={isLive}
          onJumpToStep={handleJumpToStep}
          isHighlighted={highlightedIndex === idx}
          jumpExpandNonce={
            jumpExpandTarget?.index === idx ? jumpExpandTarget.nonce : undefined
          }
          cardRef={(el) => registerCardRef(idx, el)}
        />
      ))}
    </div>
  );
});

// ── Visual DAG Graph View & Node Inspector ───────────────────────────────────

// AgentGraphView: Memoized DAG topology canvas so parent search inputs or tab state changes
// do not trigger re-rendering of the execution graph unless `events` or `isLive` changes.
export const AgentGraphView = memo(function AgentGraphView({
  events,
  isLive = false,
}: {
  events: TraceEvent[];
  isLive?: boolean;
}) {
  const { nodes, rootNode, subagentNodes } = useMemo(
    () => buildAgentExecutionGraph(events),
    [events]
  );

  const [selectedNodeId, setSelectedNodeId] = useState<string>("all");
  // Controls expand/collapse state of execution step cards in the inspector or all-steps list; defaults to false (collapsed by default)
  const [expandAllSteps, setExpandAllSteps] = useState<boolean>(false);
  // Incrementing counter to ensure parent expand/collapse triggers cascade to children even when repeating the same boolean state
  const [expandVersion, setExpandVersion] = useState<number>(0);
  // promptExpanded: toggles disclosure of the prompt card in the Selected Node inspector (defaults to false / collapsed)
  const [promptExpanded, setPromptExpanded] = useState<boolean>(false);
  // responseExpanded: toggles disclosure of the final response markdown card in the Selected Node inspector (defaults to false / collapsed)
  const [responseExpanded, setResponseExpanded] = useState<boolean>(false);

  // Ensure selectedNodeId stays valid if events change
  const activeSelectedId =
    selectedNodeId === "all" || nodes.some((n) => n.id === selectedNodeId)
      ? selectedNodeId
      : (rootNode?.id ?? "all");

  const selectedNode = nodes.find((n) => n.id === activeSelectedId) ?? null;

  if (nodes.length === 0) {
    return (
      <div className="p-6 text-center text-xs text-text-muted">
        No agent graph topology recorded for this run yet.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ── Visual Topology Canvas (Commander -> Parallel Subagent Swarm) ── */}
      <div className="rounded-xl border border-border-subtle bg-bg-primary/80 p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-text-primary">
              🕸️ Execution Topology Graph (DAG)
            </span>
            <span className="text-[0.65rem] font-mono px-2 py-0.5 rounded-full bg-bg-tertiary text-text-secondary">
              {nodes.length} agent node{nodes.length === 1 ? "" : "s"} •{" "}
              {subagentNodes.length} subagent{subagentNodes.length === 1 ? "" : "s"}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setSelectedNodeId("all")}
            className={`text-[0.68rem] px-2.5 py-1 rounded-md border transition-colors ${activeSelectedId === "all"
                ? "bg-accent-cyan/20 border-accent-cyan/40 text-accent-cyan font-semibold"
                : "bg-bg-tertiary border-border-subtle text-text-secondary hover:text-text-primary"
              }`}
          >
            Show All Nodes &amp; Steps ({events.length})
          </button>
        </div>

        {/* Root Orchestrator Node */}
        {rootNode && (
          <div className="flex flex-col items-center">
            <button
              type="button"
              onClick={() => setSelectedNodeId(rootNode.id)}
              className={`w-full max-w-xl text-left rounded-xl border p-3.5 transition-all ${activeSelectedId === rootNode.id
                  ? "border-cyan-400 bg-cyan-500/15 shadow-[0_0_20px_rgba(56,189,248,0.18)]"
                  : "border-cyan-500/35 bg-bg-secondary/90 hover:border-cyan-400/60"
                }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-base">🧠</span>
                  <span className="font-bold text-xs text-cyan-300">
                    {rootNode.label === "NexusAgent" || rootNode.label === "nexus" ? "Head Agent" : rootNode.label}
                  </span>
                  <span className="text-[0.62rem] font-mono px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-200" title={`Unique Agent ID: ${rootNode.id}`}>
                    Head Agent (Root)
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[0.65rem] font-mono">
                  <span className="text-text-secondary">
                    🔧 {rootNode.toolCallsCount} tools
                  </span>
                  <span className="text-text-secondary">
                    ⚡ {rootNode.events.length} steps
                  </span>
                  {rootNode.inputTokens > 0 && (
                    <span className="text-cyan-300">
                      {(rootNode.inputTokens + rootNode.outputTokens).toLocaleString()} tok
                    </span>
                  )}
                  {rootNode.costUsd > 0 && (
                    <span className="text-amber-300">
                      💰 ${rootNode.costUsd < 0.01 ? rootNode.costUsd.toFixed(4) : rootNode.costUsd.toFixed(3)}
                    </span>
                  )}
                  <span
                    className={`px-1.5 py-0.2 rounded-full text-[0.6rem] uppercase ${rootNode.status === "done"
                        ? "bg-emerald-500/20 text-emerald-300"
                        : rootNode.status === "error"
                          ? "bg-rose-500/20 text-rose-300"
                          : "bg-cyan-500/20 text-cyan-300 animate-pulse"
                      }`}
                  >
                    {isLive && rootNode.status === "running" ? "running" : rootNode.status}
                  </span>
                </div>
              </div>
              {rootNode.taskPrompt && (
                <p className="text-[0.72rem] text-text-secondary font-mono whitespace-pre-wrap break-words">
                  {rootNode.taskPrompt}
                </p>
              )}
            </button>

            {/* SVG / CSS Branch Connectors to Spawned Subagent Swarm */}
            {subagentNodes.length > 0 && (
              <div className="w-full flex flex-col items-center">
                {/* Vertical stem from Commander */}
                <div className="w-0.5 h-5 bg-gradient-to-b from-cyan-400 to-fuchsia-400" />
                {/* Horizontal bus bar if multiple subagents */}
                {subagentNodes.length > 1 && (
                  <div className="w-4/5 h-0.5 bg-gradient-to-r from-fuchsia-500/50 via-amber-400/60 to-emerald-400/50 rounded-full" />
                )}

                {/* Subagent Node Cards Grid */}
                <div
                  className={`w-full grid gap-3 mt-2 ${subagentNodes.length === 1
                      ? "grid-cols-1 max-w-xl"
                      : subagentNodes.length === 2
                        ? "grid-cols-1 md:grid-cols-2"
                        : "grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
                    }`}
                >
                  {subagentNodes.map((sub, idx) => {
                    const theme = AGENT_THEME[sub.color] ?? AGENT_THEME.magenta;
                    const isSelected = activeSelectedId === sub.id;
                    return (
                      <button
                        key={sub.id}
                        type="button"
                        onClick={() => setSelectedNodeId(sub.id)}
                        className={`text-left rounded-xl border p-3.5 transition-all flex flex-col justify-between ${isSelected
                            ? `${theme.border} ${theme.bg} ring-1 ring-fuchsia-400/60 shadow-[0_0_18px_rgba(232,121,249,0.18)]`
                            : `${theme.border} bg-bg-secondary/85 hover:bg-bg-secondary`
                          }`}
                      >
                        <div>
                          <div className="flex items-center justify-between gap-1.5 mb-2">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span className="text-sm">⚡</span>
                              <span className={`font-bold text-xs truncate ${theme.text}`}>
                                {sub.label}
                              </span>
                              <span className="text-[0.6rem] font-mono px-1.5 py-0.2 rounded bg-bg-primary/80 text-text-muted border border-border-subtle/50" title={`Unique Agent ID: ${sub.id}`}>
                                {sub.id}
                              </span>
                              {sub.modelTier && (
                                <span className="text-[0.6rem] font-mono px-1.5 py-0.2 rounded bg-bg-tertiary text-text-secondary uppercase">
                                  {sub.modelTier}
                                </span>
                              )}
                            </div>
                            <span
                              className={`px-1.5 py-0.2 rounded-full text-[0.6rem] font-mono uppercase shrink-0 ${sub.status === "done"
                                  ? "bg-emerald-500/20 text-emerald-300"
                                  : sub.status === "error"
                                    ? "bg-rose-500/20 text-rose-300"
                                    : "bg-fuchsia-500/20 text-fuchsia-300 animate-pulse"
                                }`}
                            >
                              {sub.status}
                            </span>
                          </div>

                          {/* Subagent Task Prompt Preview (click node to inspect full prompt & steps below) */}
                          <div className="text-[0.68rem] font-mono text-text-secondary bg-bg-primary/60 rounded-lg p-2 border border-border-subtle/50 mb-2.5 max-h-28 overflow-y-auto whitespace-pre-wrap break-words">
                            {sub.taskPrompt || `Subagent #${idx + 1} execution`}
                          </div>
                        </div>

                        <div className="flex items-center justify-between text-[0.64rem] font-mono text-text-muted pt-1.5 border-t border-border-subtle/40">
                          <span>🔧 {sub.toolCallsCount} tool calls</span>
                          <span>📋 {sub.events.length} steps</span>
                          {sub.inputTokens > 0 && (
                            <span className={theme.text}>
                              {(sub.inputTokens + sub.outputTokens).toLocaleString()} tok
                            </span>
                          )}
                          {sub.costUsd > 0 && (
                            <span className="text-amber-300">
                              💰 ${sub.costUsd < 0.01 ? sub.costUsd.toFixed(4) : sub.costUsd.toFixed(3)}
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Selected Agent Node Deep-Dive Inspector ───────────────────────── */}
      {selectedNode ? (
        <div className="rounded-xl border border-border-subtle bg-bg-secondary/60 p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-border-subtle pb-2.5">
            <div className="flex items-center gap-2">
              <span className="text-base">
                {selectedNode.parentId === null ? "🧠" : "⚡"}
              </span>
              <h4 className="text-xs font-bold text-text-primary">
                {selectedNode.id === "nexus" || selectedNode.label === "NexusAgent" || selectedNode.label === "nexus" ? "Head Agent" : selectedNode.label} — Full Uncut Inspector
              </h4>
              <span className="text-[0.62rem] font-mono px-1.5 py-0.5 rounded bg-bg-tertiary text-accent-cyan border border-accent-cyan/30" title={`Unique Agent ID: ${selectedNode.id}`}>
                id: {selectedNode.id}
              </span>
              <span className="text-[0.65rem] font-mono text-text-muted">
                ({selectedNode.events.length} trace steps •{" "}
                {selectedNode.toolCallsCount} tool calls)
              </span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {selectedNode.costUsd > 0 && (
                <span className="text-[0.68rem] font-mono px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/30 text-amber-300">
                  Cost: ${selectedNode.costUsd < 0.01 ? selectedNode.costUsd.toFixed(4) : selectedNode.costUsd.toFixed(3)}
                </span>
              )}
              {selectedNode.inputTokens > 0 && (
                <span className="text-[0.68rem] font-mono px-2 py-0.5 rounded bg-bg-tertiary text-accent-cyan">
                  Tokens: {selectedNode.inputTokens.toLocaleString()} in (
                  {selectedNode.cachedTokens.toLocaleString()} cached) |{" "}
                  {selectedNode.outputTokens.toLocaleString()} out
                </span>
              )}
            </div>
          </div>

          {/* 1. Full Untruncated Context Manifest or Legacy Prompt Dispatched to this Agent / Subagent */}
          {selectedNode.contextManifest && selectedNode.contextManifest.length > 0 ? (
            <div className="rounded-lg border border-border-subtle bg-bg-primary/60 p-2.5">
              <ContextManifestInspector
                manifest={selectedNode.contextManifest}
                summary={selectedNode.contextSummary}
                title={
                  selectedNode.parentId === null
                    ? "Head Agent Injected Boot Context"
                    : "Subagent Injected Boot Context"
                }
              />
            </div>
          ) : selectedNode.taskPrompt ? (
            <div className="rounded-lg border border-border-subtle bg-bg-primary/60 p-2.5">
              <div
                onClick={() => setPromptExpanded((prev) => !prev)}
                className="flex items-center justify-between cursor-pointer select-none"
              >
                <div className="text-[0.65rem] font-mono uppercase tracking-wider text-accent-cyan flex items-center gap-1.5">
                  <span>
                    {selectedNode.parentId === null
                      ? "Initial User Query"
                      : "Full Subagent Task Prompt"}
                  </span>
                  <span className="text-text-muted font-normal">
                    ({formatCharsAndTokens(selectedNode.taskPrompt.length)})
                  </span>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setPromptExpanded((prev) => !prev);
                  }}
                  className="text-[0.65rem] text-text-muted hover:text-text-primary transition-colors flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-bg-tertiary"
                  title={promptExpanded ? "Collapse prompt window" : "Expand prompt window"}
                  aria-expanded={promptExpanded}
                >
                  <span>{promptExpanded ? "▾" : "▸"}</span>
                  <span>{promptExpanded ? "Collapse" : "Expand"}</span>
                </button>
              </div>
              {promptExpanded ? (
                <pre className="mt-2 p-3 rounded-lg bg-bg-secondary/90 border border-border-subtle text-text-primary font-mono text-xs leading-relaxed whitespace-pre-wrap break-words max-h-96 overflow-y-auto">
                  {selectedNode.taskPrompt}
                </pre>
              ) : (
                <p className="mt-1 text-[0.7rem] font-mono text-text-muted line-clamp-2">
                  {selectedNode.taskPrompt}
                </p>
              )}
            </div>
          ) : null}

          {/* 2. All Ordered Execution Steps for this Node (with dedicated Expand/Collapse All toggle) */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-text-muted">
                Complete Step-by-Step Execution Log ({selectedNode.events.length} steps):
              </div>
              <button
                type="button"
                onClick={() => {
                  setExpandAllSteps((prev) => !prev);
                  setExpandVersion((v) => v + 1);
                }}
                className="text-[0.65rem] px-2 py-0.5 rounded-md border border-border-subtle bg-bg-primary/60 text-text-secondary hover:text-text-primary transition-colors flex items-center gap-1"
                title={expandAllSteps ? "Collapse all step payloads" : "Expand all step payloads"}
                aria-expanded={expandAllSteps}
              >
                <span>{expandAllSteps ? "▾" : "▸"}</span>
                <span>{expandAllSteps ? "Collapse All" : "Expand All"}</span>
              </button>
            </div>
            <TraceStepList
              events={selectedNode.events}
              isLive={isLive}
              forceExpanded={expandAllSteps}
              expandVersion={expandVersion}
            />
          </div>

          {/* 3. Final Synthesis Returned by this Agent (Collapsible card, collapsed by default) */}
          {selectedNode.finalResponse && (
            <div className="rounded-lg border border-emerald-500/30 bg-bg-primary/60 p-2.5">
              <div
                onClick={() => setResponseExpanded((prev) => !prev)}
                className="flex items-center justify-between cursor-pointer select-none"
              >
                <div className="text-[0.65rem] font-mono uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                  <span>Final Output / Synthesis Returned</span>
                  <span className="text-text-muted font-normal">
                    ({formatCharsAndTokens(selectedNode.finalResponse.length)})
                  </span>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setResponseExpanded((prev) => !prev);
                  }}
                  className="text-[0.65rem] text-text-muted hover:text-text-primary transition-colors flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-bg-tertiary"
                  title={responseExpanded ? "Collapse output window" : "Expand output window"}
                  aria-expanded={responseExpanded}
                >
                  <span>{responseExpanded ? "▾" : "▸"}</span>
                  <span>{responseExpanded ? "Collapse" : "Expand"}</span>
                </button>
              </div>
              {responseExpanded && (
                <div className="mt-2 p-3.5 rounded-lg bg-bg-secondary/90 border border-emerald-500/30 text-text-primary text-xs">
                  {/* Render final response; note links click into new tabs */}
                  <MarkdownMessage content={selectedNode.finalResponse} openInNewTab={true} />
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        /* Show All Steps Chronologically when "Show All Nodes & Steps" is selected */
        <div className="space-y-2">
          <div className="flex items-center justify-between mb-1">
            <div className="text-[0.65rem] font-mono uppercase tracking-wider text-text-muted">
              All Chronological Steps ({events.length}):
            </div>
            <button
              type="button"
              onClick={() => {
                setExpandAllSteps((prev) => !prev);
                setExpandVersion((v) => v + 1);
              }}
              className="text-[0.65rem] px-2 py-0.5 rounded-md border border-border-subtle bg-bg-primary/60 text-text-secondary hover:text-text-primary transition-colors flex items-center gap-1"
              title={expandAllSteps ? "Collapse all step payloads" : "Expand all step payloads"}
              aria-expanded={expandAllSteps}
            >
              <span>{expandAllSteps ? "▾" : "▸"}</span>
              <span>{expandAllSteps ? "Collapse All" : "Expand All"}</span>
            </button>
          </div>
          <TraceStepList
            events={events}
            isLive={isLive}
            forceExpanded={expandAllSteps}
            expandVersion={expandVersion}
          />
        </div>
      )}
    </div>
  );
});

// ── Collapsible & Expandable Thinking Panel (Used in Chat Thread) ────────────

// ThinkingPanel: Collapsible agent execution trace drawer for both streaming and historical turns.
// Wrapped in `React.memo` so historical trace drawers never re-render when chat input state changes.
// - events: TraceEvent[] — Lossless chronological array of trace events (tool calls, LLM responses, agent boundaries).
// - isLive: boolean — Distinguishes between active SSE streaming execution and completed historical runs.
// - defaultExpanded: boolean — Initial disclosure state; defaults to false so live runs and message history start collapsed.
// - messageId: optional SQLite messages.id; enables lazy on-demand trace fetching from message_traces when expanded.
export const ThinkingPanel = memo(function ThinkingPanel({
  events: initialEvents,
  isLive,
  defaultExpanded = false,
  messageId,
}: {
  events?: TraceEvent[];
  isLive: boolean;
  defaultExpanded?: boolean;
  messageId?: number;
}) {
  // expanded: controls visibility of the inner graph/step visualization; initialized via defaultExpanded (default: false)
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [viewMode, setViewMode] = useState<"graph" | "steps" | "raw">("graph");
  // fetchedEvents holds trace arrays lazy-loaded on demand via getMessageTrace(messageId) for historical messages
  const [fetchedEvents, setFetchedEvents] = useState<TraceEvent[]>([]);
  const [isLoadingTrace, setIsLoadingTrace] = useState(false);
  const [traceLoadError, setTraceLoadError] = useState<string | null>(null);

  // Derive activeEvents directly from live/inline initialEvents when provided, falling back to lazy-fetched events
  const activeEvents = useMemo(
    () => (initialEvents && initialEvents.length > 0 ? initialEvents : fetchedEvents),
    [initialEvents, fetchedEvents]
  );

  // expandAllSteps: toggles global expand/collapse of all steps in chronological list; defaults to false (collapsed by default)
  const [expandAllSteps, setExpandAllSteps] = useState(false);
  // expandVersion: ensures explicit expand/collapse triggers cascade to child cards
  const [expandVersion, setExpandVersion] = useState(0);
  const [fullHeight, setFullHeight] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  // isAtBottomRef: guards compact auto-scroll so inspecting earlier steps while live does not pull view
  const isAtBottomRef = useRef(true);

  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    isAtBottomRef.current = scrollHeight - scrollTop - clientHeight <= 40;
  }, []);

  const { subagentNodes } = useMemo(
    () => buildAgentExecutionGraph(activeEvents),
    [activeEvents]
  );

  // Auto-scroll while live if bounded height mode is active and user is near the bottom
  useEffect(() => {
    if (expanded && isLive && !fullHeight && scrollRef.current && isAtBottomRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activeEvents, expanded, isLive, fullHeight]);

  const handleToggleExpand = useCallback(async () => {
    if (!expanded) {
      setExpanded(true);
      // If expanding a historical turn where traces were not pre-loaded, fetch on demand
      if (activeEvents.length === 0 && messageId !== undefined && !isLoadingTrace) {
        setIsLoadingTrace(true);
        setTraceLoadError(null);
        try {
          const fetched = await getMessageTrace(messageId);
          setFetchedEvents(fetched);
        } catch (err) {
          console.error("Failed to load message trace:", err);
          setTraceLoadError("Failed to load execution trace.");
        } finally {
          setIsLoadingTrace(false);
        }
      }
    } else {
      setExpanded(false);
    }
  }, [expanded, activeEvents.length, messageId, isLoadingTrace]);

  // Do not render anything if no events exist and this is not a lazy-fetchable historical message
  if (activeEvents.length === 0 && messageId === undefined) return null;

  return (
    <div className="mt-3 rounded-xl border border-border-subtle/80 bg-bg-secondary/50 overflow-hidden">
      {/* ── Top Control Bar ── */}
      <div
        className={`flex flex-wrap items-center justify-between gap-2 px-3.5 py-2 bg-bg-tertiary/60 ${expanded ? "border-b border-border-subtle/50" : ""
          }`}
      >
        <button
          type="button"
          onClick={handleToggleExpand}
          className="flex items-center gap-2 text-xs font-semibold text-text-primary hover:text-accent-cyan transition-colors"
        >
          <svg
            className={`w-3.5 h-3.5 transition-transform ${expanded ? "rotate-90" : ""}`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path d="M9 18l6-6-6-6" />
          </svg>
          {isLive ? (
            <span className="inline-flex items-center gap-1.5 text-accent-cyan">
              <span className="w-2 h-2 rounded-full bg-accent-cyan animate-pulse" />
              Live Agent Execution ({activeEvents.length} steps
              {subagentNodes.length > 0
                ? ` • ${subagentNodes.length} subagents`
                : ""}
              )
            </span>
          ) : (
            <span>
              Agent Execution Trace
              {activeEvents.length > 0 ? (
                ` (${activeEvents.length} step${activeEvents.length === 1 ? "" : "s"}${subagentNodes.length > 0
                  ? ` • ${subagentNodes.length} subagent${subagentNodes.length === 1 ? "" : "s"}`
                  : ""})`
              ) : (
                " (Click to expand)"
              )}
            </span>
          )}
        </button>

        {expanded && (
          <div className="flex items-center gap-1.5 flex-wrap">
            {/* View Mode Switcher: Graph View vs Chronological Steps vs Raw JSON */}
            <div className="flex items-center rounded-lg bg-bg-primary/80 p-0.5 border border-border-subtle text-[0.68rem]">
              <button
                type="button"
                onClick={() => setViewMode("graph")}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors ${viewMode === "graph"
                    ? "bg-accent-cyan/20 text-accent-cyan"
                    : "text-text-muted hover:text-text-primary"
                  }`}
              >
                🕸️ Graph View
              </button>
              <button
                type="button"
                onClick={() => setViewMode("steps")}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors ${viewMode === "steps"
                    ? "bg-accent-cyan/20 text-accent-cyan"
                    : "text-text-muted hover:text-text-primary"
                  }`}
              >
                📜 All Steps ({activeEvents.length})
              </button>
              <button
                type="button"
                onClick={() => setViewMode("raw")}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors ${viewMode === "raw"
                    ? "bg-accent-cyan/20 text-accent-cyan"
                    : "text-text-muted hover:text-text-primary"
                  }`}
              >
                {"{ }"} Raw JSON
              </button>
            </div>

            {viewMode === "steps" && (
              <button
                type="button"
                onClick={() => {
                  setExpandAllSteps((prev) => !prev);
                  setExpandVersion((v) => v + 1);
                }}
                className="text-[0.65rem] px-2 py-1 rounded-md border border-border-subtle bg-bg-primary/60 text-text-secondary hover:text-text-primary flex items-center gap-1 transition-colors"
                title={expandAllSteps ? "Collapse all step payloads" : "Expand all step payloads"}
                aria-expanded={expandAllSteps}
              >
                <span>{expandAllSteps ? "▾" : "▸"}</span>
                <span>{expandAllSteps ? "Collapse All" : "Expand All"}</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => setFullHeight((prev) => !prev)}
              className="text-[0.65rem] px-2 py-1 rounded-md border border-border-subtle bg-bg-primary/60 text-text-secondary hover:text-text-primary"
              title="Toggle between full uncut height and scrollable box"
            >
              {fullHeight ? "↕ Full Height (Uncut)" : "↕ Compact Scroll"}
            </button>
          </div>
        )}
      </div>

      {/* ── Body ── */}
      {expanded && (
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className={`p-3.5 ${fullHeight ? "" : "max-h-[32rem] overflow-y-auto"
            }`}
        >
          {isLoadingTrace ? (
            <div className="py-8 flex flex-col items-center justify-center gap-2 text-xs text-text-muted font-mono">
              <div className="w-4 h-4 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin" />
              <span>Loading execution trace telemetry...</span>
            </div>
          ) : traceLoadError ? (
            <div className="py-6 text-center text-xs text-red-400 font-mono">
              <p>{traceLoadError}</p>
              <button
                type="button"
                onClick={() => {
                  if (messageId !== undefined) {
                    setIsLoadingTrace(true);
                    setTraceLoadError(null);
                    getMessageTrace(messageId)
                      .then(setFetchedEvents)
                      .catch(() => setTraceLoadError("Failed to load trace events."))
                      .finally(() => setIsLoadingTrace(false));
                  }
                }}
                className="mt-2 inline-block px-3 py-1 rounded bg-red-500/10 border border-red-500/20 text-red-300 hover:bg-red-500/20 transition-colors"
              >
                Retry
              </button>
            </div>
          ) : (
            <>
              {viewMode === "graph" && (
                <AgentGraphView events={activeEvents} isLive={isLive} />
              )}

              {viewMode === "steps" && (
                <TraceStepList
                  events={activeEvents}
                  isLive={isLive}
                  forceExpanded={expandAllSteps}
                  expandVersion={expandVersion}
                />
              )}

              {viewMode === "raw" && (
                <pre className="p-3 rounded-lg bg-bg-primary/90 border border-border-subtle text-text-primary font-mono text-[0.7rem] leading-relaxed whitespace-pre-wrap break-words overflow-x-auto">
                  {JSON.stringify(activeEvents, null, 2)}
                </pre>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
});
