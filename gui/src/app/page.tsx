"use client";

/**
 * page.tsx (`/`) — Route orchestrator for the Nexus Home workspace.
 *
 * Coordinates persistent pinned note selections, layout view mode preferences
 * (multi-column card Grid vs IDE-style split Reader), asynchronous Vault markdown
 * content retrieval, and note reordering. Delegates all UI presentation to modular
 * subcomponents in `@/components/home`.
 */

import { useEffect, useState, useCallback } from "react";
import {
  getAllVaultNotes,
  getNote,
  type VaultNoteSummary,
  type NoteContentResponse,
} from "@/lib/api";
import {
  HomeHeader,
  HomeEmptyState,
  PinnedCardGrid,
  PinnedNotesReader,
  PinNoteModal,
  PINNED_STORAGE_KEY,
  VIEW_MODE_KEY,
  DEFAULT_PINNED_FALLBACK,
  type PinnedNoteData,
  type ViewMode,
} from "@/components/home";

export default function HomePage() {
  // ── Core State ────────────────────────────────────────────────────────────

  // pinnedPaths: string array of Vault-relative paths currently pinned to the Home page
  const [pinnedPaths, setPinnedPaths] = useState<string[]>([]);
  // noteDataMap: Key-value map indexing path -> PinnedNoteData for instant O(1) content lookups
  const [noteDataMap, setNoteDataMap] = useState<Record<string, PinnedNoteData>>({});
  // allNotes: Flat list of all Vault notes loaded from /api/vault/notes for the Pin Modal picker
  const [allNotes, setAllNotes] = useState<VaultNoteSummary[]>([]);
  const [isLoadingAllNotes, setIsLoadingAllNotes] = useState(false);

  // Layout View Mode: "grid" renders multi-column cards; "reader" renders an IDE-style split workspace
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  // activeReaderPath: in "reader" mode, specifies which pinned note is rendered in the main reader pane
  const [activeReaderPath, setActiveReaderPath] = useState<string | null>(null);

  // isPinModalOpen: controls visibility of the searchable "+ Pin Note" modal dialog
  const [isPinModalOpen, setIsPinModalOpen] = useState(false);

  // expandedCards: dictionary tracking which cards in Grid mode are expanded beyond default max-height
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});
  // copiedPath: path of note whose markdown was just copied to clipboard (shows 2-second checkmark feedback)
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  // isRefreshing: visual indicator when manually refreshing note contents from disk
  const [isRefreshing, setIsRefreshing] = useState(false);
  // isHydrated: tracks whether localStorage has been safely loaded into state on mount
  const [isHydrated, setIsHydrated] = useState(false);

  // ── Hydration & LocalStorage Persistence ──────────────────────────────────

  // Read saved pinned notes and view mode preference from localStorage on mount.
  // Running inside queueMicrotask prevents React 19 cascading render warnings.
  useEffect(() => {
    queueMicrotask(() => {
      try {
        const savedPinned = localStorage.getItem(PINNED_STORAGE_KEY);
        if (savedPinned) {
          const parsed = JSON.parse(savedPinned);
          if (Array.isArray(parsed) && parsed.length > 0) {
            setPinnedPaths(parsed);
            setActiveReaderPath(parsed[0]);
          } else {
            setPinnedPaths(DEFAULT_PINNED_FALLBACK);
            setActiveReaderPath(DEFAULT_PINNED_FALLBACK[0]);
          }
        } else {
          setPinnedPaths(DEFAULT_PINNED_FALLBACK);
          setActiveReaderPath(DEFAULT_PINNED_FALLBACK[0]);
        }

        const savedMode = localStorage.getItem(VIEW_MODE_KEY);
        if (savedMode === "grid" || savedMode === "reader") {
          setViewMode(savedMode);
        }
      } catch {
        // Gracefully fall back to defaults if localStorage is restricted or throws
        setPinnedPaths(DEFAULT_PINNED_FALLBACK);
        setActiveReaderPath(DEFAULT_PINNED_FALLBACK[0]);
      } finally {
        setIsHydrated(true);
      }
    });
  }, []);

  // Save pinnedPaths whenever they change after initial hydration
  const persistPinnedPaths = useCallback((paths: string[]) => {
    setPinnedPaths(paths);
    try {
      localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(paths));
    } catch {
      // Ignore quota/privacy errors in restricted browser contexts
    }
  }, []);

  // Save layout viewMode preference whenever toggled
  const handleToggleViewMode = useCallback((mode: ViewMode) => {
    setViewMode(mode);
    try {
      localStorage.setItem(VIEW_MODE_KEY, mode);
    } catch {
      // Ignore quota/privacy errors in restricted browser contexts
    }
  }, []);

  // ── Fetch Note Content ────────────────────────────────────────────────────

  // loadNoteContent: Fetches note content from /api/vault/note?path=... and populates noteDataMap
  const loadNoteContent = useCallback(async (path: string) => {
    // Determine default title and folder from path segments
    const parts = path.split("/");
    const filename = parts[parts.length - 1];
    const cleanTitle = filename.replace(/\.md$/, "");
    const folder = parts.length > 1 ? parts.slice(0, -1).join("/") : "Vault Root";

    setNoteDataMap((prev) => ({
      ...prev,
      [path]: {
        path,
        title: cleanTitle,
        folder,
        content: prev[path]?.content || "",
        loading: true,
        error: null,
      },
    }));

    try {
      const res: NoteContentResponse = await getNote(path);
      setNoteDataMap((prev) => ({
        ...prev,
        [path]: {
          path,
          title: cleanTitle,
          folder,
          content: res.content,
          loading: false,
          error: null,
        },
      }));
    } catch (err) {
      setNoteDataMap((prev) => ({
        ...prev,
        [path]: {
          path,
          title: cleanTitle,
          folder,
          content: "",
          loading: false,
          error: err instanceof Error ? err.message : "Failed to load note content",
        },
      }));
    }
  }, []);

  // Synchronize note contents whenever pinnedPaths changes
  useEffect(() => {
    if (!isHydrated) return;

    // Load any notes that haven't been fetched yet
    pinnedPaths.forEach((path) => {
      if (!noteDataMap[path] || noteDataMap[path].loading === undefined) {
        loadNoteContent(path);
      }
    });

    // Ensure activeReaderPath remains valid
    if (pinnedPaths.length > 0 && (!activeReaderPath || !pinnedPaths.includes(activeReaderPath))) {
      setActiveReaderPath(pinnedPaths[0]);
    }
  }, [pinnedPaths, isHydrated, loadNoteContent, noteDataMap, activeReaderPath]);

  // handleRefreshAll: Re-fetches the latest disk content for all pinned notes
  const handleRefreshAll = async () => {
    setIsRefreshing(true);
    await Promise.allSettled(pinnedPaths.map((path) => loadNoteContent(path)));
    setIsRefreshing(false);
  };

  // ── Pin / Unpin / Reorder Handlers ────────────────────────────────────────

  // togglePin: Pins a note if not already pinned; unpins if already present
  const togglePin = (path: string) => {
    if (pinnedPaths.includes(path)) {
      const next = pinnedPaths.filter((p) => p !== path);
      persistPinnedPaths(next);
      if (activeReaderPath === path) {
        setActiveReaderPath(next.length > 0 ? next[0] : null);
      }
    } else {
      const next = [...pinnedPaths, path];
      persistPinnedPaths(next);
      loadNoteContent(path);
      setActiveReaderPath(path);
    }
  };

  // unpinNote: Explicit unpin action called from card headers and tabs
  const unpinNote = (path: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const next = pinnedPaths.filter((p) => p !== path);
    persistPinnedPaths(next);
    if (activeReaderPath === path) {
      setActiveReaderPath(next.length > 0 ? next[0] : null);
    }
  };

  // movePin: Re-orders notes left/right in Grid view
  const movePin = (index: number, direction: "prev" | "next") => {
    const targetIndex = direction === "prev" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= pinnedPaths.length) return;

    const updated = [...pinnedPaths];
    const [moved] = updated.splice(index, 1);
    updated.splice(targetIndex, 0, moved);
    persistPinnedPaths(updated);
  };

  // handleCopy: Copies raw markdown to clipboard with temporary feedback
  const handleCopy = (path: string, content: string) => {
    navigator.clipboard.writeText(content);
    setCopiedPath(path);
    setTimeout(() => setCopiedPath(null), 2000);
  };

  // toggleCardExpand: Toggles expansion of a specific card in Grid view
  const toggleCardExpand = (path: string) => {
    setExpandedCards((prev) => ({
      ...prev,
      [path]: !prev[path],
    }));
  };

  // ── Pin Modal: Note Index Fetching ────────────────────────────────────────

  // Open modal and fetch the flat list of notes if not already loaded
  const handleOpenPinModal = async () => {
    setIsPinModalOpen(true);
    if (allNotes.length === 0) {
      setIsLoadingAllNotes(true);
      try {
        const notes = await getAllVaultNotes();
        setAllNotes(notes);
      } catch (err) {
        console.error("Failed to load vault notes:", err);
      } finally {
        setIsLoadingAllNotes(false);
      }
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="px-6 py-6 max-w-7xl mx-auto flex flex-col min-h-[calc(100vh-3rem)]">
      {/* ── Page Header & Workspace Toolbar ──────────────────────────────── */}
      <HomeHeader
        pinnedCount={pinnedPaths.length}
        viewMode={viewMode}
        onToggleViewMode={handleToggleViewMode}
        onRefreshAll={handleRefreshAll}
        isRefreshing={isRefreshing}
        onOpenPinModal={handleOpenPinModal}
      />

      {/* ── Empty State (When no notes are pinned) ────────────────────────── */}
      {isHydrated && pinnedPaths.length === 0 ? (
        <HomeEmptyState
          suggestedNotes={DEFAULT_PINNED_FALLBACK}
          onPinSuggested={togglePin}
          onOpenPinModal={handleOpenPinModal}
        />
      ) : null}

      {/* ── VIEW MODE 1: Cards Grid ────────────────────────────────────────── */}
      {isHydrated && pinnedPaths.length > 0 && viewMode === "grid" && (
        <PinnedCardGrid
          pinnedPaths={pinnedPaths}
          noteDataMap={noteDataMap}
          expandedCards={expandedCards}
          copiedPath={copiedPath}
          onMovePin={movePin}
          onCopyNote={handleCopy}
          onToggleCardExpand={toggleCardExpand}
          onUnpinNote={unpinNote}
        />
      )}

      {/* ── VIEW MODE 2: Workspace Split Reader ────────────────────────────── */}
      {isHydrated && pinnedPaths.length > 0 && viewMode === "reader" && (
        <PinnedNotesReader
          pinnedPaths={pinnedPaths}
          noteDataMap={noteDataMap}
          activeReaderPath={activeReaderPath}
          copiedPath={copiedPath}
          onSelectReaderPath={setActiveReaderPath}
          onUnpinNote={unpinNote}
          onCopyNote={handleCopy}
          onOpenPinModal={handleOpenPinModal}
        />
      )}

      {/* ── "+ Pin Note" Modal Dialog ─────────────────────────────────────── */}
      <PinNoteModal
        isOpen={isPinModalOpen}
        onClose={() => setIsPinModalOpen(false)}
        allNotes={allNotes}
        isLoadingAllNotes={isLoadingAllNotes}
        pinnedPaths={pinnedPaths}
        onTogglePin={togglePin}
      />
    </div>
  );
}
