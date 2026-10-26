"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import MarkdownMessage from "@/components/MarkdownMessage";
import { AgentGraphView, TRACE_ICONS, AGENT_THEME } from "@/components/AgentTraceVisualizer";
import { getAgentRuns, getAgentRun } from "@/lib/api";
import type { RunSummary, RunSnapshot, SubagentRunRecord, TraceEvent } from "@/lib/api";

// ── Tab Navigation Keys ──────────────────────────────────────────────────────
type AuditTab = "graph" | "subagents" | "steps" | "io" | "json";

export default function AuditPage() {
  // runs: list of recent execution summaries fetched from GET /api/agents/runs
  const [runs, setRuns] = useState<RunSummary[]>([]);
  // selectedRunId: active run ID being inspected in the detailed view
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  // activeSnapshot: complete, untruncated run details fetched from GET /api/agents/runs/{run_id}
  const [activeSnapshot, setActiveSnapshot] = useState<RunSnapshot | null>(null);
  // activeTab: current inspection view (Graph, Subagent Fleet, Full Steps, I/O, Raw JSON)
  const [activeTab, setActiveTab] = useState<AuditTab>("graph");
  // searchQuery: text filter for finding runs by prompt or ID
  const [searchQuery, setSearchQuery] = useState<string>("");
  // loading state flags for list and detail fetches
  const [loadingList, setLoadingList] = useState<boolean>(true);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch recent run summaries on initial mount
  useEffect(() => {
    async function loadRuns() {
      try {
        setLoadingList(true);
        // apiFetch returns RunSummary[] array ordered newest-to-oldest from logs/runs/
        const data = await getAgentRuns(50);
        setRuns(data);
        if (data.length > 0) {
          setSelectedRunId(data[0].run_id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load run logs");
      } finally {
        setLoadingList(false);
      }
    }
    loadRuns();
  }, []);

  // Fetch full untruncated run snapshot when selectedRunId changes
  useEffect(() => {
    if (!selectedRunId) {
      setActiveSnapshot(null);
      return;
    }
    let cancelled = false;
    async function loadRunDetail(id: string) {
      try {
        setLoadingDetail(true);
        // getAgentRun fetches the complete JSON snapshot without field truncation
        const snapshot = await getAgentRun(id);
        if (!cancelled) {
          setActiveSnapshot(snapshot);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to load run snapshot:", err);
        }
      } finally {
        if (!cancelled) {
          setLoadingDetail(false);
        }
      }
    }
    loadRunDetail(selectedRunId);
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  // Filter runs based on search input (matching query, ID, or agent name)
  const filteredRuns = useMemo(() => {
    if (!searchQuery.trim()) return runs;
    const q = searchQuery.toLowerCase();
    return runs.filter(
      (r) =>
        r.run_id.toLowerCase().includes(q) ||
        r.input_query?.toLowerCase().includes(q) ||
        r.agent_name?.toLowerCase().includes(q)
    );
  }, [runs, searchQuery]);

  // Token metrics parsed from run metadata
  const tokenMetrics = useMemo(() => {
    if (!activeSnapshot?.metadata?.token_usage) return null;
    const u = activeSnapshot.metadata.token_usage as Record<string, number>;
    const input = u.input_tokens ?? 0;
    const output = u.output_tokens ?? 0;
    const cached = u.cached_tokens ?? 0;
    const total = u.total_tokens ?? input + output;
    const cacheHitPct = input > 0 ? Math.round((cached / input) * 100) : 0;
    return { input, output, cached, total, cacheHitPct };
  }, [activeSnapshot]);

  return (
    <div className="flex h-full max-h-screen">
      {/* ── Left Sidebar: Run Ledger List ──────────────────────────────────── */}
      <aside className="w-80 xl:w-96 border-r border-border-subtle bg-bg-secondary flex flex-col shrink-0 select-none">
        <div className="p-4 border-b border-border-subtle space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-base font-bold text-text-primary flex items-center gap-2">
                <span>📜</span>
                <span>Agent Audit Log</span>
              </h1>
              <p className="text-[0.68rem] text-text-muted mt-0.5">
                Full-fidelity execution traces &amp; graph topology
              </p>
            </div>
            <span className="text-[0.65rem] font-mono px-2 py-0.5 rounded-full bg-bg-tertiary text-text-secondary">
              {filteredRuns.length} runs
            </span>
          </div>

          {/* Search / Filter input */}
          <div className="relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search runs by query, ID, or agent..."
              className="w-full text-xs px-3 py-1.5 rounded-lg bg-bg-primary/70 border border-border-subtle text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-cyan"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-1.5 text-xs text-text-muted hover:text-text-primary"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Run List Items */}
        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {loadingList ? (
            <div className="space-y-2 p-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="glass-card p-3 h-16 animate-pulse" />
              ))}
            </div>
          ) : filteredRuns.length === 0 ? (
            <div className="text-center py-12 px-4 opacity-60 text-xs text-text-muted">
              No matching run snapshots found in `logs/runs/`.
            </div>
          ) : (
            filteredRuns.map((r) => {
              const isSelected = r.run_id === selectedRunId;
              const dateStr = r.timestamp
                ? new Date(r.timestamp).toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "Unknown time";
              return (
                <button
                  key={r.run_id}
                  type="button"
                  onClick={() => setSelectedRunId(r.run_id)}
                  className={`w-full text-left p-3 rounded-xl border transition-all flex flex-col gap-1.5 ${
                    isSelected
                      ? "bg-accent-cyan/15 border-accent-cyan/40 shadow-[0_0_15px_rgba(56,189,248,0.12)] text-text-primary"
                      : "bg-bg-tertiary/40 border-border-subtle/60 text-text-secondary hover:bg-bg-tertiary hover:text-text-primary"
                  }`}
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-mono text-[0.68rem] font-bold text-accent-cyan">
                      #{r.run_id}
                    </span>
                    <span className="text-[0.62rem] text-text-muted">
                      {dateStr}
                    </span>
                  </div>

                  <p className="text-xs font-medium text-text-primary line-clamp-2 leading-snug">
                    {r.input_query || "(empty query)"}
                  </p>

                  <div className="flex items-center gap-2 flex-wrap text-[0.62rem] font-mono text-text-muted pt-1 border-t border-border-subtle/30">
                    <span className="px-1.5 py-0.2 rounded bg-bg-primary/60 text-cyan-300">
                      {r.agent_name || "nexus"}
                    </span>
                    {r.subagents_count !== undefined && r.subagents_count > 0 && (
                      <span className="px-1.5 py-0.2 rounded bg-fuchsia-500/20 text-fuchsia-300">
                        ⚡ {r.subagents_count} subagent{r.subagents_count === 1 ? "" : "s"}
                      </span>
                    )}
                    {r.latency_seconds !== null && (
                      <span>⏱️ {r.latency_seconds}s</span>
                    )}
                    <span>🔧 {r.tool_calls_count} tools</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </aside>

      {/* ── Main Panel: Run Detail Inspector ───────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 max-h-screen bg-bg-primary">
        {loadingDetail && !activeSnapshot ? (
          <div className="flex-1 flex items-center justify-center text-xs text-text-muted animate-pulse">
            Loading run snapshot #{selectedRunId}...
          </div>
        ) : !activeSnapshot ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 opacity-60">
            <span className="text-4xl mb-3">🔍</span>
            <p className="text-sm text-text-secondary">
              Select a run from the ledger to inspect its full execution graph, subagents, and telemetry.
            </p>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0">
            {/* ── Run Overview Header ── */}
            <header className="px-8 py-4 border-b border-border-subtle bg-bg-secondary/40 shrink-0">
              <div className="flex items-center justify-between gap-4 flex-wrap mb-2">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">🧠</span>
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-base font-bold text-text-primary">
                        Run Snapshot <span className="font-mono text-accent-cyan">#{activeSnapshot.run_id}</span>
                      </h2>
                      <span className="text-[0.65rem] font-mono px-2 py-0.5 rounded-full bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30">
                        {activeSnapshot.agent_name}
                      </span>
                      {activeSnapshot.domain && (
                        <span className="text-[0.65rem] font-mono px-2 py-0.5 rounded-full bg-bg-tertiary text-text-secondary">
                          domain: {activeSnapshot.domain}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-text-muted mt-0.5 font-mono">
                      {new Date(activeSnapshot.timestamp).toLocaleString()} • Thread ID: {activeSnapshot.thread_id}
                    </p>
                  </div>
                </div>

                {/* Quick stats pills */}
                <div className="flex items-center gap-2 flex-wrap font-mono text-xs">
                  {activeSnapshot.latency_seconds !== null && (
                    <div className="glass-card px-3 py-1.5 flex items-center gap-1.5">
                      <span className="text-text-muted">Latency:</span>
                      <span className="text-text-primary font-bold">
                        {activeSnapshot.latency_seconds}s
                      </span>
                    </div>
                  )}
                  {tokenMetrics && (
                    <div className="glass-card px-3 py-1.5 flex items-center gap-2">
                      <span className="text-text-muted">Tokens:</span>
                      <span className="text-accent-cyan font-semibold">
                        {tokenMetrics.input.toLocaleString()} in
                      </span>
                      <span className="text-emerald-400 font-semibold">
                        ({tokenMetrics.cached.toLocaleString()} cached, {tokenMetrics.cacheHitPct}%)
                      </span>
                      <span className="text-purple-300 font-semibold">
                        | {tokenMetrics.output.toLocaleString()} out
                      </span>
                    </div>
                  )}
                  <div className="glass-card px-3 py-1.5 flex items-center gap-1.5">
                    <span className="text-text-muted">Trace:</span>
                    <span className="text-text-primary font-bold">
                      {activeSnapshot.trace_events?.length ?? 0} steps
                    </span>
                  </div>
                </div>
              </div>

              {/* View Navigation Tabs */}
              <div className="flex items-center gap-1 pt-2 border-t border-border-subtle/50 text-xs">
                <button
                  type="button"
                  onClick={() => setActiveTab("graph")}
                  className={`px-3 py-1.5 rounded-lg font-medium transition-colors flex items-center gap-1.5 ${
                    activeTab === "graph"
                      ? "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40"
                      : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
                  }`}
                >
                  <span>🕸️</span>
                  <span>Execution Graph (DAG)</span>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveTab("subagents")}
                  className={`px-3 py-1.5 rounded-lg font-medium transition-colors flex items-center gap-1.5 ${
                    activeTab === "subagents"
                      ? "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40"
                      : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
                  }`}
                >
                  <span>⚡</span>
                  <span>
                    Subagent Swarm ({activeSnapshot.subagents?.length ?? 0})
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveTab("steps")}
                  className={`px-3 py-1.5 rounded-lg font-medium transition-colors flex items-center gap-1.5 ${
                    activeTab === "steps"
                      ? "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40"
                      : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
                  }`}
                >
                  <span>📜</span>
                  <span>
                    All Steps ({activeSnapshot.trace_events?.length ?? 0})
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveTab("io")}
                  className={`px-3 py-1.5 rounded-lg font-medium transition-colors flex items-center gap-1.5 ${
                    activeTab === "io"
                      ? "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40"
                      : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
                  }`}
                >
                  <span>💬</span>
                  <span>Prompt &amp; Output</span>
                </button>

                <button
                  type="button"
                  onClick={() => setActiveTab("json")}
                  className={`px-3 py-1.5 rounded-lg font-medium transition-colors flex items-center gap-1.5 ${
                    activeTab === "json"
                      ? "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40"
                      : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
                  }`}
                >
                  <span>{"{ }"}</span>
                  <span>Raw Snapshot JSON</span>
                </button>
              </div>
            </header>

            {/* ── Tab Content Body ── */}
            <div className="flex-1 overflow-y-auto px-8 py-6">
              {/* Tab 1: Visual Execution Graph (DAG) */}
              {activeTab === "graph" && (
                <div className="max-w-6xl mx-auto">
                  <AgentGraphView
                    events={activeSnapshot.trace_events || []}
                    isLive={false}
                  />
                </div>
              )}

              {/* Tab 2: Dedicated Subagent Swarm Breakdown */}
              {activeTab === "subagents" && (
                <div className="max-w-6xl mx-auto space-y-4">
                  {(!activeSnapshot.subagents || activeSnapshot.subagents.length === 0) ? (
                    <div className="glass-card p-8 text-center opacity-60 text-xs text-text-secondary">
                      No subagents were spawned during this run. The primary orchestrator completed all tasks directly.
                    </div>
                  ) : (
                    activeSnapshot.subagents.map((sub, idx) => {
                      const theme = AGENT_THEME[sub.color] ?? AGENT_THEME.magenta;
                      return (
                        <div
                          key={sub.agent_id ?? idx}
                          className={`rounded-2xl border ${theme.border} bg-bg-secondary/70 p-5 space-y-3.5`}
                        >
                          <div className="flex items-center justify-between border-b border-border-subtle/60 pb-3 flex-wrap gap-2">
                            <div className="flex items-center gap-2">
                              <span className="text-xl">⚡</span>
                              <div>
                                <h3 className={`font-bold text-sm ${theme.text}`}>
                                  {sub.agent_name}
                                </h3>
                                <p className="text-[0.68rem] font-mono text-text-muted mt-0.5">
                                  ID: {sub.agent_id} • Parent: {sub.parent_id ?? "nexus"} • Tier: {sub.model_tier}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2 font-mono text-[0.68rem]">
                              <span className="px-2 py-0.5 rounded bg-bg-tertiary text-text-secondary">
                                🔧 {sub.tool_calls?.length ?? 0} tool calls
                              </span>
                              <span className="px-2 py-0.5 rounded bg-bg-tertiary text-text-secondary">
                                📋 {sub.steps?.length ?? 0} steps
                              </span>
                            </div>
                          </div>

                          {/* Full Untruncated Subagent Prompt */}
                          <div>
                            <div className="text-[0.65rem] font-mono uppercase tracking-wider text-accent-cyan mb-1">
                              Full Subagent Task Prompt (Untruncated, {sub.task_prompt?.length.toLocaleString()} chars):
                            </div>
                            <pre className="p-3.5 rounded-xl bg-bg-primary/90 border border-border-subtle text-text-primary font-mono text-xs leading-relaxed whitespace-pre-wrap break-words">
                              {sub.task_prompt}
                            </pre>
                          </div>

                          {/* Tool Invocations inside this Subagent */}
                          {sub.tool_calls && sub.tool_calls.length > 0 && (
                            <div>
                              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-text-muted mb-1.5">
                                Tools Executed ({sub.tool_calls.length}):
                              </div>
                              <div className="space-y-2">
                                {sub.tool_calls.map((tc, tcIdx) => (
                                  <div
                                    key={tc.call_id ?? tcIdx}
                                    className="rounded-lg bg-bg-primary/80 border border-border-subtle p-3 space-y-2 text-xs"
                                  >
                                    <div className="flex items-center justify-between font-mono text-[0.72rem]">
                                      <span className="font-bold text-accent-cyan">
                                        🔧 {tc.tool}()
                                      </span>
                                      {tc.timestamp && (
                                        <span className="text-text-muted text-[0.65rem]">
                                          {new Date(tc.timestamp).toLocaleTimeString()}
                                        </span>
                                      )}
                                    </div>
                                    {tc.args && Object.keys(tc.args).length > 0 && (
                                      <div>
                                        <div className="text-[0.62rem] font-mono uppercase tracking-wider text-text-muted mb-0.5">
                                          Arguments:
                                        </div>
                                        <pre className="p-2 rounded bg-bg-secondary text-text-secondary font-mono text-[0.7rem] whitespace-pre-wrap break-words">
                                          {JSON.stringify(tc.args, null, 2)}
                                        </pre>
                                      </div>
                                    )}
                                    {tc.result && (
                                      <div>
                                        <div className="text-[0.62rem] font-mono uppercase tracking-wider text-emerald-400 mb-0.5">
                                          Output ({tc.result.length.toLocaleString()} chars):
                                        </div>
                                        <pre className="p-2 rounded bg-bg-secondary text-text-primary font-mono text-[0.7rem] whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                                          {tc.result}
                                        </pre>
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Final Synthesis Returned by Subagent */}
                          {sub.final_response && (
                            <div>
                              <div className="text-[0.65rem] font-mono uppercase tracking-wider text-emerald-400 mb-1">
                                Synthesis Returned to Orchestrator ({sub.final_response.length.toLocaleString()} chars):
                              </div>
                              <div className="p-4 rounded-xl bg-bg-primary/90 border border-emerald-500/30 text-text-primary text-xs">
                                <MarkdownMessage content={sub.final_response} />
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              )}

              {/* Tab 3: Chronological Step-by-Step Trace */}
              {activeTab === "steps" && (
                <div className="max-w-6xl mx-auto space-y-2">
                  <AgentGraphView
                    events={activeSnapshot.trace_events || []}
                    isLive={false}
                  />
                </div>
              )}

              {/* Tab 4: Prompt and Final Output */}
              {activeTab === "io" && (
                <div className="max-w-4xl mx-auto space-y-6">
                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-accent-cyan mb-2">
                      Input Prompt (Full Untruncated User Query)
                    </h3>
                    <div className="p-4 rounded-xl bg-accent-cyan/10 border border-accent-cyan/20 text-text-primary text-sm whitespace-pre-wrap leading-relaxed">
                      {activeSnapshot.input_query}
                    </div>
                  </div>

                  <div>
                    <h3 className="text-xs font-bold uppercase tracking-wider text-purple-300 mb-2">
                      Assistant Markdown Response
                    </h3>
                    <div className="glass-card p-6 text-sm text-text-primary leading-relaxed">
                      <MarkdownMessage content={activeSnapshot.output_response} />
                    </div>
                  </div>
                </div>
              )}

              {/* Tab 5: Raw JSON Snapshot */}
              {activeTab === "json" && (
                <div className="max-w-6xl mx-auto">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-mono text-text-muted uppercase tracking-wider">
                      Full JSON Document ({JSON.stringify(activeSnapshot).length.toLocaleString()} bytes)
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(JSON.stringify(activeSnapshot, null, 2));
                      }}
                      className="text-xs px-3 py-1 rounded-md bg-bg-tertiary text-accent-cyan hover:bg-bg-tertiary/80 transition-colors"
                    >
                      Copy JSON
                    </button>
                  </div>
                  <pre className="p-4 rounded-xl bg-bg-secondary/90 border border-border-subtle text-text-primary font-mono text-[0.72rem] leading-relaxed whitespace-pre-wrap break-words overflow-x-auto">
                    {JSON.stringify(activeSnapshot, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
