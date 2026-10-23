"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getPendingHitl,
  approveHitl,
  rejectHitl,
  rebaseHitl,
  rollbackHitl,
  getRecentRevisions,
  ApiError,
  isHitlConflict,
  type Transaction,
  type HitlConflictDetail,
  type HitlRevision,
} from "@/lib/api";
import { DiffEditor } from "@monaco-editor/react";
// MarkdownMessage: Shared GFM + [[Wiki-Link]] renderer, reused here for the Pre-Commit Preview tab
import MarkdownMessage from "@/components/MarkdownMessage";

// Which pane the main review area shows:
//   diff     -> agent baseline vs proposal (the classic review)
//   preview  -> full rendered note AFTER the change (what you'll actually read in Obsidian)
//   conflict -> 3-way stale-base view, only reachable after a 409 on approve
type ReviewView = "diff" | "preview" | "conflict";
// Inside the conflict view: inspect your own drift, or the exact overwrite approval would perform
type ConflictPane = "your_edits" | "would_write";

// Shared Monaco options (read-only, side-by-side) so every diff pane looks identical
const DIFF_OPTIONS = {
  renderSideBySide: true,
  minimap: { enabled: false },
  readOnly: true,
  scrollBeyondLastLine: false,
  wordWrap: "on" as const, // `as const` narrows the string to Monaco's literal union type ("on" | "off" | ...)
  fontFamily: "var(--font-mono)",
  fontSize: 14,
  padding: { top: 16 },
};

