"use client";

/**
 * BranchLineageBar.tsx — Subroutine lineage breadcrumb and "Distill & Merge to Parent" bar.
 * Displays parent thread ancestry when inside a child branch, allows one-click or guided
 * proportional distillation back to the parent thread, and surfaces child branch pills on parent threads.
 */

import { useState, memo } from "react";
import type { Conversation } from "@/lib/api";

// BranchLineageBarProps: props governing the lineage banner below `ChatHeader`
// - activeConversation: currently selected Conversation object (or null)
// - parentConversation: parent Conversation object when viewing a child branch (or null)
// - childBranches: array of child Conversation records spawned from the active conversation
// - isMerging: boolean indicating whether a branch distillation & merge operation is in flight
// - onSelectConversation: callback to switch active focus to a parent or child conversation UUID
// - onMergeToParent: callback to distill the active branch and merge takeaways into `parentConversation`
export interface BranchLineageBarProps {
  activeConversation: Conversation | null;
  parentConversation: Conversation | null;
  childBranches: Conversation[];
  isMerging: boolean;
  onSelectConversation: (conversationId: string) => void;
  onMergeToParent: (guidance?: string) => Promise<void> | void;
}

const BranchLineageBar = memo(function BranchLineageBar({
  activeConversation,
  parentConversation,
  childBranches,
  isMerging,
  onSelectConversation,
  onMergeToParent,
}: BranchLineageBarProps) {
  // showGuidanceInput: toggles an optional input field to customize what the merge distillation emphasizes
  const [showGuidanceInput, setShowGuidanceInput] = useState<boolean>(false);
  // guidanceText: optional user instructions passed to `onMergeToParent`
  const [guidanceText, setGuidanceText] = useState<string>("");

  if (!parentConversation && childBranches.length === 0) {
    return null;
  }

  const handleConfirmMerge = async () => {
    const trimmed = guidanceText.trim();
    setShowGuidanceInput(false);
    setGuidanceText("");
    await onMergeToParent(trimmed || undefined);
  };

  return (
    <div className="px-4 md:px-8 py-2 border-b border-border-subtle bg-bg-secondary/60 shrink-0 space-y-1.5">
      {/* Child Branch View: Parent Breadcrumb + Distill & Merge to Parent Controls */}
      {parentConversation && activeConversation && (
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 min-w-0 flex-wrap text-xs">
            <span className="inline-flex items-center gap-1 text-emerald-400 font-mono font-medium">
              <span>🌿</span>
              <span>
                {activeConversation.branch_mode === "fork" ? "Forked from:" : "Tangent from:"}
              </span>
            </span>

            <button
              type="button"
              onClick={() => onSelectConversation(parentConversation.id)}
              title={`Return to parent thread: ${parentConversation.title}`}
              className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-lg bg-bg-tertiary hover:bg-accent-cyan/15 border border-border-subtle hover:border-accent-cyan/40 text-text-primary hover:text-accent-cyan transition-colors font-medium truncate max-w-xs cursor-pointer"
            >
              <span>↩</span>
              <span className="truncate">{parentConversation.title}</span>
            </button>

            {activeConversation.merged_at && (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.65rem] font-mono bg-emerald-500/15 border border-emerald-500/30 text-emerald-300"
                title={`Merged at ${new Date(activeConversation.merged_at).toLocaleString()}`}
              >
                <span>✓</span>
                <span>Merged</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              disabled={isMerging}
              onClick={() => setShowGuidanceInput((prev) => !prev)}
              title="Add optional focus instructions before distilling & merging"
              className="px-2 py-1 rounded-lg text-[0.7rem] font-mono border border-border-subtle bg-bg-tertiary/70 text-text-muted hover:text-text-primary transition-colors cursor-pointer"
            >
              {showGuidanceInput ? "Hide note" : "+ Focus note"}
            </button>

            <button
              type="button"
              disabled={isMerging}
              onClick={handleConfirmMerge}
              title="Synthesize branch takeaways (with proportional depth) and append to parent conversation"
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
                isMerging
                  ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300 animate-pulse"
                  : "bg-emerald-500/15 hover:bg-emerald-500/25 border-emerald-500/40 text-emerald-300 shadow-xs"
              }`}
            >
              <span>{isMerging ? "⏳" : "🌿"}</span>
              <span>
                {isMerging
                  ? "Distilling & Merging…"
                  : activeConversation.merged_at
                    ? "Re-Distill & Merge ↩"
                    : "Distill & Merge to Parent ↩"}
              </span>
            </button>
          </div>
        </div>
      )}

      {/* Optional Merge Guidance Input Bar */}
      {parentConversation && showGuidanceInput && !isMerging && (
        <div className="flex items-center gap-2 pt-1">
          <input
            type="text"
            value={guidanceText}
            onChange={(e) => setGuidanceText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleConfirmMerge();
              } else if (e.key === "Escape") {
                setShowGuidanceInput(false);
              }
            }}
            placeholder="Optional merge guidance (e.g., 'Include full SQL schema and code snippets, ~1 page')…"
            className="flex-1 min-w-0 bg-bg-primary/90 border border-emerald-500/40 rounded-lg px-3 py-1 text-xs text-text-primary focus:outline-none focus:border-emerald-400"
          />
          <button
            type="button"
            onClick={handleConfirmMerge}
            className="px-2.5 py-1 rounded-lg text-xs font-medium bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 transition-colors cursor-pointer"
          >
            Merge Now ↩
          </button>
        </div>
      )}

      {/* Child Branches Strip (shown when active conversation has spawned branches) */}
      {childBranches.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap text-xs">
          <span className="text-[0.68rem] font-mono text-text-muted">
            🌿 Branches ({childBranches.length}):
          </span>
          {childBranches.map((branch) => (
            <button
              key={branch.id}
              type="button"
              onClick={() => onSelectConversation(branch.id)}
              title={`Open child branch: ${branch.title}`}
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.68rem] font-mono border transition-colors cursor-pointer ${
                branch.merged_at
                  ? "bg-emerald-500/10 hover:bg-emerald-500/20 border-emerald-500/30 text-emerald-300"
                  : "bg-teal-500/15 hover:bg-teal-500/25 border-teal-500/35 text-teal-300"
              }`}
            >
              <span className="max-w-[180px] truncate">{branch.title.replace(/^🌿\s*/, "")}</span>
              {branch.merged_at && <span title="Merged">✓</span>}
              <span>→</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
});

export default BranchLineageBar;
