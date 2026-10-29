"use client";

/**
 * HomeHeader.tsx — Top-level header and workspace toolbar for the Nexus Home dashboard.
 *
 * Renders the page title, active pinned count badge, refresh disk content trigger,
 * layout segmented switcher (Grid vs Split Reader), and the primary "+ Pin Note" button.
 */

import React from "react";
import type { HomeHeaderProps } from "./types";

/**
 * HomeHeader renders the top toolbar navigation of the Nexus Home workspace.
 *
 * @param props.pinnedCount - Number of notes currently pinned in state.
 * @param props.viewMode - Current layout view ("grid" or "reader").
 * @param props.onToggleViewMode - Function invoked to change the layout mode.
 * @param props.onRefreshAll - Function invoked to re-fetch all pinned note markdown from disk.
 * @param props.isRefreshing - Boolean indicating if a refresh disk fetch is currently pending.
 * @param props.onOpenPinModal - Function invoked to open the searchable note picker modal.
 */
export default function HomeHeader({
  pinnedCount,
  viewMode,
  onToggleViewMode,
  onRefreshAll,
  isRefreshing,
  onOpenPinModal,
}: HomeHeaderProps) {
  return (
    <header className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border-subtle/80">
      <div>
        <div className="flex items-center gap-2.5">
          <span className="text-xl">📌</span>
          <h1 className="text-2xl font-bold tracking-tight text-text-primary">
            <span className="gradient-text">Pinned Notes</span>
          </h1>
          <span className="px-2 py-0.5 rounded-full text-[0.7rem] font-medium bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20">
            {pinnedCount} pinned
          </span>
        </div>
        <p className="text-text-secondary text-xs mt-1">
          Keep your active war rooms, daily schedule, and core projects immediately accessible.
        </p>
      </div>

      {/* Toolbar Actions */}
      <div className="flex items-center gap-2.5 self-start sm:self-auto">
        {/* Refresh Disk Content Button */}
        <button
          type="button"
          onClick={onRefreshAll}
          disabled={isRefreshing}
          className="p-2 rounded-xl border border-border-subtle bg-bg-surface hover:bg-bg-card-hover text-text-secondary hover:text-text-primary transition-all text-xs flex items-center gap-1.5"
          title="Refresh note contents from disk"
        >
          <svg
            className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-accent-cyan" : ""}`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          <span className="hidden md:inline">Refresh</span>
        </button>

        {/* View Mode Segmented Switcher (Grid vs Split Reader) */}
        <div className="flex items-center p-0.5 rounded-xl border border-border-subtle bg-bg-secondary/60">
          <button
            type="button"
            onClick={() => onToggleViewMode("grid")}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
              viewMode === "grid"
                ? "bg-accent-cyan/20 text-accent-cyan shadow-sm"
                : "text-text-muted hover:text-text-primary"
            }`}
            title="Cards Grid View"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <rect x="3" y="3" width="7" height="7" rx="1.5" />
              <rect x="14" y="3" width="7" height="7" rx="1.5" />
              <rect x="14" y="14" width="7" height="7" rx="1.5" />
              <rect x="3" y="14" width="7" height="7" rx="1.5" />
            </svg>
            <span>Grid</span>
          </button>
          <button
            type="button"
            onClick={() => onToggleViewMode("reader")}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
              viewMode === "reader"
                ? "bg-accent-cyan/20 text-accent-cyan shadow-sm"
                : "text-text-muted hover:text-text-primary"
            }`}
            title="Workspace Split Reader View"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <line x1="9" y1="4" x2="9" y2="20" />
            </svg>
            <span>Reader</span>
          </button>
        </div>

        {/* "+ Pin Note" Modal Trigger Button */}
        <button
          type="button"
          onClick={onOpenPinModal}
          className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-accent-cyan/80 to-accent-violet/80 text-black font-semibold text-xs hover:opacity-95 shadow-[0_0_20px_rgba(56,189,248,0.25)] flex items-center gap-1.5 transition-all active:scale-[0.98]"
        >
          <span className="text-sm font-bold leading-none">+</span>
          <span>Pin Note</span>
        </button>
      </div>
    </header>
  );
}