export default function HitlPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useState<ReviewView>("diff");
  const [conflict, setConflict] = useState<HitlConflictDetail | null>(null);
  const [conflictPane, setConflictPane] = useState<ConflictPane>("your_edits");
  const [revisions, setRevisions] = useState<HitlRevision[]>([]);
  // isQueueCollapsed: toggles the left review queue sidebar between expanded (w-1/3) and collapsed rail (w-14)
  const [isQueueCollapsed, setIsQueueCollapsed] = useState(false);
  // isRecentCollapsed: accordion toggle to collapse/expand the Recently Applied undo ledger sub-menu
  const [isRecentCollapsed, setIsRecentCollapsed] = useState(false);
  // isReasoningCollapsed: allows collapsing the agent reasoning card to maximize vertical diff editor real estate
  const [isReasoningCollapsed, setIsReasoningCollapsed] = useState(false);

  // useCallback: Memoizes the function so callers can reuse a stable reference across renders.
  // keepId: After approve/rebase we re-select by ID from the FRESH list, so the panel never shows a stale
  // (already-approved or pre-rebase) copy of the transaction — the old code kept the stale object selected.
  const fetchPending = useCallback(async (keepId?: number) => {
    setLoading(true);
    try {
      // Promise.all: Runs both requests concurrently and waits for both (queue + undo list)
      const [pending, recent] = await Promise.all([getPendingHitl(), getRecentRevisions(10)]);
      setTransactions(pending);
      setRevisions(recent);
      // ?? : Falls back to the first card when the kept ID is gone (approved/rejected) or none was given
      const next = (keepId !== undefined ? pending.find(t => t.id === keepId) : undefined) ?? pending[0] ?? null;
      setSelectedTx(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch HITL queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true; // Cleanup flag prevents setting state if the component unmounts mid-request
    Promise.all([getPendingHitl(), getRecentRevisions(10)])
      .then(([pending, recent]) => {
        if (!active) return;
        setTransactions(pending);
        setRevisions(recent);
        setSelectedTx(pending[0] ?? null);
      })
      .catch(e => {
        if (active) setError(e instanceof Error ? e.message : "Failed to fetch HITL queue");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  // Switching cards clears any conflict state that belonged to the previous card
  function selectTx(tx: Transaction) {
    setSelectedTx(tx);
    setConflict(null);
    setView("diff");
  }

  async function handleApprove(force = false) {
    if (!selectedTx) return;
    setActionLoading(true);
    setError(null);
    try {
      const res = await approveHitl(selectedTx.id, force);
      setNotice(`Applied #${selectedTx.id} → ${res.target_file.split("/").pop()}${res.forced ? " (forced)" : ""}. Undo is available below.`);
      setConflict(null);
      setView("diff");
      await fetchPending();
    } catch (e) {
      // 409 stale_base: the note changed on disk since staging -> open the 3-way conflict view instead of failing
      if (e instanceof ApiError && e.status === 409 && isHitlConflict(e.detail)) {
        setConflict(e.detail);
        setConflictPane("your_edits");
        setView("conflict");
      } else {
        setError(e instanceof Error ? e.message : "Failed to approve transaction");
      }
    } finally {
      setActionLoading(false);
    }
  }

  async function handleReject() {
    if (!selectedTx) return;
    setActionLoading(true);
    try {
      await rejectHitl(selectedTx.id);
      setConflict(null);
      setView("diff");
      await fetchPending();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reject transaction");
    } finally {
      setActionLoading(false);
    }
  }

  // Rebase: 3-way merge the agent's edit onto the current disk text, then show the refreshed diff
  async function handleRebase() {
    if (!selectedTx) return;
    setActionLoading(true);
    setError(null);
    try {
      const res = await rebaseHitl(selectedTx.id);
      setNotice(`#${selectedTx.id}: ${res.message}. Review the updated diff, then approve.`);
      setConflict(null);
      setView("diff");
      await fetchPending(selectedTx.id);
    } catch (e) {
      if (e instanceof ApiError && isHitlConflict(e.detail)) {
        setError(`Rebase failed: ${e.detail.message}`);
      } else {
        setError(e instanceof Error ? e.message : "Failed to rebase transaction");
      }
    } finally {
      setActionLoading(false);
    }
  }

  // Undo: restore the pre-approval snapshot; if the note changed since approval, ask before forcing
  async function handleUndo(rev: HitlRevision, force = false) {
    setActionLoading(true);
    setError(null);
    try {
      await rollbackHitl(rev.tx_id, force);
      setNotice(`Rolled back #${rev.tx_id} → ${rev.target_file.split("/").pop()}.`);
      await fetchPending(selectedTx?.id);
    } catch (e) {
      if (!force && e instanceof ApiError && e.status === 409) {
        // window.confirm: Blocking native dialog; returns true on OK. Forced undo still keeps the newer text in the ledger.
        const ok = window.confirm(
          `${rev.target_file.split("/").pop()} was edited after this approval.\n\n` +
          `Undo anyway? The newer text will be overwritten (but preserved in the revisions ledger).`
        );
        if (ok) {
          setActionLoading(false);
          return handleUndo(rev, true);
        }
      } else {
        setError(e instanceof Error ? e.message : "Failed to roll back transaction");
      }
    } finally {
      setActionLoading(false);
    }
  }

  // Parse structured JSON reasoning outside JSX construction to satisfy `react-hooks/error-boundaries`
  let parsedReasoning: { decision?: string; confidence?: number; alternatives_considered?: string[] } | null = null;
  if (selectedTx?.reasoning) {
    try {
      parsedReasoning = JSON.parse(selectedTx.reasoning);
    } catch {
      parsedReasoning = null;
    }
  }

  let reasoningDisplay = null;
  if (selectedTx?.reasoning) {
    if (parsedReasoning && typeof parsedReasoning === "object" && "decision" in parsedReasoning) {
      reasoningDisplay = (
        <div className="text-sm">
          <p><span className="font-medium text-text-primary">Decision:</span> {parsedReasoning.decision}</p>
          {typeof parsedReasoning.confidence === "number" && (
            <p className="mt-1"><span className="font-medium text-text-primary">Confidence:</span> {(parsedReasoning.confidence * 100).toFixed(0)}%</p>
          )}
          {parsedReasoning.alternatives_considered && parsedReasoning.alternatives_considered.length > 0 && (
            <p className="mt-1"><span className="font-medium text-text-primary">Alternatives:</span> {parsedReasoning.alternatives_considered.join(", ")}</p>
          )}
        </div>
      );
    } else {
      // whitespace-pre-line: keeps the "•" bullet lines produced by cumulative overlay stacking on separate rows
      reasoningDisplay = <p className="text-sm whitespace-pre-line">{selectedTx.reasoning}</p>;
    }
  }

  // Tab button styling helper (active tab gets the amber accent)
  const tabClass = (active: boolean) =>
    `px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
      active ? "bg-accent-amber/15 text-accent-amber" : "text-text-muted hover:text-text-secondary"
    }`;

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* ── Collapsible Queue Sidebar Menu ────────────────── */}
      {isQueueCollapsed ? (
        // Collapsed Rail: Slim column maximizing editor width, with quick-nav IDs and expand button
        <aside
          className="w-14 border-r border-background-light flex flex-col bg-background-dark/30 py-4 items-center shrink-0 transition-all duration-300 ease-in-out select-none"
          aria-label="Collapsed Review Queue"
        >
          <button
            onClick={() => setIsQueueCollapsed(false)}
            className="p-2 rounded-lg text-text-muted hover:text-accent-amber hover:bg-background-light/50 transition-colors flex items-center justify-center"
            title="Expand Review Queue"
            aria-label="Expand Review Queue"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            </svg>
          </button>

          {/* Pending Counter Badge */}
          <div
            onClick={() => setIsQueueCollapsed(false)}
            className="mt-3 cursor-pointer flex flex-col items-center gap-1 px-1.5 py-2 rounded-lg bg-accent-amber/10 border border-accent-amber/30 text-accent-amber text-[10px] font-semibold"
            title={`${transactions.length} Pending Decisions — Click to expand`}
          >
            <span>🔒</span>
            <span>{transactions.length}</span>
          </div>

          {/* Vertical list of pending transaction IDs for direct switching while collapsed */}
          <div className="mt-4 flex-1 overflow-y-auto space-y-2 w-full px-2 flex flex-col items-center">
            {transactions.map((tx) => (
              <button
                key={tx.id}
                onClick={() => selectTx(tx)}
                className={`w-9 h-9 rounded-lg flex items-center justify-center text-xs font-mono transition-all ${
                  selectedTx?.id === tx.id
                    ? "bg-accent-amber/20 text-accent-amber border border-accent-amber/50 shadow-[0_0_10px_rgba(251,191,36,0.2)] font-bold"
                    : "text-text-muted hover:text-text-primary hover:bg-background-light/40"
                }`}
                title={`#${tx.id} [${tx.agent_name}] ${tx.target_file.split("/").pop()}`}
              >
                {tx.id}
              </button>
            ))}
          </div>
        </aside>
      ) : (
        // Expanded Menu: Full details for pending transactions and collapsible Recently Applied undo ledger
        <aside
          className="w-1/3 max-w-sm border-r border-background-light flex flex-col bg-background-dark/30 shrink-0 transition-all duration-300 ease-in-out"
          aria-label="Review Queue Menu"
        >
          <div className="p-4 border-b border-background-light flex justify-between items-center">
            <div className="flex items-center gap-2">
              <h2 className="font-semibold text-lg">Review Queue</h2>
              <span className="bg-accent-amber/20 text-accent-amber text-xs px-2 py-0.5 rounded-full font-medium">
                {transactions.length} Pending
              </span>
            </div>
            {/* Collapse toggle button */}
            <button
              onClick={() => setIsQueueCollapsed(true)}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-background-light/50 transition-colors"
              title="Collapse Review Queue"
              aria-label="Collapse Review Queue"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              </svg>
            </button>
          </div>
          
          <div className="overflow-y-auto flex-1">
            {loading ? (
              <div className="p-4 text-text-muted text-sm">Loading queue...</div>
            ) : transactions.length === 0 ? (
              <div className="p-8 text-center text-text-muted text-sm">
                <span className="text-2xl block mb-2">🎉</span>
                No pending decisions.
              </div>
            ) : (
              <ul className="divide-y divide-background-light/50">
                {transactions.map(tx => (
                  <li key={tx.id}>
                    <button
                      onClick={() => selectTx(tx)}
                      className={`w-full text-left p-4 hover:bg-background-light/50 transition-colors ${
                        selectedTx?.id === tx.id ? "bg-background-light/80 border-l-2 border-accent-amber" : "border-l-2 border-transparent"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-text-muted uppercase tracking-wider">{tx.agent_name}</span>
                        <span className="text-[10px] text-text-muted">{new Date(tx.created_at).toLocaleTimeString()}</span>
                      </div>
                      <p className="font-medium text-sm text-text-primary truncate">{tx.action_type}</p>
                      <p className="text-xs text-text-muted truncate mt-1" title={tx.target_file}>
                        {tx.target_file.split("/").pop() || tx.target_file}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Recently Applied - Collapsible undo list backed by the `revisions` snapshot ledger */}
          {revisions.length > 0 && (
            <div className="border-t border-background-light shrink-0 overflow-hidden">
              <button
                type="button"
                onClick={() => setIsRecentCollapsed((prev) => !prev)}
                className="w-full px-4 py-2.5 flex items-center justify-between text-xs font-semibold text-text-muted uppercase tracking-wider hover:text-text-secondary hover:bg-background-light/30 transition-colors"
                title={isRecentCollapsed ? "Expand Recently Applied menu" : "Collapse Recently Applied menu"}
                aria-expanded={!isRecentCollapsed}
              >
                <span className="flex items-center gap-1.5">
                  <span>📜</span>
                  <span>Recently Applied ({revisions.length})</span>
                </span>
                <svg
                  className={`w-3.5 h-3.5 transition-transform duration-200 ${isRecentCollapsed ? "-rotate-90" : "rotate-0"}`}
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {!isRecentCollapsed && (
                <div className="max-h-48 overflow-y-auto">
                  <ul className="pb-2">
                    {revisions.map(rev => (
                      <li key={rev.id} className="px-4 py-1.5 flex items-center justify-between gap-2 text-xs">
                        <span className={`truncate ${rev.rolled_back ? "text-text-muted line-through" : "text-text-secondary"}`} title={rev.target_file}>
                          #{rev.tx_id} {rev.target_file.split("/").pop()}
                        </span>
                        {rev.rolled_back ? (
                          <span className="text-text-muted shrink-0">undone</span>
                        ) : (
                          <button
                            onClick={() => handleUndo(rev)}
                            disabled={actionLoading}
                            className="shrink-0 px-2 py-0.5 rounded border border-accent-rose/30 text-accent-rose hover:bg-accent-rose/10 disabled:opacity-50"
                          >
                            Undo
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </aside>
      )}

      {/* Main Review Area */}
      <div className="flex-1 flex flex-col bg-background-dark/10">
        {error && (
          <div className="p-4 bg-accent-rose/10 text-accent-rose border-b border-accent-rose/20 text-sm flex justify-between items-center">
            {error}
            <button onClick={() => setError(null)} className="opacity-50 hover:opacity-100">✕</button>
          </div>
        )}
        {notice && (
          <div className="p-3 bg-accent-cyan/10 text-accent-cyan border-b border-accent-cyan/20 text-sm flex justify-between items-center">
            {notice}
            <button onClick={() => setNotice(null)} className="opacity-50 hover:opacity-100">✕</button>
          </div>
        )}

        {!selectedTx ? (
          <div className="flex-1 flex items-center justify-center text-text-muted flex-col gap-4">
            <span className="text-4xl">🕵️‍♂️</span>
            <p>Select a transaction to review</p>
          </div>
        ) : (
          <>
            {/* Header / Context */}
            <div className="p-6 border-b border-background-light shrink-0">
              <div className="flex justify-between items-start mb-4">
                <div>
                  <h1 className="text-xl font-bold text-text-primary mb-1">
                    {selectedTx.action_type}: <span className="text-text-secondary">{selectedTx.target_file.split("/").pop()}</span>
                  </h1>
                  <p className="text-xs font-mono text-text-muted break-all">
                    {selectedTx.target_file}
                  </p>
                </div>
                <div className="flex gap-3">
                  <button 
                    onClick={handleReject} 
                    disabled={actionLoading}
                    className="px-4 py-2 rounded-lg border border-accent-rose/30 text-accent-rose hover:bg-accent-rose/10 transition-colors font-medium text-sm disabled:opacity-50"
                  >
                    Reject
                  </button>
                  <button 
                    onClick={() => handleApprove(false)} 
                    disabled={actionLoading || conflict !== null}
                    className="px-4 py-2 rounded-lg bg-accent-amber/10 border border-accent-amber/50 text-accent-amber hover:bg-accent-amber/20 transition-colors font-medium text-sm flex items-center gap-2 disabled:opacity-50 shadow-[0_0_15px_rgba(251,191,36,0.1)] hover:shadow-[0_0_20px_rgba(251,191,36,0.2)]"
                  >
                    {actionLoading ? "Processing..." : "Approve Change"}
                  </button>
                </div>
              </div>

              {reasoningDisplay && (
                <div className="mt-4 rounded-xl border border-background-light/50 bg-background-light/20 relative overflow-hidden transition-all">
                  <div className="absolute top-0 left-0 w-1 h-full bg-accent-cyan"></div>
                  <div className="p-3.5 flex items-center justify-between">
                    <h3 className="text-xs font-semibold text-accent-cyan uppercase tracking-wider flex items-center gap-2">
                      <span>🧠</span> Agent Reasoning
                    </h3>
                    <button
                      type="button"
                      onClick={() => setIsReasoningCollapsed((prev) => !prev)}
                      className="text-[0.65rem] text-text-muted hover:text-accent-cyan flex items-center gap-1.5 transition-colors px-2 py-0.5 rounded hover:bg-background-light/40"
                      title={isReasoningCollapsed ? "Expand Agent Reasoning" : "Collapse Agent Reasoning"}
                      aria-expanded={!isReasoningCollapsed}
                    >
                      <span>{isReasoningCollapsed ? "Show details" : "Collapse"}</span>
                      <svg
                        className={`w-3 h-3 transition-transform duration-200 ${isReasoningCollapsed ? "-rotate-90" : "rotate-0"}`}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                  </div>
                  {!isReasoningCollapsed && (
                    <div className="px-4 pb-4 pt-0">
                      {reasoningDisplay}
                    </div>
                  )}
                </div>
              )}

              {/* Stale-Base Conflict Banner - shown after approve returns 409 */}
              {conflict && (
                <div className="mt-4 p-4 rounded-xl border border-accent-rose/40 bg-accent-rose/5">
                  <h3 className="text-sm font-semibold text-accent-rose mb-1">⚠️ This note changed after the agent staged its edit</h3>
                  <p className="text-xs text-text-secondary mb-3">
                    {conflict.message} Approving as-is would erase whatever changed on disk. Rebase merges the agent&apos;s
                    edit onto the current note; Force overwrites it (the overwritten version stays recoverable via Undo).
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={handleRebase}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded-lg bg-accent-cyan/10 border border-accent-cyan/40 text-accent-cyan hover:bg-accent-cyan/20 text-xs font-medium disabled:opacity-50"
                    >
                      Rebase onto current
                    </button>
                    <button
                      onClick={() => handleApprove(true)}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded-lg border border-accent-rose/40 text-accent-rose hover:bg-accent-rose/10 text-xs font-medium disabled:opacity-50"
                    >
                      Force approve
                    </button>
                    <button
                      onClick={() => { setConflict(null); setView("diff"); }}
                      className="px-3 py-1.5 rounded-lg text-text-muted hover:text-text-secondary text-xs"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {/* View Tabs */}
              <div className="mt-4 flex gap-1">
                <button onClick={() => setView("diff")} className={tabClass(view === "diff")}>Diff</button>
                <button onClick={() => setView("preview")} className={tabClass(view === "preview")}>Preview Result</button>
                {conflict && (
                  <button onClick={() => setView("conflict")} className={tabClass(view === "conflict")}>Conflict (3-way)</button>
                )}
              </div>
            </div>

            {/* Diff Viewer */}
            {view === "diff" && (
              <div className="flex-1 min-h-0 relative">
                <DiffEditor
                  height="100%"
                  language="markdown"
                  original={selectedTx.original_content || ""}
                  modified={selectedTx.proposed_content}
                  theme="vs-dark"
                  options={DIFF_OPTIONS}
                />
              </div>
            )}

            {/* Pre-Commit Preview - full rendered note after the change */}
            {view === "preview" && (
              <div className="flex-1 min-h-0 overflow-y-auto p-8">
                <div className="max-w-3xl mx-auto">
                  <MarkdownMessage content={selectedTx.proposed_content} />
                </div>
              </div>
            )}

            {/* 3-Way Conflict Viewer - your drift vs. what approval would overwrite */}
            {view === "conflict" && conflict && (
              <div className="flex-1 min-h-0 flex flex-col">
                <div className="px-6 py-2 flex items-center gap-1 border-b border-background-light text-xs">
                  <button onClick={() => setConflictPane("your_edits")} className={tabClass(conflictPane === "your_edits")}>
                    What changed on disk
                  </button>
                  <button onClick={() => setConflictPane("would_write")} className={tabClass(conflictPane === "would_write")}>
                    What Force would write
                  </button>
                  <span className="ml-3 text-text-muted">
                    {conflictPane === "your_edits"
                      ? "Left: agent's baseline · Right: current disk"
                      : "Left: current disk · Right: agent proposal (red on the left gets lost)"}
                  </span>
                </div>
                <div className="flex-1 min-h-0 relative">
                  <DiffEditor
                    // key: Forces Monaco to remount when switching panes so both models are swapped cleanly
                    key={conflictPane}
                    height="100%"
                    language="markdown"
                    original={conflictPane === "your_edits" ? (selectedTx.original_content || "") : (conflict.current_content ?? "")}
                    modified={conflictPane === "your_edits" ? (conflict.current_content ?? "") : selectedTx.proposed_content}
                    theme="vs-dark"
                    options={DIFF_OPTIONS}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
