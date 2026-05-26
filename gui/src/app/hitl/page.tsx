"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getPendingHitl, approveHitl, rejectHitl, Transaction } from "@/lib/api";
import { DiffEditor } from "@monaco-editor/react";

export default function HitlPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchPending() {
    setLoading(true);
    try {
      const pending = await getPendingHitl();
      setTransactions(pending);
      if (pending.length > 0 && !selectedTx) {
        setSelectedTx(pending[0]);
      } else if (pending.length === 0) {
        setSelectedTx(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch HITL queue");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchPending();
  }, []);

  async function handleApprove() {
    if (!selectedTx) return;
    setActionLoading(true);
    try {
      await approveHitl(selectedTx.id);
      await fetchPending();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to approve transaction");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleReject() {
    if (!selectedTx) return;
    setActionLoading(true);
    try {
      await rejectHitl(selectedTx.id);
      await fetchPending();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reject transaction");
    } finally {
      setActionLoading(false);
    }
  }

  let reasoningDisplay = null;
  if (selectedTx?.reasoning) {
    try {
      const parsed = JSON.parse(selectedTx.reasoning);
      reasoningDisplay = (
        <div className="text-sm">
          <p><span className="font-medium text-text-primary">Decision:</span> {parsed.decision}</p>
          <p className="mt-1"><span className="font-medium text-text-primary">Confidence:</span> {(parsed.confidence * 100).toFixed(0)}%</p>
          {parsed.alternatives_considered?.length > 0 && (
            <p className="mt-1"><span className="font-medium text-text-primary">Alternatives:</span> {parsed.alternatives_considered.join(", ")}</p>
          )}
        </div>
      );
    } catch {
      reasoningDisplay = <p className="text-sm">{selectedTx.reasoning}</p>;
    }
  }

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
                    onClick={() => setSelectedTx(tx)}
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
      </div>

      {/* Main Review Area */}
      <div className="flex-1 flex flex-col bg-background-dark/10">
        {error && (
          <div className="p-4 bg-accent-rose/10 text-accent-rose border-b border-accent-rose/20 text-sm flex justify-between items-center">
            {error}
            <button onClick={() => setError(null)} className="opacity-50 hover:opacity-100">✕</button>
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
                    onClick={handleApprove} 
                    disabled={actionLoading}
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
            </div>

            {/* Diff Viewer */}
            <div className="flex-1 min-h-0 relative">
              <DiffEditor
                height="100%"
                language="markdown"
                original={selectedTx.original_content || ""}
                modified={selectedTx.proposed_content}
                theme="vs-dark"
                options={{
                  renderSideBySide: true,
                  minimap: { enabled: false },
                  readOnly: true,
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                  fontFamily: "var(--font-mono)",
                  fontSize: 14,
                  padding: { top: 16 }
                }}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
