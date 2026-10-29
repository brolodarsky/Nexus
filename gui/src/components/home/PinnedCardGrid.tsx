"use client";

/**
 * PinnedCardGrid.tsx — Responsive grid layout rendering pinned note cards.
 *
 * Arranges pinned notes in a dynamic 1-to-3 column grid (mobile: 1 col, lg: 2 cols, 2xl: 3 cols).
 * Delegates rendering and interaction handling for each note to `PinnedNoteCard`.
 */

import React from "react";
import PinnedNoteCard from "./PinnedNoteCard";
import type { PinnedCardGridProps } from "./types";

/**
 * PinnedCardGrid orchestrates the multi-column card layout on the Home page.
 *
 * @param props.pinnedPaths - Ordered array of Vault-relative paths currently pinned.
 * @param props.noteDataMap - Map of note paths to loaded metadata and content.
 * @param props.expandedCards - Dictionary tracking which cards are expanded to full height.
 * @param props.copiedPath - Path of the note recently copied to clipboard (for checkmark feedback).
 * @param props.onMovePin - Callback to shift card order left or right.
 * @param props.onCopyNote - Callback to copy markdown text to clipboard.
 * @param props.onToggleCardExpand - Callback to toggle expansion state of a specific card.
 * @param props.onUnpinNote - Callback to unpin a note from the dashboard.
 */
export default function PinnedCardGrid({
  pinnedPaths,
  noteDataMap,
  expandedCards,
  copiedPath,
  onMovePin,
  onCopyNote,
  onToggleCardExpand,
  onUnpinNote,
}: PinnedCardGridProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-5">
      {pinnedPaths.map((path, index) => {
        const data = noteDataMap[path];
        const isExpanded = expandedCards[path] ?? false;
        const isCopied = copiedPath === path;

        return (
          <PinnedNoteCard
            key={path}
            path={path}
            data={data}
            index={index}
            totalCards={pinnedPaths.length}
            isExpanded={isExpanded}
            isCopied={isCopied}
            onMovePrev={() => onMovePin(index, "prev")}
            onMoveNext={() => onMovePin(index, "next")}
            onCopy={() => onCopyNote(path, data?.content || "")}
            onToggleExpand={() => onToggleCardExpand(path)}
            onUnpin={(e) => onUnpinNote(path, e)}
          />
        );
      })}
    </div>
  );
}

