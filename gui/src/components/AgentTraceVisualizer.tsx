"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import type { TraceEvent } from "@/lib/api";
import MarkdownMessage from "@/components/MarkdownMessage";

// ── Icon & Color Maps ────────────────────────────────────────────────────────

// Maps trace event discriminators to visual glyphs for timeline rows and graph nodes
export const TRACE_ICONS: Record<string, string> = {
  agent_start: "▶",
  agent_end: "■",
  llm_call: "🤖",
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
  finalResponse: string | null;   // Final output synthesis emitted by this agent
  status: "running" | "done" | "error";
  startedAt: string | null;
  endedAt: string | null;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
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
    let displayLabel = rawAgent;
    let color = evt.color ?? "cyan";

    if (!nodeId) {
      // Legacy fallback for historical runs before `agent_id` was added
      const isSub = rawAgent.toLowerCase().startsWith("subagent");
      if (!isSub) {
        nodeId = "nexus";
        parentId = null;
        displayLabel = rawAgent || "NexusAgent";
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
      // Parse token metrics from either structured `data` or `"Tokens: 13,625 in (0 cached, 0%) | 371 out"`
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

function TraceStepCard({
  evt,
  index,
  forceExpanded,
}: {
  evt: TraceEvent;
  index: number;
  forceExpanded: boolean;
}) {
  const [localOpen, setLocalOpen] = useState(true);
  const isOpen = forceExpanded || localOpen;

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
  const fullLlmResponse =
    typeof data.response === "string" ? data.response : null;

  const hasStructuredPayload = Boolean(
    (toolArgs && Object.keys(toolArgs).length > 0) ||
      toolResult ||
      toolError ||
      fullTaskPrompt ||
      fullLlmResponse
  );

  const timeLabel = evt.timestamp
    ? new Date(evt.timestamp).toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "";

  return (
    <div
      className={`rounded-lg border ${theme.border} bg-bg-primary/60 p-2.5 transition-colors`}
    >
      {/* Header bar for the step */}
      <div
        onClick={() => setLocalOpen((prev) => !prev)}
        className="flex items-start justify-between gap-2 cursor-pointer select-none"
      >
        <div className="flex items-start gap-2 min-w-0 flex-1 font-mono text-xs">
          <span className="shrink-0 text-text-muted text-[0.65rem] pt-0.5">
            #{index + 1}
          </span>
          <span className="shrink-0 w-4 text-center">{icon}</span>
          <span
            className={`shrink-0 px-1.5 py-0.2 rounded border text-[0.65rem] font-semibold ${theme.badge}`}
          >
            {evt.agent ?? "System"}
          </span>
          <span className="px-1.5 py-0.2 rounded bg-bg-tertiary text-text-secondary text-[0.62rem] uppercase tracking-wider shrink-0">
            {evt.type}
          </span>
          {toolName && (
            <span className="text-accent-cyan font-semibold shrink-0">
              {toolName}()
            </span>
          )}
          {!hasStructuredPayload && (
            <span className="text-text-primary whitespace-pre-wrap break-words">
              {evt.message}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {timeLabel && (
            <span className="text-[0.62rem] font-mono text-text-muted">
              {timeLabel}
            </span>
          )}
          {hasStructuredPayload && (
            <span className="text-[0.65rem] text-text-muted hover:text-text-primary">
              {isOpen ? "▾ Hide details" : "▸ Show details"}
            </span>
          )}
        </div>
      </div>

      {/* Full Uncut Body / Structured Payload */}
      {hasStructuredPayload && isOpen && (
        <div className="mt-2 pt-2 border-t border-border-subtle/50 space-y-2 text-xs">
          {/* Agent Start / Subagent Task Prompt */}
          {fullTaskPrompt && (
            <div>
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-text-muted mb-1">
                Full Prompt / Context ({fullTaskPrompt.length.toLocaleString()} chars):
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
                        ({formattedVal.length.toLocaleString()} chars)
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
                Tool Output ({toolResult.length.toLocaleString()} chars):
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

          {/* Full LLM Response */}
          {fullLlmResponse && (
            <div>
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-purple-300 mb-1">
                LLM Output ({fullLlmResponse.length.toLocaleString()} chars):
              </div>
              <div className="p-3 rounded-lg bg-bg-secondary/90 border border-border-subtle text-text-primary">
                <MarkdownMessage content={fullLlmResponse} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Fallback when collapsed */}
      {hasStructuredPayload && !isOpen && (
        <div className="mt-1 text-[0.7rem] font-mono text-text-muted whitespace-pre-wrap break-words">
          {evt.message}
        </div>
      )}
    </div>
  );
}

// ── Visual DAG Graph View & Node Inspector ───────────────────────────────────

export function AgentGraphView({
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
            className={`text-[0.68rem] px-2.5 py-1 rounded-md border transition-colors ${
              activeSelectedId === "all"
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
              className={`w-full max-w-xl text-left rounded-xl border p-3.5 transition-all ${
                activeSelectedId === rootNode.id
                  ? "border-cyan-400 bg-cyan-500/15 shadow-[0_0_20px_rgba(56,189,248,0.18)]"
                  : "border-cyan-500/35 bg-bg-secondary/90 hover:border-cyan-400/60"
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-base">🧠</span>
                  <span className="font-bold text-xs text-cyan-300">
                    {rootNode.label}
                  </span>
                  <span className="text-[0.62rem] font-mono px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-200">
                    Commander (Root)
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
                  <span
                    className={`px-1.5 py-0.2 rounded-full text-[0.6rem] uppercase ${
                      rootNode.status === "done"
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
                  className={`w-full grid gap-3 mt-2 ${
                    subagentNodes.length === 1
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
                        className={`text-left rounded-xl border p-3.5 transition-all flex flex-col justify-between ${
                          isSelected
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
                              {sub.modelTier && (
                                <span className="text-[0.6rem] font-mono px-1.5 py-0.2 rounded bg-bg-tertiary text-text-secondary uppercase">
                                  {sub.modelTier}
                                </span>
                              )}
                            </div>
                            <span
                              className={`px-1.5 py-0.2 rounded-full text-[0.6rem] font-mono uppercase shrink-0 ${
                                sub.status === "done"
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
                {selectedNode.label} — Full Uncut Inspector
              </h4>
              <span className="text-[0.65rem] font-mono text-text-muted">
                ({selectedNode.events.length} trace steps •{" "}
                {selectedNode.toolCallsCount} tool calls)
              </span>
            </div>
            {selectedNode.inputTokens > 0 && (
              <span className="text-[0.68rem] font-mono px-2 py-0.5 rounded bg-bg-tertiary text-accent-cyan">
                Tokens: {selectedNode.inputTokens.toLocaleString()} in (
                {selectedNode.cachedTokens.toLocaleString()} cached) |{" "}
                {selectedNode.outputTokens.toLocaleString()} out
              </span>
            )}
          </div>

          {/* 1. Full Untruncated Prompt Dispatched to this Agent / Subagent */}
          {selectedNode.taskPrompt && (
            <div>
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-accent-cyan mb-1">
                {selectedNode.parentId === null
                  ? "Initial User Query:"
                  : "Full Subagent Task Prompt (Untruncated):"}
              </div>
              <pre className="p-3 rounded-lg bg-bg-primary/90 border border-border-subtle text-text-primary font-mono text-xs leading-relaxed whitespace-pre-wrap break-words">
                {selectedNode.taskPrompt}
              </pre>
            </div>
          )}

          {/* 2. All Ordered Execution Steps for this Node */}
          <div>
            <div className="text-[0.65rem] font-mono uppercase tracking-wider text-text-muted mb-1.5">
              Complete Step-by-Step Execution Log ({selectedNode.events.length} steps):
            </div>
            <div className="space-y-2">
              {selectedNode.events.map((evt, idx) => (
                <TraceStepCard
                  key={evt.id ?? idx}
                  evt={evt}
                  index={idx}
                  forceExpanded={true}
                />
              ))}
            </div>
          </div>

          {/* 3. Final Synthesis Returned by this Agent */}
          {selectedNode.finalResponse && (
            <div>
              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-emerald-400 mb-1">
                Final Output / Synthesis Returned:
              </div>
              <div className="p-3.5 rounded-lg bg-bg-primary/90 border border-emerald-500/30 text-text-primary text-xs">
                <MarkdownMessage content={selectedNode.finalResponse} />
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Show All Steps Chronologically when "Show All Nodes & Steps" is selected */
        <div className="space-y-2">
          {events.map((evt, idx) => (
            <TraceStepCard
              key={evt.id ?? idx}
              evt={evt}
              index={idx}
              forceExpanded={true}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Collapsible & Expandable Thinking Panel (Used in Chat Thread) ────────────

export function ThinkingPanel({
  events,
  isLive,
  defaultExpanded = true,
}: {
  events: TraceEvent[];
  isLive: boolean;
  defaultExpanded?: boolean;
}) {
  // Never auto-collapse when a run finishes so the user never loses visibility of steps
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [viewMode, setViewMode] = useState<"graph" | "steps" | "raw">("graph");
  const [expandAllSteps, setExpandAllSteps] = useState(true);
  const [fullHeight, setFullHeight] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { subagentNodes } = useMemo(
    () => buildAgentExecutionGraph(events),
    [events]
  );

  // Auto-scroll while live if bounded height mode is active
  useEffect(() => {
    if (expanded && isLive && !fullHeight && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, expanded, isLive, fullHeight]);

  if (events.length === 0) return null;

  return (
    <div className="mt-3 rounded-xl border border-border-subtle/80 bg-bg-secondary/50 overflow-hidden">
      {/* ── Top Control Bar ── */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2 bg-bg-tertiary/60 border-b border-border-subtle/50">
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
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
              Live Agent Execution ({events.length} steps
              {subagentNodes.length > 0
                ? ` • ${subagentNodes.length} subagents`
                : ""}
              )
            </span>
          ) : (
            <span>
              Agent Execution Trace ({events.length} steps
              {subagentNodes.length > 0
                ? ` • ${subagentNodes.length} subagent${subagentNodes.length === 1 ? "" : "s"}`
                : ""}
              )
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
                className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                  viewMode === "graph"
                    ? "bg-accent-cyan/20 text-accent-cyan"
                    : "text-text-muted hover:text-text-primary"
                }`}
              >
                🕸️ Graph View
              </button>
              <button
                type="button"
                onClick={() => setViewMode("steps")}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                  viewMode === "steps"
                    ? "bg-accent-cyan/20 text-accent-cyan"
                    : "text-text-muted hover:text-text-primary"
                }`}
              >
                📜 All Steps ({events.length})
              </button>
              <button
                type="button"
                onClick={() => setViewMode("raw")}
                className={`px-2.5 py-1 rounded-md font-medium transition-colors ${
                  viewMode === "raw"
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
                onClick={() => setExpandAllSteps((prev) => !prev)}
                className="text-[0.65rem] px-2 py-1 rounded-md border border-border-subtle bg-bg-primary/60 text-text-secondary hover:text-text-primary"
              >
                {expandAllSteps ? "Collapse Payloads" : "Expand All Payloads"}
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
          className={`p-3.5 ${
            fullHeight ? "" : "max-h-[32rem] overflow-y-auto"
          }`}
        >
          {viewMode === "graph" && (
            <AgentGraphView events={events} isLive={isLive} />
          )}

          {viewMode === "steps" && (
            <div className="space-y-2">
              {events.map((evt, i) => (
                <TraceStepCard
                  key={evt.id ?? i}
                  evt={evt}
                  index={i}
                  forceExpanded={expandAllSteps}
                />
              ))}
            </div>
          )}

          {viewMode === "raw" && (
            <pre className="p-3 rounded-lg bg-bg-primary/90 border border-border-subtle text-text-primary font-mono text-[0.7rem] leading-relaxed whitespace-pre-wrap break-words overflow-x-auto">
              {JSON.stringify(events, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
