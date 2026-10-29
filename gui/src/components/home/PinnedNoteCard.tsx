"use client";

/**
 * PinnedNoteCard.tsx — Modular card component for individual pinned notes in Grid view.
 *
 * Encapsulates the visual presentation of a pinned note: header title and folder tags,
 * re-ordering arrows, copy-to-clipboard button, deep-link to Vault explorer, expand/collapse
 * height controls, unpin action, loading/error states, and rendered markdown content with word metrics.
 */

import React from "react";
import Link from "next/link";
import MarkdownMessage from "@/components/MarkdownMessage";
import type { PinnedNoteCardProps } from "./types";

/**
 * PinnedNoteCard renders an individual card representing one pinned Vault note.
 *
 * @param props.path - The Vault-relative path of this note (e.g., "Tasks.md").
 * @param props.data - In-memory note data (title, folder, markdown content, loading/error states).
 * @param props.index - Zero-based index within the pinned notes array.
 * @param props.totalCards - Total count of pinned notes, used to bound reordering actions.
 * @param props.isExpanded - Whether this card's height is expanded to 750px or compact 384px (max-h-96).
 * @param props.isCopied - Temporary feedback state when the card's markdown was copied.
 * @param props.onMovePrev - Optional handler to shift this card left/up.
 * @param props.onMoveNext - Optional handler to shift this card right/down.
 * @param props.onCopy - Callback to copy note content to clipboard.
 * @param props.onToggleExpand - Callback to toggle between compact and expanded heights.
 * @param props.onUnpin - Callback to remove this note from pinned dashboard.
 */
export default function PinnedNoteCard({
  path,
  data,
  index,
  totalCards,
  isExpanded,
  isCopied,
  onMovePrev,
  onMoveNext,
  onCopy,
  onToggleExpand,
  onUnpin,
}: PinnedNoteCardProps) {
  // Derive clean title from data or filename fallback
  const displayTitle = data?.title || path.split("/").pop()?.replace(/\.md$/, "");
  const displayFolder = data?.folder || "Vault Root";
  const wordCount = data?.content ? data.content.split(/\s+/).filter(Boolean).length : 0;

  return (
    <div className="glass-card flex flex-col border border-border-subtle bg-bg-card hover:border-border-accent/50 transition-all rounded-2xl overflow-hidden shadow-lg group">
      {/* ── Card Header ────────────────────────────────────────────────────── */}
      <div className="p-4 border-b border-border-subtle/60 bg-bg-secondary/30 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="text-xs">📌</span>
            <h2
              className="text-sm font-semibold text-text-primary truncate"
              title={displayTitle}
            >
              {displayTitle}
            </h2>
          </div>
          <div className="flex items-center gap-2 text-[0.7rem] text-text-muted">
            <span className="px-1.5 py-0.5 rounded bg-bg-surface font-mono text-[0.65rem] truncate max-w-[220px]">
              {displayFolder}
            </span>
          </div>
        </div>

        {/* Card Action Controls */}
        <div className="flex items-center gap-1 shrink-0">
          {/* Move Left / Prev Arrow */}
          {index > 0 && onMovePrev && (
            <button
              type="button"
              onClick={onMovePrev}
              className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors"
              title="Move pin left"
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          )}

          {/* Move Right / Next Arrow */}
          {index < totalCards - 1 && onMoveNext && (
            <button
              type="button"
              onClick={onMoveNext}
              className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors"
              title="Move pin right"
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </button>
          )}

          {/* Copy Raw Markdown */}
          <button
            type="button"
            onClick={onCopy}
            className="p-1 rounded text-text-muted hover:text-accent-cyan hover:bg-bg-surface transition-colors"
            title={isCopied ? "Copied to clipboard!" : "Copy markdown"}
          >
            {isCopied ? (
              <span className="text-[0.65rem] font-medium text-accent-emerald">✓</span>
            ) : (
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <rect x="9" y="9" width="13" height="13" rx="2" />
                <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
              </svg>
            )}
          </button>

          {/* Open in Brain Explorer */}
          <Link
            href={`/vault?note=${encodeURIComponent(path)}`}
            className="p-1 rounded text-text-muted hover:text-accent-violet hover:bg-bg-surface transition-colors"
            title="Open in Brain Explorer"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </Link>

          {/* Toggle Expand / Full Height */}
          <button
            type="button"
            onClick={onToggleExpand}
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors"
            title={isExpanded ? "Collapse height" : "Expand full height"}
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              {isExpanded ? (
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 14h6m0 0v6m0-6L3 21m17-7h-6m0 0v6m0-6l7 7M4 10h6m0 0V4m0 6L3 3m17 7h-6m0 0V4m0 6l7-7" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 3h6m0 0v6m0-6L14 10M9 21H3m0 0v-6m0 6l7-7M3 9V3m0 0h6m-6 0l7 7M21 15v6m0 0h-6m6 0l-7-7" />
              )}
            </svg>
          </button>

          {/* Unpin Button */}
          <button
            type="button"
            onClick={onUnpin}
            className="p-1 rounded text-text-muted hover:text-accent-rose hover:bg-accent-rose/10 transition-colors ml-0.5"
            title="Unpin note from home page"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* ── Card Body (Scrollable Rendered Markdown) ───────────────────────── */}
      <div
        className={`p-4 overflow-y-auto text-xs leading-relaxed transition-all ${
          isExpanded ? "max-h-[750px]" : "max-h-96"
        }`}
      >
        {data?.loading ? (
          <div className="py-12 flex flex-col items-center justify-center text-text-muted gap-2">
            <span className="w-4 h-4 border-2 border-accent-cyan/30 border-t-accent-cyan rounded-full animate-spin"></span>
            <span className="text-[0.7rem]">Reading note from Vault...</span>
          </div>
        ) : data?.error ? (
          <div className="p-3 rounded-xl bg-accent-rose/10 border border-accent-rose/20 text-accent-rose text-xs space-y-1">
            <p className="font-semibold">Failed to load note</p>
            <p className="text-[0.7rem] text-text-muted">{data.error}</p>
            <button
              type="button"
              onClick={onUnpin}
              className="text-[0.7rem] text-accent-rose underline hover:opacity-80 pt-1"
            >
              Unpin this missing note
            </button>
          </div>
        ) : (
          <div className="prose prose-invert max-w-none">
            <MarkdownMessage content={data?.content || "_Note is empty._"} />
          </div>
        )}
      </div>

      {/* ── Card Footer: Path & Word Metrics ──────────────────────────────── */}
      <div className="px-4 py-2 border-t border-border-subtle/40 bg-bg-secondary/20 flex items-center justify-between text-[0.65rem] text-text-muted mt-auto">
        <span className="font-mono truncate max-w-[200px]" title={path}>
          {path}
        </span>
        <span>
          {data?.content ? `${wordCount} words` : ""}
        </span>
      </div>
    </div>
  );
}
