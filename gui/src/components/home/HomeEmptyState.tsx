"use client";

/**
 * HomeEmptyState.tsx — Educational empty state placeholder for the Nexus Home workspace.
 *
 * Rendered when the user has not pinned any notes yet or has unpinned all active notes.
 * Provides intuitive onboarding with suggested quick-pins and a direct trigger to browse
 * the entire Vault.
 */

import React from "react";
import type { HomeEmptyStateProps } from "./types";

/**
 * HomeEmptyState renders an engaging fallback container when `pinnedPaths.length === 0`.
 *
 * @param props.suggestedNotes - Array of recommended default note paths (e.g. Tasks.md, Goals.md).
 * @param props.onPinSuggested - Callback triggered when clicking a suggested quick-pin chip.
 * @param props.onOpenPinModal - Callback triggered when clicking "Browse All Vault Notes".
 */
export default function HomeEmptyState({
  suggestedNotes,
  onPinSuggested,
  onOpenPinModal,
}: HomeEmptyStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-12 text-center animate-fade-in-up">
      <div className="w-16 h-16 rounded-2xl bg-bg-surface border border-border-accent/40 flex items-center justify-center text-3xl mb-4 shadow-[0_0_30px_rgba(56,189,248,0.12)]">
        📌
      </div>
      <h2 className="text-xl font-bold text-text-primary mb-2">No notes pinned yet</h2>
      <p className="text-text-secondary text-xs max-w-md mb-6 leading-relaxed">
        Your home page is a focused personal workspace. Pin your daily schedule, active war rooms, project plans, or core goals so they are immediately at your fingertips.
      </p>

      {/* Suggested Quick Pin Chips */}
      {suggestedNotes.length > 0 && (
        <div className="flex flex-wrap items-center justify-center gap-2 mb-6 max-w-lg">
          <span className="text-xs text-text-muted mr-1">Suggested quick pins:</span>
          {suggestedNotes.map((path) => (
            <button
              key={path}
              type="button"
              onClick={() => onPinSuggested(path)}
              className="px-2.5 py-1 rounded-lg border border-border-subtle bg-bg-surface hover:border-accent-cyan/40 hover:text-accent-cyan text-xs font-mono text-text-secondary transition-all flex items-center gap-1.5"
            >
              <span>+</span>
              <span>{path.split("/").pop()?.replace(/\.md$/, "")}</span>
            </button>
          ))}
        </div>
      )}

      {/* Primary Action Button */}
      <button
        type="button"
        onClick={onOpenPinModal}
        className="px-5 py-2.5 rounded-xl bg-accent-cyan text-black font-semibold text-xs hover:bg-accent-cyan/90 transition-all shadow-[0_0_25px_rgba(56,189,248,0.3)] flex items-center gap-2"
      >
        <span>Browse All Vault Notes</span>
        <span className="text-sm">→</span>
      </button>
    </div>
  );
}

