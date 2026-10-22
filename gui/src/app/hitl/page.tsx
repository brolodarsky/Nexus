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
      {/* Sidebar - Queue */}
      <div className="w-1/3 max-w-sm border-r border-background-light flex flex-col bg-background-dark/30">
        <div className="p-4 border-b border-background-light flex justify-between items-center">
          <h2 className="font-semibold text-lg">Review Queue</h2>
          <span className="bg-accent-amber/20 text-accent-amber text-xs px-2 py-1 rounded-full font-medium">
            {transactions.length} Pending
          </span>
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

        {/* Recently Applied - Undo list backed by the `revisions` snapshot ledger */}
        {revisions.length > 0 && (
          <div className="border-t border-background-light max-h-[35%] overflow-y-auto shrink-0">
            <h3 className="px-4 pt-3 pb-2 text-xs font-semibold text-text-muted uppercase tracking-wider">Recently Applied</h3>
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
                <div className="mt-4 p-4 rounded-xl border border-background-light/50 bg-background-light/20 relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-1 h-full bg-accent-cyan"></div>
                  <h3 className="text-xs font-semibold text-accent-cyan uppercase tracking-wider mb-2 flex items-center gap-2">
                    <span>🧠</span> Agent Reasoning
                  </h3>
                  {reasoningDisplay}
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
