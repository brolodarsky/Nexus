"use client";

/**
 * BlackboardDrawer.tsx — Right-hand situational feed drawer for the Shared Agent Blackboard (`blackboard.db`).
 * Renders live bulletins published by Flash subagents and Astra, with individual card expand/collapse,
 * manual refresh, unpinned bulletin clearing, and per-bulletin dismissal.
 */

import { useState } from "react";
import MarkdownMessage from "@/components/MarkdownMessage";
import type { BoardBulletin } from "@/lib/api";

// BlackboardDrawerProps: defines bulletin items and action handlers for the right-side Blackboard drawer
// - bulletins: array of BoardBulletin records fetched from GET /api/board
// - onRefresh: callback to re-fetch recent bulletins from the backend
// - onClear: async callback to clear all unpinned bulletins and refresh the list
// - onDismiss: async callback to delete a specific bulletin by ID and refresh the list
// - onClose: callback to collapse/close the Blackboard drawer
export interface BlackboardDrawerProps {
  bulletins: BoardBulletin[];
  onRefresh: () => void;
  onClear: () => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onClose: () => void;
}

export default function BlackboardDrawer({
  bulletins,
  onRefresh,
  onClear,
  onDismiss,
  onClose,
}: BlackboardDrawerProps) {
  // Local expand/collapse dictionary keyed by bulletin ID (defaults to true/expanded)
  // Keeping this state localized inside BlackboardDrawer prevents re-rendering the chat thread when toggling cards
  const [expandedBulletinIds, setExpandedBulletinIds] = useState<Record<number, boolean>>({});

  return (
    <aside className="w-80 xl:w-96 border-l border-border-subtle bg-bg-secondary flex flex-col shrink-0 max-h-screen">
      <div className="p-4 border-b border-border-subtle flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-text-primary flex items-center gap-1.5">
            <span>📋</span>
            <span>Agent Blackboard</span>
          </h2>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={onRefresh}
            className="text-xs px-2 py-1 rounded-md bg-bg-tertiary text-text-secondary hover:text-accent-cyan transition-colors"
            title="Refresh Blackboard"
          >
            ↻
          </button>
          {bulletins.length > 0 && (
            <button
              onClick={onClear}
              className="text-[0.68rem] px-2 py-1 rounded-md bg-bg-tertiary text-text-muted hover:text-red-400 transition-colors"
              title="Clear unpinned bulletins"
            >
              Clear
            </button>
          )}
          {/* Symmetrical drawer collapse toggle */}
          <button
            type="button"
            onClick={onClose}
            className="text-xs px-2 py-1 rounded-md bg-bg-tertiary text-text-muted hover:text-text-primary transition-colors flex items-center justify-center"
            title="Collapse Blackboard menu"
            aria-label="Collapse Blackboard menu"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Bulletin Feed */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {bulletins.length === 0 ? (
          <div className="text-center py-12 px-4 opacity-60">
            <div className="text-2xl mb-2">⚡</div>
            <p className="text-xs text-text-secondary">
              No bulletins posted yet. When Astra dispatches Flash subagents for email, calendar, or Vault sweeps, their distilled reports land here automatically.
            </p>
          </div>
        ) : (
          bulletins.map((b) => {
            const isExpanded = expandedBulletinIds[b.id] ?? true;
            return (
              <div
                key={b.id}
                className="rounded-xl border border-border-subtle bg-bg-tertiary/40 p-3 text-xs space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedBulletinIds((prev) => ({
                        ...prev,
                        [b.id]: !isExpanded,
                      }))
                    }
                    className="text-left flex-1 min-w-0"
                  >
                    <div className="flex items-center gap-1.5 flex-wrap mb-1">
                      {b.pinned ? (
                        <span className="text-[0.65rem]" title="Pinned bulletin">
                          📌
                        </span>
                      ) : null}
                      <span className="text-[0.65rem] text-purple-300 font-medium truncate">
                        {b.author}
                      </span>
                      <span className="text-[0.6rem] text-text-muted ml-auto">
                        #{b.id}
                      </span>
                    </div>
                    <div className="font-semibold text-text-primary leading-snug line-clamp-2">
                      {b.title}
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => onDismiss(b.id)}
                    className="text-text-muted hover:text-red-400 text-[0.65rem] px-1"
                    title="Dismiss bulletin"
                  >
                    ✕
                  </button>
                </div>
                {isExpanded && (
                  <div className="pt-1.5 border-t border-border-subtle/60 text-xs max-h-64 overflow-y-auto">
                    <MarkdownMessage content={b.content} />
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}

