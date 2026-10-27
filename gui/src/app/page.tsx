"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import MarkdownMessage from "@/components/MarkdownMessage";
import {
  getAllVaultNotes,
  getNote,
  type VaultNoteSummary,
  type NoteContentResponse,
} from "@/lib/api";

// ── Educational Type Definitions ──────────────────────────────────────────

// PinnedNoteData: models loaded note content, parsed metadata, and async fetching states for pinned cards
// - path: Vault-relative file path (e.g. "Tasks.md", "1. Core/Goals.md")
// - title: Clean display title without the ".md" extension
// - folder: Directory path relative to Vault root or "Vault Root"
// - content: Raw UTF-8 Markdown text retrieved from the FastAPI /api/vault/note endpoint
// - loading: True while HTTP request is in-flight
// - error: Human-readable error message if the file was deleted, moved, or failed to load
interface PinnedNoteData {
  path: string;
  title: string;
  folder: string;
  content: string;
  loading: boolean;
  error: string | null;
  mtime?: number;
  size?: number;
}

// STORAGE_KEY: localStorage key for storing pinned note paths as a JSON-serialized string array
const PINNED_STORAGE_KEY = "nexus_pinned_notes";
// VIEW_MODE_KEY: localStorage key for persisting layout preference ("grid" vs "reader")
const VIEW_MODE_KEY = "nexus_home_view_mode";

// DEFAULT_PINNED_FALLBACK: Sensible starting notes if user hasn't pinned anything yet
const DEFAULT_PINNED_FALLBACK: string[] = [
  "Tasks.md",
  "1. Core/1.1. Philosophy & Personal North Star/Goals.md",
];

