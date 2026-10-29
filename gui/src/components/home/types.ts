/**
 * types.ts — Educational type definitions and shared interfaces for the Nexus Home workspace.
 *
 * This module defines the core data contracts for pinned note state, storage keys,
 * layout display modes, and component props used across the modularized Home page.
 */

import type { VaultNoteSummary } from "@/lib/api";

// ── Pinned Note State Data Contract ─────────────────────────────────────────

/**
 * PinnedNoteData models the in-memory representation of a pinned markdown note.
 *
 * Parameters & Attributes breakdown:
 * - `path`: Vault-relative file path (e.g., "Tasks.md", "1. Core/Goals.md") serving as the unique key.
 * - `title`: Clean human-readable display title with any ".md" extension stripped out.
 * - `folder`: Directory path relative to the Vault root, or "Vault Root" for top-level files.
 * - `content`: Raw UTF-8 Markdown text retrieved asynchronously from the FastAPI `/api/vault/note` endpoint.
 * - `loading`: Boolean flag indicating whether an HTTP fetch operation is currently in-flight.
 * - `error`: Human-readable error string if disk reading failed (e.g., file deleted or moved), else null.
 * - `mtime`: Optional POSIX timestamp indicating the note file's last modified time.
 * - `size`: Optional file size in bytes for disk usage statistics.
 */
export interface PinnedNoteData {
  path: string;
  title: string;
  folder: string;
  content: string;
  loading: boolean;
  error: string | null;
  mtime?: number;
  size?: number;
}

// ── View Mode Types ─────────────────────────────────────────────────────────

/**
 * ViewMode defines the primary layout paradigm for rendering pinned notes:
 * - `"grid"`: Multi-column responsive cards layout ideal for scanning multiple dashboards.
 * - `"reader"`: IDE-style split workspace with a left navigation rail and a dedicated document reader.
 */
export type ViewMode = "grid" | "reader";

// ── Storage Keys & Default Fallbacks ────────────────────────────────────────

/**
 * PINNED_STORAGE_KEY: Browser localStorage key for storing pinned note paths as a JSON-serialized string array.
 */
export const PINNED_STORAGE_KEY = "nexus_pinned_notes";

/**
 * VIEW_MODE_KEY: Browser localStorage key for persisting the user's preferred layout ("grid" vs "reader").
 */
export const VIEW_MODE_KEY = "nexus_home_view_mode";

/**
 * DEFAULT_PINNED_FALLBACK: Sensible starting notes pinned automatically if the user has no saved preferences.
 */
export const DEFAULT_PINNED_FALLBACK: string[] = [
  "Tasks.md",
  "1. Core/1.1. Philosophy & Personal North Star/Goals.md",
];

// ── Modular Component Prop Interfaces ───────────────────────────────────────

/**
 * HomeHeaderProps describes the top-level toolbar actions and badge status indicators.
 *
 * Parameters:
 * - `pinnedCount`: Total number of notes currently pinned by the user.
 * - `viewMode`: Active display layout ("grid" | "reader").
 * - `onToggleViewMode`: Callback invoked when switching between grid and split reader modes.
 * - `onRefreshAll`: Callback invoked when clicking the refresh button to re-fetch contents from disk.
 * - `isRefreshing`: Boolean state triggering the spinning refresh animation during active network requests.
 * - `onOpenPinModal`: Callback to open the "+ Pin Note" modal selector.
 */
export interface HomeHeaderProps {
  pinnedCount: number;
  viewMode: ViewMode;
  onToggleViewMode: (mode: ViewMode) => void;
  onRefreshAll: () => void;
  isRefreshing: boolean;
  onOpenPinModal: () => void;
}

/**
 * HomeEmptyStateProps describes the empty state placeholder shown when no notes are pinned.
 *
 * Parameters:
 * - `suggestedNotes`: Array of vault-relative note paths suggested for quick pinning.
 * - `onPinSuggested`: Callback invoked when clicking one of the quick suggestion pills.
 * - `onOpenPinModal`: Callback invoked when clicking the "Browse All Vault Notes" call to action.
 */
export interface HomeEmptyStateProps {
  suggestedNotes: string[];
  onPinSuggested: (path: string) => void;
  onOpenPinModal: () => void;
}

/**
 * PinnedNoteCardProps describes an individual card in the Grid view.
 *
 * Parameters:
 * - `path`: Vault-relative path of the note rendered by this card.
 * - `data`: Cached PinnedNoteData object containing title, folder, content, and loading state.
 * - `index`: Position index of this card within the pinned array (used for ordering arrows).
 * - `totalCards`: Total number of cards pinned (used to disable next-arrow on last card).
 * - `isExpanded`: Boolean indicating whether the card body is expanded beyond default height.
 * - `isCopied`: Boolean indicating whether the markdown content was copied within the last 2 seconds.
 * - `onMovePrev`: Optional callback to shift this card one position to the left.
 * - `onMoveNext`: Optional callback to shift this card one position to the right.
 * - `onCopy`: Callback to copy the raw markdown text to clipboard.
 * - `onToggleExpand`: Callback to toggle the card height between compact and expanded.
 * - `onUnpin`: Callback to unpin and remove this card from the home dashboard.
 */
export interface PinnedNoteCardProps {
  path: string;
  data?: PinnedNoteData;
  index: number;
  totalCards: number;
  isExpanded: boolean;
  isCopied: boolean;
  onMovePrev?: () => void;
  onMoveNext?: () => void;
  onCopy: () => void;
  onToggleExpand: () => void;
  onUnpin: (e?: React.MouseEvent) => void;
}

/**
 * PinnedCardGridProps describes the grid container rendering all pinned cards.
 */
export interface PinnedCardGridProps {
  pinnedPaths: string[];
  noteDataMap: Record<string, PinnedNoteData>;
  expandedCards: Record<string, boolean>;
  copiedPath: string | null;
  onMovePin: (index: number, direction: "prev" | "next") => void;
  onCopyNote: (path: string, content: string) => void;
  onToggleCardExpand: (path: string) => void;
  onUnpinNote: (path: string, e?: React.MouseEvent) => void;
}

/**
 * PinnedNotesReaderProps describes the workspace split reader view.
 */
export interface PinnedNotesReaderProps {
  pinnedPaths: string[];
  noteDataMap: Record<string, PinnedNoteData>;
  activeReaderPath: string | null;
  copiedPath: string | null;
  onSelectReaderPath: (path: string) => void;
  onUnpinNote: (path: string, e?: React.MouseEvent) => void;
  onCopyNote: (path: string, content: string) => void;
  onOpenPinModal: () => void;
}

/**
 * PinNoteModalProps describes the searchable modal dialog used to browse and pin Vault notes.
 */
export interface PinNoteModalProps {
  isOpen: boolean;
  onClose: () => void;
  allNotes: VaultNoteSummary[];
  isLoadingAllNotes: boolean;
  pinnedPaths: string[];
  onTogglePin: (path: string) => void;
}
