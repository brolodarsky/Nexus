"use client";

/**
 * MessageBranchTrigger.tsx — Modular per-message branching controls and child-branch badges.
 * Rendered inside `ChatMessageItem` so users can fork any turn into either:
 *   1. `tangent` (Proportional Parent Context Brief + focal turn in a fresh context window)
 *   2. `fork` (Full verbatim history clone up to this turn)
 * Also renders clickable pills for any child branches already spawned from this message.
 */

import { useState, memo } from "react";
import type { BranchMode, Conversation } from "@/lib/api";

// MessageBranchTriggerProps: defines the callbacks and lineage metadata for a single message turn
// - messageIndex: 0-based position of this message inside the active conversation thread
// - messageId: optional SQLite `messages.id` primary key
// - spawnedBranches: optional list of child Conversation records forked from this message
// - isBranching: boolean indicating whether a branch request is currently in-flight for this message
// - onBranch: callback to trigger branching from this message with the chosen `BranchMode`
// - onSelectConversation: callback to navigate directly to an existing child branch conversation
export interface MessageBranchTriggerProps {
  messageIndex: number;
  messageId?: number;
  spawnedBranches?: Conversation[];
  isBranching?: boolean;
  onBranch?: (messageIndex: number, messageId: number | undefined, mode: BranchMode) => Promise<void> | void;
  onSelectConversation?: (conversationId: string) => void;
}

const MessageBranchTrigger = memo(function MessageBranchTrigger({
  messageIndex,
  messageId,
  spawnedBranches,
  isBranching = false,
  onBranch,
  onSelectConversation,
}: MessageBranchTriggerProps) {
  // showMenu: controls whether the inline Tangent vs Full Fork mode selector popover is open
  const [showMenu, setShowMenu] = useState<boolean>(false);

  const handleTriggerMode = async (mode: BranchMode) => {
    setShowMenu(false);
    if (onBranch) {
      await onBranch(messageIndex, messageId, mode);
    }
  };

  return (
    <div className="relative inline-flex items-center gap-1.5 flex-wrap">
      {/* Existing child branches spawned from this message turn */}
      {spawnedBranches &&
        spawnedBranches.length > 0 &&
        spawnedBranches.map((child) => (
          <button
            key={child.id}
            type="button"
            onClick={() => onSelectConversation?.(child.id)}
            title={`Jump to branch: ${child.title}${child.merged_at ? " (Merged)" : ""}`}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.65rem] font-mono border transition-colors cursor-pointer ${
              child.merged_at
                ? "bg-emerald-500/10 hover:bg-emerald-500/20 border-emerald-500/30 text-emerald-300"
                : "bg-teal-500/15 hover:bg-teal-500/25 border-teal-500/35 text-teal-300"
            }`}
          >
            <span>🌿</span>
            <span className="max-w-[140px] truncate">{child.title.replace(/^🌿\s*/, "")}</span>
            {child.merged_at && <span title="Distilled & merged back to parent">✓</span>}
            <span>→</span>
          </button>
        ))}

      {/* Branch from here action button */}
      {onBranch && (
        <div className="relative inline-flex items-center">
          <button
            type="button"
            disabled={isBranching}
            onClick={() => setShowMenu((prev) => !prev)}
            title="Branch conversation from this turn (Tangent ALU or Full History Fork)"
            aria-label="Branch from this message"
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.65rem] font-mono font-medium border transition-colors cursor-pointer ${
              isBranching
                ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300 animate-pulse"
                : "bg-emerald-500/10 hover:bg-emerald-500/20 border-emerald-500/30 text-emerald-300"
            }`}
          >
            <span>🌿</span>
            <span>{isBranching ? "Branching…" : "Branch"}</span>
          </button>

          {/* Inline Mode Selector Popover */}
          {showMenu && !isBranching && (
            <div
              className="absolute right-0 top-full mt-1.5 w-64 rounded-xl border border-border-subtle bg-bg-secondary/95 backdrop-blur-md shadow-2xl p-1.5 z-30 text-left space-y-1"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                onClick={() => handleTriggerMode("tangent")}
                className="w-full text-left px-2.5 py-2 rounded-lg hover:bg-emerald-500/15 transition-colors group"
              >
                <div className="flex items-center justify-between text-xs font-semibold text-emerald-300">
                  <span>🌿 Tangent Branch (Fresh ALU)</span>
                  <span className="text-[0.6rem] font-mono px-1.5 py-0.2 rounded bg-emerald-500/20 border border-emerald-500/30">
                    Default
                  </span>
                </div>
                <p className="text-[0.68rem] text-text-muted mt-0.5 leading-snug">
                  Synthesizes prior context into a proportional brief + keeps this turn in a clean context window.
                </p>
              </button>

              <button
                type="button"
                onClick={() => handleTriggerMode("fork")}
                className="w-full text-left px-2.5 py-2 rounded-lg hover:bg-accent-cyan/15 transition-colors group"
              >
                <div className="text-xs font-semibold text-accent-cyan">
                  🔀 Full History Fork
                </div>
                <p className="text-[0.68rem] text-text-muted mt-0.5 leading-snug">
                  Clones all messages up to this turn verbatim into a new parallel thread.
                </p>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

export default MessageBranchTrigger;