export default function HomePage() {
  // ── Core State ────────────────────────────────────────────────────────────

  // pinnedPaths: string array of Vault-relative paths currently pinned to the Home page
  const [pinnedPaths, setPinnedPaths] = useState<string[]>([]);
  // noteDataMap: Key-value map indexing path -> PinnedNoteData for instant O(1) content lookups
  const [noteDataMap, setNoteDataMap] = useState<Record<string, PinnedNoteData>>({});
  // allNotes: Full list of all 300+ Vault notes loaded from /api/vault/notes for the Pin Modal picker
  const [allNotes, setAllNotes] = useState<VaultNoteSummary[]>([]);
  const [isLoadingAllNotes, setIsLoadingAllNotes] = useState(false);

  // Layout View Mode: "grid" renders multi-column cards; "reader" renders an IDE-style split workspace
  const [viewMode, setViewMode] = useState<"grid" | "reader">("grid");
  // activeReaderPath: in "reader" mode, specifies which pinned note is rendered in the main reader pane
  const [activeReaderPath, setActiveReaderPath] = useState<string | null>(null);

  // isPinModalOpen: controls visibility of the searchable "+ Pin Note" modal dialog
  const [isPinModalOpen, setIsPinModalOpen] = useState(false);
  // searchQuery: active filter string inside the Pin Modal
  const [searchQuery, setSearchQuery] = useState("");
  // selectedFolderFilter: category chip filter ("all" or folder prefix like "1. Core")
  const [selectedFolderFilter, setSelectedFolderFilter] = useState("all");

  // expandedCards: dictionary tracking which cards in Grid mode are expanded beyond default max-height
  const [expandedCards, setExpandedCards] = useState<Record<string, boolean>>({});
  // copiedPath: path of note whose markdown was just copied to clipboard (shows 2-second checkmark feedback)
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  // isRefreshing: visual indicator when manually refreshing note contents from disk
  const [isRefreshing, setIsRefreshing] = useState(false);
  // isHydrated: tracks whether localStorage has been safely loaded into state on mount
  const [isHydrated, setIsHydrated] = useState(false);

  // ── Hydration & LocalStorage Persistence ──────────────────────────────────

  // Read saved pinned notes and view mode preference from localStorage on mount
  // Running inside useEffect prevents React SSR/client hydration mismatches
  useEffect(() => {
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
      // Gracefully fall back to defaults if localStorage is disabled or restricted
      setPinnedPaths(DEFAULT_PINNED_FALLBACK);
      setActiveReaderPath(DEFAULT_PINNED_FALLBACK[0]);
    } finally {
      setIsHydrated(true);
    }
  }, []);

  // Save pinnedPaths whenever they change after initial hydration
  const persistPinnedPaths = useCallback((paths: string[]) => {
    setPinnedPaths(paths);
    try {
      localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(paths));
    } catch {
      // Ignore quota/privacy errors
    }
  }, []);

  // Save layout viewMode preference whenever toggled
  const handleToggleViewMode = useCallback((mode: "grid" | "reader") => {
    setViewMode(mode);
    try {
      localStorage.setItem(VIEW_MODE_KEY, mode);
    } catch {
      // Ignore quota/privacy errors
    }
  }, []);

  // ── Fetch Note Content ────────────────────────────────────────────────────

  // loadNoteContent: Fetches note content from /api/vault/note?path=... and populates noteDataMap
  const loadNoteContent = useCallback(async (path: string, force = false) => {
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
    await Promise.allSettled(pinnedPaths.map((path) => loadNoteContent(path, true)));
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

  // movePin: Re-orders notes left/right or up/down
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

  // ── Pin Modal: All Notes & Filtering ──────────────────────────────────────

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

  // Unique top-level folder categories derived from all notes for filtering chips
  const folderCategories = useMemo(() => {
    const set = new Set<string>();
    allNotes.forEach((n) => {
      const top = n.folder.split("/")[0];
      if (top) set.add(top);
    });
    return ["all", ...Array.from(set).sort()];
  }, [allNotes]);

  // Filtered notes in modal based on search query and folder chip
  const filteredModalNotes = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return allNotes.filter((note) => {
      const matchesFolder =
        selectedFolderFilter === "all" ||
        note.folder.startsWith(selectedFolderFilter);
      if (!matchesFolder) return false;

      if (!query) return true;
      return (
        note.title.toLowerCase().includes(query) ||
        note.folder.toLowerCase().includes(query) ||
        note.path.toLowerCase().includes(query)
      );
    });
  }, [allNotes, searchQuery, selectedFolderFilter]);

  // Close modal when Escape key is pressed
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isPinModalOpen) {
        setIsPinModalOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isPinModalOpen]);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="px-6 py-6 max-w-7xl mx-auto flex flex-col min-h-[calc(100vh-3rem)]">
      {/* ── Page Header & Workspace Toolbar ──────────────────────────────── */}
      <header className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-border-subtle/80">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="text-xl">📌</span>
            <h1 className="text-2xl font-bold tracking-tight text-text-primary">
              <span className="gradient-text">Pinned Notes</span>
            </h1>
            <span className="px-2 py-0.5 rounded-full text-[0.7rem] font-medium bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/20">
              {pinnedPaths.length} pinned
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
            onClick={handleRefreshAll}
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
              onClick={() => handleToggleViewMode("grid")}
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
              onClick={() => handleToggleViewMode("reader")}
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
            onClick={handleOpenPinModal}
            className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-accent-cyan/80 to-accent-violet/80 text-black font-semibold text-xs hover:opacity-95 shadow-[0_0_20px_rgba(56,189,248,0.25)] flex items-center gap-1.5 transition-all active:scale-[0.98]"
          >
            <span className="text-sm font-bold leading-none">+</span>
            <span>Pin Note</span>
          </button>
        </div>
      </header>

      {/* ── Empty State (When no notes are pinned) ────────────────────────── */}
      {isHydrated && pinnedPaths.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center p-12 text-center animate-fade-in-up">
          <div className="w-16 h-16 rounded-2xl bg-bg-surface border border-border-accent/40 flex items-center justify-center text-3xl mb-4 shadow-[0_0_30px_rgba(56,189,248,0.12)]">
            📌
          </div>
          <h2 className="text-xl font-bold text-text-primary mb-2">No notes pinned yet</h2>
          <p className="text-text-secondary text-xs max-w-md mb-6 leading-relaxed">
            Your home page is a focused personal workspace. Pin your daily schedule, active war rooms, project plans, or core goals so they are immediately at your fingertips.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-2 mb-6 max-w-lg">
            <span className="text-xs text-text-muted mr-1">Suggested quick pins:</span>
            {DEFAULT_PINNED_FALLBACK.map((path) => (
              <button
                key={path}
                type="button"
                onClick={() => togglePin(path)}
                className="px-2.5 py-1 rounded-lg border border-border-subtle bg-bg-surface hover:border-accent-cyan/40 hover:text-accent-cyan text-xs font-mono text-text-secondary transition-all flex items-center gap-1.5"
              >
                <span>+</span>
                <span>{path.split("/").pop()?.replace(/\.md$/, "")}</span>
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={handleOpenPinModal}
            className="px-5 py-2.5 rounded-xl bg-accent-cyan text-black font-semibold text-xs hover:bg-accent-cyan/90 transition-all shadow-[0_0_25px_rgba(56,189,248,0.3)] flex items-center gap-2"
          >
            <span>Browse All Vault Notes</span>
            <span className="text-sm">→</span>
          </button>
        </div>
      ) : null}

      {/* ── VIEW MODE 1: Cards Grid ────────────────────────────────────────── */}
      {isHydrated && pinnedPaths.length > 0 && viewMode === "grid" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-5">
          {pinnedPaths.map((path, index) => {
            const data = noteDataMap[path];
            const isExpanded = expandedCards[path] ?? false;
            const isCopied = copiedPath === path;

            return (
              <div
                key={path}
                className="glass-card flex flex-col border border-border-subtle bg-bg-card hover:border-border-accent/50 transition-all rounded-2xl overflow-hidden shadow-lg group"
              >
                {/* Card Header */}
                <div className="p-4 border-b border-border-subtle/60 bg-bg-secondary/30 flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="text-xs">📌</span>
                      <h2
                        className="text-sm font-semibold text-text-primary truncate"
                        title={data?.title || path}
                      >
                        {data?.title || path.split("/").pop()?.replace(/\.md$/, "")}
                      </h2>
                    </div>
                    <div className="flex items-center gap-2 text-[0.7rem] text-text-muted">
                      <span className="px-1.5 py-0.5 rounded bg-bg-surface font-mono text-[0.65rem] truncate max-w-[220px]">
                        {data?.folder || "Vault Root"}
                      </span>
                    </div>
                  </div>

                  {/* Card Actions */}
                  <div className="flex items-center gap-1 shrink-0">
                    {/* Move Left / Prev Arrow */}
                    {index > 0 && (
                      <button
                        type="button"
                        onClick={() => movePin(index, "prev")}
                        className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors"
                        title="Move pin left"
                      >
                        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                        </svg>
                      </button>
                    )}

                    {/* Move Right / Next Arrow */}
                    {index < pinnedPaths.length - 1 && (
                      <button
                        type="button"
                        onClick={() => movePin(index, "next")}
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
                      onClick={() => handleCopy(path, data?.content || "")}
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
                      onClick={() => toggleCardExpand(path)}
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
                      onClick={(e) => unpinNote(path, e)}
                      className="p-1 rounded text-text-muted hover:text-accent-rose hover:bg-accent-rose/10 transition-colors ml-0.5"
                      title="Unpin note from home page"
                    >
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>

                {/* Card Body (Scrollable Rendered Markdown) */}
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
                        onClick={() => unpinNote(path)}
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

                {/* Card Footer: Metadata / Stats */}
                <div className="px-4 py-2 border-t border-border-subtle/40 bg-bg-secondary/20 flex items-center justify-between text-[0.65rem] text-text-muted mt-auto">
                  <span className="font-mono truncate max-w-[200px]" title={path}>
                    {path}
                  </span>
                  <span>
                    {data?.content ? `${data.content.split(/\s+/).filter(Boolean).length} words` : ""}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── VIEW MODE 2: Workspace Split Reader ────────────────────────────── */}
      {isHydrated && pinnedPaths.length > 0 && viewMode === "reader" && (
        <div className="flex-1 flex flex-col lg:flex-row gap-5 min-h-[600px]">
          {/* Left Rail: Pinned Note Selector List */}
          <aside className="lg:w-80 flex flex-col glass-card border border-border-subtle rounded-2xl overflow-hidden shrink-0">
            <div className="p-3 border-b border-border-subtle bg-bg-secondary/30 flex items-center justify-between">
              <span className="text-xs font-semibold text-text-primary">Pinned Notes</span>
              <span className="text-[0.65rem] text-text-muted">{pinnedPaths.length} notes</span>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
              {pinnedPaths.map((path, idx) => {
                const data = noteDataMap[path];
                const isActive = activeReaderPath === path;

                return (
                  <div
                    key={path}
                    onClick={() => setActiveReaderPath(path)}
                    className={`group w-full p-2.5 rounded-xl text-left cursor-pointer transition-all flex items-start justify-between gap-2 ${
                      isActive
                        ? "bg-accent-cyan/15 border border-accent-cyan/30 text-text-primary shadow-sm"
                        : "hover:bg-bg-surface text-text-secondary hover:text-text-primary border border-transparent"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs">📄</span>
                        <p className="text-xs font-medium truncate">
                          {data?.title || path.split("/").pop()?.replace(/\.md$/, "")}
                        </p>
                      </div>
                      <p className="text-[0.65rem] text-text-muted font-mono truncate mt-0.5">
                        {data?.folder || "Vault Root"}
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => unpinNote(path, e)}
                      className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-accent-rose rounded transition-opacity"
                      title="Unpin note"
                    >
                      <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                );
              })}
            </div>

            <div className="p-2.5 border-t border-border-subtle/60 bg-bg-secondary/20">
              <button
                type="button"
                onClick={handleOpenPinModal}
                className="w-full py-2 rounded-xl border border-dashed border-border-subtle hover:border-accent-cyan/40 text-text-muted hover:text-accent-cyan text-xs font-medium transition-all flex items-center justify-center gap-1.5"
              >
                <span>+</span>
                <span>Pin Another Note</span>
              </button>
            </div>
          </aside>

          {/* Right Pane: Full Document Reader */}
          <main className="flex-1 glass-card border border-border-subtle rounded-2xl flex flex-col overflow-hidden bg-bg-card">
            {activeReaderPath && noteDataMap[activeReaderPath] ? (
              <>
                {/* Reader Header */}
                <div className="p-5 border-b border-border-subtle/60 bg-bg-secondary/30 flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-bold text-text-primary mb-1">
                      {noteDataMap[activeReaderPath]?.title}
                    </h2>
                    <div className="flex items-center gap-2 text-xs text-text-muted font-mono">
                      <span>{noteDataMap[activeReaderPath]?.path}</span>
                      <span>•</span>
                      <span>
                        {noteDataMap[activeReaderPath]?.content
                          ? `${noteDataMap[activeReaderPath].content.split(/\s+/).filter(Boolean).length} words`
                          : "0 words"}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* Copy Markdown */}
                    <button
                      type="button"
                      onClick={() =>
                        handleCopy(
                          activeReaderPath,
                          noteDataMap[activeReaderPath]?.content || ""
                        )
                      }
                      className="px-2.5 py-1.5 rounded-lg border border-border-subtle bg-bg-surface hover:text-accent-cyan text-xs font-medium transition-all flex items-center gap-1.5"
                    >
                      {copiedPath === activeReaderPath ? (
                        <>
                          <span className="text-accent-emerald">✓</span>
                          <span>Copied</span>
                        </>
                      ) : (
                        <>
                          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                            <rect x="9" y="9" width="13" height="13" rx="2" />
                            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                          </svg>
                          <span>Copy</span>
                        </>
                      )}
                    </button>

                    {/* Open in Brain Explorer */}
                    <Link
                      href={`/vault?note=${encodeURIComponent(activeReaderPath)}`}
                      className="px-2.5 py-1.5 rounded-lg border border-border-subtle bg-bg-surface hover:text-accent-violet text-xs font-medium transition-all flex items-center gap-1.5"
                    >
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                      <span>Open in Vault</span>
                    </Link>

                    {/* Unpin */}
                    <button
                      type="button"
                      onClick={() => unpinNote(activeReaderPath)}
                      className="px-2.5 py-1.5 rounded-lg border border-border-subtle bg-bg-surface hover:text-accent-rose hover:border-accent-rose/30 text-xs font-medium transition-all flex items-center gap-1.5 text-text-muted"
                    >
                      <span>Unpin</span>
                    </button>
                  </div>
                </div>

                {/* Reader Markdown Content */}
                <div className="flex-1 overflow-y-auto p-6 text-sm leading-relaxed">
                  {noteDataMap[activeReaderPath]?.loading ? (
                    <div className="py-20 flex flex-col items-center justify-center text-text-muted gap-2">
                      <span className="w-5 h-5 border-2 border-accent-cyan/30 border-t-accent-cyan rounded-full animate-spin"></span>
                      <span className="text-xs">Reading note from Vault...</span>
                    </div>
                  ) : noteDataMap[activeReaderPath]?.error ? (
                    <div className="p-4 rounded-xl bg-accent-rose/10 border border-accent-rose/20 text-accent-rose text-xs space-y-2">
                      <p className="font-semibold">Unable to load note</p>
                      <p className="text-text-muted">{noteDataMap[activeReaderPath].error}</p>
                    </div>
                  ) : (
                    <div className="prose prose-invert max-w-4xl mx-auto">
                      <MarkdownMessage
                        content={noteDataMap[activeReaderPath]?.content || "_Note is empty._"}
                      />
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-text-muted">
                <span className="text-4xl mb-2 opacity-50">📖</span>
                <p className="text-sm">Select a pinned note from the left to read its contents.</p>
              </div>
            )}
          </main>
        </div>
      )}

      {/* ── "+ Pin Note" Modal Dialog ─────────────────────────────────────── */}
      {isPinModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-fade-in-up"
          onClick={() => setIsPinModalOpen(false)}
        >
          <div
            className="w-full max-w-2xl max-h-[85vh] glass-card border border-border-accent/40 bg-bg-secondary flex flex-col rounded-2xl shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="p-4 border-b border-border-subtle bg-bg-surface/50 flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <span className="text-lg">📌</span>
                <h3 className="text-base font-bold text-text-primary">Pin Notes to Home</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsPinModalOpen(false)}
                className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors"
                title="Close (Esc)"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Search Input */}
            <div className="p-4 border-b border-border-subtle/80 bg-bg-secondary/40 space-y-3">
              <div className="relative">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted text-sm">
                  🔍
                </span>
                <input
                  type="text"
                  autoFocus
                  placeholder="Search 300+ notes by title, folder, or keyword..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-border-subtle bg-bg-surface text-text-primary placeholder:text-text-muted text-xs focus:outline-none focus:border-accent-cyan transition-colors"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery("")}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary text-xs"
                  >
                    Clear
                  </button>
                )}
              </div>

              {/* Folder Category Chips */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-[0.7rem] no-scrollbar">
                {folderCategories.map((folder) => {
                  const isSelected = selectedFolderFilter === folder;
                  return (
                    <button
                      key={folder}
                      type="button"
                      onClick={() => setSelectedFolderFilter(folder)}
                      className={`px-2.5 py-1 rounded-lg font-medium whitespace-nowrap transition-all ${
                        isSelected
                          ? "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/30"
                          : "bg-bg-surface text-text-secondary hover:text-text-primary border border-border-subtle/50"
                      }`}
                    >
                      {folder === "all" ? "All Folders" : folder}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Note Results List */}
            <div className="flex-1 overflow-y-auto p-3 space-y-1.5 divide-y divide-border-subtle/20">
              {isLoadingAllNotes ? (
                <div className="py-16 flex flex-col items-center justify-center text-text-muted gap-2">
                  <span className="w-5 h-5 border-2 border-accent-cyan/30 border-t-accent-cyan rounded-full animate-spin"></span>
                  <span className="text-xs">Scanning Vault for markdown notes...</span>
                </div>
              ) : filteredModalNotes.length === 0 ? (
                <div className="py-16 text-center text-text-muted text-xs">
                  <p>No notes matched &ldquo;{searchQuery}&rdquo;</p>
                  <p className="text-[0.7rem] mt-1 text-text-muted/70">
                    Try another search keyword or switch folder filter.
                  </p>
                </div>
              ) : (
                filteredModalNotes.map((note) => {
                  const isPinned = pinnedPaths.includes(note.path);

                  return (
                    <div
                      key={note.path}
                      className="pt-1.5 first:pt-0 flex items-center justify-between gap-3 p-2.5 rounded-xl hover:bg-bg-surface/70 transition-colors"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm">📄</span>
                          <span className="text-xs font-semibold text-text-primary truncate">
                            {note.title}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[0.65rem] text-text-muted font-mono mt-0.5">
                          <span className="truncate">{note.folder}</span>
                          {note.size ? <span>• {(note.size / 1024).toFixed(1)} KB</span> : null}
                        </div>
                      </div>

                      {/* Pin Toggle Button */}
                      <button
                        type="button"
                        onClick={() => togglePin(note.path)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                          isPinned
                            ? "bg-accent-amber/20 text-accent-amber border border-accent-amber/40 hover:bg-accent-rose/20 hover:text-accent-rose hover:border-accent-rose/40"
                            : "bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/25"
                        }`}
                      >
                        {isPinned ? (
                          <>
                            <span>📌</span>
                            <span>Pinned</span>
                          </>
                        ) : (
                          <>
                            <span>+</span>
                            <span>Pin</span>
                          </>
                        )}
                      </button>
                    </div>
                  );
                })
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-3 border-t border-border-subtle bg-bg-secondary/60 flex items-center justify-between text-[0.7rem] text-text-muted">
              <span>{filteredModalNotes.length} notes found</span>
              <button
                type="button"
                onClick={() => setIsPinModalOpen(false)}
                className="px-3 py-1 rounded-lg bg-bg-surface hover:text-text-primary transition-colors text-xs font-medium"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
