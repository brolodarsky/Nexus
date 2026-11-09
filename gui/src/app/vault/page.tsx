"use client";

/**
 * page.tsx — Brain Explorer & Vault Knowledge Browser.
 *
 * Provides a master-detail file browser for the entire Obsidian Vault:
 * - Left rail: Collapsible directory hierarchy with folder navigation and audio podcast badges.
 * - Right pane: Full document reader featuring auto-collapsed YAML frontmatter metadata,
 *   rich Markdown rendering (GFM tables, checkboxes, Obsidian callouts, and [[Wiki-Links]]),
 *   reading metrics, raw/preview view modes, one-click copy, and integrated Podcast Studio.
 */

import React, { useEffect, useState, useMemo, useCallback } from "react";
import { VaultEntry, listVault, generatePodcast, getPodcastAudioUrl, getNote } from "@/lib/api";
import MarkdownMessage from "@/components/MarkdownMessage";
import NoteFrontmatter from "@/components/NoteFrontmatter";

export default function BrainExplorerPage() {
  // currentPath: relative directory path from Vault root (e.g. "1. Core/1.1. Philosophy & Personal North Star")
  const [currentPath, setCurrentPath] = useState<string>("");
  // entries: directory items (files and subfolders) in the active directory
  const [entries, setEntries] = useState<VaultEntry[]>([]);
  // loadingList: visual pulse indicator when fetching directory entries
  const [loadingList, setLoadingList] = useState(true);

  // selectedNote: metadata for the currently active note
  const [selectedNote, setSelectedNote] = useState<VaultEntry | null>(null);
  // noteContent: raw UTF-8 content fetched from /api/vault/note
  const [noteContent, setNoteContent] = useState<string>("");
  // loadingNote: visual pulse indicator while loading note content
  const [loadingNote, setLoadingNote] = useState(false);

  // viewMode: toggles between rendered rich markdown ("preview") and raw source ("raw")
  const [viewMode, setViewMode] = useState<"preview" | "raw">("preview");

  // expandedNotePath: path of the note whose frontmatter is currently expanded (defaults to null = auto-collapsed)
  // By tracking the path of the expanded note, switching notes automatically renders the new note collapsed
  const [expandedNotePath, setExpandedNotePath] = useState<string | null>(null);
  const isFrontmatterExpanded = selectedNote ? expandedNotePath === selectedNote.path : false;
  const toggleFrontmatter = useCallback(() => {
    if (!selectedNote) return;
    setExpandedNotePath((prev) => (prev === selectedNote.path ? null : selectedNote.path));
  }, [selectedNote]);

  // isNoteCopied: temporary 2-second checkmark feedback when copying note content to clipboard
  const [isNoteCopied, setIsNoteCopied] = useState(false);

  // generating: audio podcast generation in progress
  const [generating, setGenerating] = useState(false);
  // audioError: error string returned from podcast generation
  const [audioError, setAudioError] = useState<string | null>(null);

  // isExplorerCollapsed: toggles the file tree menu between full navigation (w-80) and a compact rail (w-14)
  const [isExplorerCollapsed, setIsExplorerCollapsed] = useState(false);
  // isPodcastCollapsed: allows minimizing the Podcast Studio control box when reading long notes
  const [isPodcastCollapsed, setIsPodcastCollapsed] = useState(false);

  // pinnedNotes: array of note paths pinned to the Home page, synchronized via localStorage
  const [pinnedNotes, setPinnedNotes] = useState<string[]>([]);

  // Load pinned notes from localStorage on mount
  useEffect(() => {
    queueMicrotask(() => {
      try {
        const saved = localStorage.getItem("nexus_pinned_notes");
        if (saved) {
          const parsed = JSON.parse(saved);
          if (Array.isArray(parsed)) setPinnedNotes(parsed);
        }
      } catch {
        // Ignore localStorage access restrictions in sandboxed contexts
      }
    });
  }, []);

  // togglePinNote: Toggles whether the currently selected note is pinned to the Home page
  const togglePinNote = (path: string) => {
    const next = pinnedNotes.includes(path)
      ? pinnedNotes.filter((p) => p !== path)
      : [...pinnedNotes, path];
    setPinnedNotes(next);
    try {
      localStorage.setItem("nexus_pinned_notes", JSON.stringify(next));
    } catch {
      // Ignore quota/privacy errors
    }
  };

  // Inspect URL search params on mount to automatically open linked notes (e.g. /vault?note=Tasks.md)
  useEffect(() => {
    queueMicrotask(() => {
      try {
        const params = new URLSearchParams(window.location.search);
        const targetNote = params.get("note");
        if (targetNote) {
          // Strip heading anchors (e.g. "Table of Contents#6. Engineering" -> "Table of Contents")
          const baseTarget = targetNote.split("#")[0].trim();
          const entryName = baseTarget.split("/").pop() || baseTarget;
          const cleanName = entryName.endsWith(".md") ? entryName : `${entryName}.md`;
          const entry: VaultEntry = {
            name: cleanName,
            path: baseTarget,
            type: "file",
            has_audio: false,
          };
          handleSelectNote(entry);
        }
      } catch {
        // Ignore URL parsing errors
      }
    });
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      fetchDirectory(currentPath);
    });
  }, [currentPath]);

  // fetchDirectory: loads folder contents from /api/vault/list?path=...
  async function fetchDirectory(path: string) {
    setLoadingList(true);
    try {
      const data = await listVault(path);
      setEntries(data);
    } catch (e) {
      console.error("Failed to list vault directory:", e);
    } finally {
      setLoadingList(false);
    }
  }

  // handleSelectNote: loads note content from backend and automatically resets frontmatter to collapsed
  async function handleSelectNote(entry: VaultEntry) {
    setSelectedNote(entry);
    setLoadingNote(true);
    setAudioError(null);

    try {
      const data = await getNote(entry.path);
      setNoteContent(data.content);
    } catch {
      setNoteContent("Error loading note.");
    } finally {
      setLoadingNote(false);
    }
  }

  // handleWikiLinkClick: in-place navigation when clicking an Obsidian [[Wiki-Link]] inside the note
  const handleWikiLinkClick = useCallback((target: string) => {
    // Strip heading anchors (e.g. "Table of Contents#6. Engineering" -> "Table of Contents")
    const baseTarget = target.split("#")[0].trim();
    if (!baseTarget) return;

    const entryName = baseTarget.split("/").pop() || baseTarget;
    const cleanName = entryName.endsWith(".md") ? entryName : `${entryName}.md`;
    const entry: VaultEntry = {
      name: cleanName,
      path: baseTarget,
      type: "file",
      has_audio: false,
    };
    handleSelectNote(entry);

    // Synchronize browser URL query param without full page refresh
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("note", baseTarget);
      window.history.pushState(null, "", url.toString());
    } catch {
      // Ignore URL history errors
    }
  }, []);

  // handleCopyNoteContent: copies cleaned markdown body or full note to clipboard
  const handleCopyNoteContent = useCallback(() => {
    if (!noteContent) return;
    const clean = noteContent.replace(/^---\s*File:[^\n]*---\r?\n\r?\n?/i, "");
    navigator.clipboard.writeText(clean);
    setIsNoteCopied(true);
    setTimeout(() => setIsNoteCopied(false), 2000);
  }, [noteContent]);

  // handleGenerate: triggers TTS audio podcast creation via FastAPI
  async function handleGenerate(force = false) {
    if (!selectedNote) return;
    setGenerating(true);
    setAudioError(null);
    try {
      await generatePodcast(selectedNote.path, force);
      // Refresh directory list so the has_audio flag updates
      await fetchDirectory(currentPath);
      // Update selected note reference so the audio player becomes visible
      setSelectedNote({ ...selectedNote, has_audio: true });
    } catch (e) {
      setAudioError(e instanceof Error ? e.message : "Failed to generate audio");
    } finally {
      setGenerating(false);
    }
  }

  function handleNavigateUp() {
    const parts = currentPath.split("/").filter(Boolean);
    parts.pop();
    setCurrentPath(parts.join("/"));
  }

  function handleNavigateDown(folder: string) {
    const newPath = currentPath ? `${currentPath}/${folder}` : folder;
    setCurrentPath(newPath);
  }

  // ── Note Content Parsing & Separation ─────────────────────────────────────

  // Strip backend `--- File: <path> ---` tool header wrapper
  const cleanContent = useMemo(() => {
    if (!noteContent) return "";
    return noteContent.replace(/^---\s*File:[^\n]*---\r?\n\r?\n?/i, "");
  }, [noteContent]);

  // Extract YAML frontmatter block and separate it from the markdown document body
  const { frontmatterRaw, markdownBody } = useMemo(() => {
    if (!cleanContent) return { frontmatterRaw: null, markdownBody: "" };
    const match = cleanContent.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
    if (match) {
      return {
        frontmatterRaw: match[1],
        markdownBody: cleanContent.slice(match[0].length),
      };
    }
    return { frontmatterRaw: null, markdownBody: cleanContent };
  }, [cleanContent]);

  // Document metrics: word count and estimated reading time
  const wordCount = useMemo(() => {
    if (!markdownBody) return 0;
    return markdownBody.split(/\s+/).filter(Boolean).length;
  }, [markdownBody]);

  const readingTimeMinutes = Math.max(1, Math.ceil(wordCount / 225));

  // Path segments for breadcrumbs navigation
  const pathSegments = useMemo(() => {
    if (!selectedNote) return [];
    return selectedNote.path.split("/").filter(Boolean);
  }, [selectedNote]);

  return (
    <div className="flex flex-col md:flex-row min-h-[calc(100dvh-4rem)] md:h-[calc(100vh)] bg-bg-primary">
      {/* ── Left Sidebar (Explorer Menu) ────────────────────── */}
      {isExplorerCollapsed ? (
        // Collapsed Rail: Slim horizontal bar on mobile (< 768px) or vertical column (w-14) on desktop (`md:`)
        <aside
          className="w-full md:w-14 border-b md:border-b-0 md:border-r border-border-subtle flex flex-row md:flex-col bg-bg-secondary/40 py-2.5 px-3 md:py-4 md:px-0 items-center gap-2 md:gap-0 shrink-0 transition-all duration-300 ease-in-out select-none"
          aria-label="Collapsed Brain Explorer"
        >
          <button
            onClick={() => setIsExplorerCollapsed(false)}
            className="p-2 rounded-lg text-text-muted hover:text-accent-cyan hover:bg-bg-surface transition-colors flex items-center justify-center shrink-0 cursor-pointer"
            title="Expand Brain Explorer"
            aria-label="Expand Brain Explorer"
          >
            <svg className="w-4 h-4 rotate-90 md:rotate-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            </svg>
          </button>

          <div
            onClick={() => setIsExplorerCollapsed(false)}
            className="md:mt-3 cursor-pointer p-1.5 md:p-2 rounded-xl text-accent-cyan hover:bg-bg-surface transition-colors flex flex-row md:flex-col items-center gap-1.5 md:gap-1"
            title="Brain Explorer — Click to expand"
          >
            <span className="text-xl">🗂️</span>
            <span className="text-xs font-medium md:hidden">Vault Explorer</span>
          </div>

          {selectedNote && (
            <div
              className="ml-auto md:ml-0 md:mt-auto md:mb-4 p-1.5 md:p-2 text-center truncate max-w-[50%] md:max-w-none"
              title={`Active Note: ${selectedNote.name}`}
            >
              <span className="text-base opacity-70">📄</span>
              <span className="text-xs text-text-muted ml-1 md:hidden truncate">{selectedNote.name}</span>
            </div>
          )}
        </aside>
      ) : (
        // Expanded Explorer Menu: Directory hierarchy, navigate up, and file list
        <aside
          className="w-full md:w-80 max-h-[38vh] md:max-h-none border-b md:border-b-0 md:border-r border-border-subtle flex flex-col bg-bg-secondary/40 shrink-0 transition-all duration-300 ease-in-out"
          aria-label="Brain Explorer Menu"
        >
          <div className="p-4 border-b border-border-subtle shrink-0 flex items-center justify-between">
            <div className="overflow-hidden">
              <h2 className="font-semibold text-lg text-text-primary tracking-tight">Brain Explorer</h2>
              <div className="text-xs text-text-muted mt-1 font-mono truncate" title={currentPath ? `Vault/${currentPath}` : "Vault Root"}>
                {currentPath ? `Vault/${currentPath}` : "Vault Root"}
              </div>
            </div>
            {/* Collapse toggle button */}
            <button
              onClick={() => setIsExplorerCollapsed(true)}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors shrink-0 cursor-pointer"
              title="Collapse Explorer Menu"
              aria-label="Collapse Explorer Menu"
            >
              <svg className="w-4 h-4 rotate-90 md:rotate-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            {currentPath !== "" && (
              <button
                onClick={handleNavigateUp}
                className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-bg-surface transition-colors flex items-center gap-3 text-sm font-medium text-text-secondary group cursor-pointer"
              >
                <span className="text-xl opacity-60 group-hover:opacity-100 transition-opacity">↵</span>
                <span>.. (Up one level)</span>
              </button>
            )}

            {loadingList ? (
              <div className="p-4 text-sm text-text-muted animate-pulse">Loading directory...</div>
            ) : entries.length === 0 ? (
              <div className="p-4 text-sm text-text-muted">Empty directory.</div>
            ) : (
              <ul className="space-y-1 mt-1">
                {entries.map((entry) => {
                  const isSelected = selectedNote?.path === entry.path;
                  if (entry.type === "directory") {
                    return (
                      <li key={entry.path}>
                        <button
                          onClick={() => handleNavigateDown(entry.name)}
                          className="w-full text-left px-3 py-2 rounded-lg hover:bg-bg-surface transition-colors flex items-center gap-3 text-sm text-text-primary cursor-pointer"
                        >
                          <span className="text-lg">📁</span>
                          <span className="truncate">{entry.name}</span>
                        </button>
                      </li>
                    );
                  } else {
                    return (
                      <li key={entry.path}>
                        <button
                          onClick={() => handleSelectNote(entry)}
                          className={`w-full text-left px-3 py-2 rounded-lg transition-all flex items-center gap-3 text-sm cursor-pointer ${
                            isSelected
                              ? "bg-accent-cyan/15 border border-accent-cyan/30 text-accent-cyan shadow-[0_0_10px_rgba(56,189,248,0.1)]"
                              : "hover:bg-bg-surface text-text-secondary hover:text-text-primary"
                          }`}
                        >
                          <span className="text-lg opacity-80">📄</span>
                          <span className="truncate flex-1">{entry.name.replace(/\.md$/, "")}</span>
                          {entry.has_audio && (
                            <span className="text-accent-emerald text-sm" title="Audio ready">🎧</span>
                          )}
                        </button>
                      </li>
                    );
                  }
                })}
              </ul>
            )}
          </div>
        </aside>
      )}

      {/* ── Right Content Area ───────────────────────────── */}
      <div className="flex-1 flex flex-col min-h-[55vh] md:h-full bg-bg-primary overflow-hidden">
        {!selectedNote ? (
          <div className="flex-1 flex flex-col items-center justify-center text-text-muted animate-fade-in-up p-6 text-center">
            <div className="text-6xl mb-4 opacity-50">🗂️</div>
            <p className="text-lg font-medium text-text-primary">No Note Selected</p>
            <p className="text-sm mt-2 max-w-sm text-text-secondary">
              Select a markdown file from the explorer to read its rendered contents or generate an audio podcast.
            </p>
          </div>
        ) : (
          <>
            {/* ── Document Header & Action Bar ───────────────────── */}
            <div className="p-4 md:p-6 border-b border-border-subtle bg-bg-secondary/25 shrink-0 space-y-4">
              {/* Top Row: Title, Breadcrumbs, and Actions */}
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div className="min-w-0">
                  {/* Breadcrumbs Navigation */}
                  <div className="flex items-center gap-1.5 text-xs text-text-muted font-mono mb-1.5 flex-wrap">
                    <span>Vault</span>
                    {pathSegments.slice(0, -1).map((seg, idx) => (
                      <React.Fragment key={idx}>
                        <span className="opacity-40">/</span>
                        <span className="text-text-secondary">{seg}</span>
                      </React.Fragment>
                    ))}
                    <span className="opacity-40">/</span>
                    <span className="text-accent-cyan/80 font-medium">
                      {selectedNote.name}
                    </span>
                  </div>

                  {/* Document Title */}
                  <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-text-primary truncate">
                    {selectedNote.name.replace(/\.md$/, "")}
                  </h1>
                </div>

                {/* Document Actions Bar */}
                <div className="flex items-center gap-2 flex-wrap shrink-0">
                  {/* View Mode Toggle: Preview (Formatted) vs Raw (Source) */}
                  <div className="flex items-center rounded-xl bg-bg-surface/80 border border-border-subtle p-0.5 text-xs">
                    <button
                      type="button"
                      onClick={() => setViewMode("preview")}
                      className={`px-2.5 py-1 rounded-lg font-medium transition-all cursor-pointer flex items-center gap-1.5 ${
                        viewMode === "preview"
                          ? "bg-accent-cyan/15 text-accent-cyan shadow-sm"
                          : "text-text-muted hover:text-text-primary"
                      }`}
                      title="Rendered Markdown view"
                    >
                      <span>👁️</span>
                      <span>Preview</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setViewMode("raw")}
                      className={`px-2.5 py-1 rounded-lg font-medium transition-all cursor-pointer flex items-center gap-1.5 ${
                        viewMode === "raw"
                          ? "bg-accent-cyan/15 text-accent-cyan shadow-sm"
                          : "text-text-muted hover:text-text-primary"
                      }`}
                      title="Raw Markdown source view"
                    >
                      <span>📝</span>
                      <span>Raw</span>
                    </button>
                  </div>

                  {/* Copy Markdown Button */}
                  <button
                    type="button"
                    onClick={handleCopyNoteContent}
                    className="px-3 py-1.5 rounded-xl border border-border-subtle bg-bg-surface hover:text-accent-cyan hover:border-accent-cyan/30 text-xs font-medium transition-all flex items-center gap-1.5 cursor-pointer"
                    title="Copy note markdown to clipboard"
                  >
                    {isNoteCopied ? (
                      <>
                        <span className="text-accent-emerald font-bold">✓</span>
                        <span className="text-accent-emerald font-medium">Copied!</span>
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

                  {/* Pin / Unpin Note to Home Page */}
                  <button
                    type="button"
                    onClick={() => togglePinNote(selectedNote.path)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                      pinnedNotes.includes(selectedNote.path)
                        ? "bg-accent-amber/20 text-accent-amber border border-accent-amber/40 hover:bg-accent-rose/20 hover:text-accent-rose hover:border-accent-rose/40"
                        : "bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/25"
                    }`}
                    title={
                      pinnedNotes.includes(selectedNote.path)
                        ? "Unpin note from Home page"
                        : "Pin note to Home page"
                    }
                  >
                    <span>📌</span>
                    <span>
                      {pinnedNotes.includes(selectedNote.path) ? "Pinned" : "Pin Note"}
                    </span>
                  </button>
                </div>
              </div>

              {/* Sub-Header: Metrics & Path */}
              <div className="flex items-center justify-between gap-3 text-xs text-text-muted flex-wrap">
                <div className="flex items-center gap-3 font-mono text-[0.72rem]">
                  <span>{wordCount.toLocaleString()} words</span>
                  <span>•</span>
                  <span>~{readingTimeMinutes} min read</span>
                </div>
              </div>

              {/* Collapsible Podcast Studio Box */}
              <div className="glass-card p-4 relative overflow-hidden transition-all">
                <div className="absolute top-0 left-0 w-1 h-full bg-accent-violet"></div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <h3 className="font-semibold text-text-primary flex items-center gap-2">
                      <span className="text-lg text-accent-violet">🎙️</span> Podcast Studio
                    </h3>
                    <span className="text-xs text-text-muted hidden sm:inline">
                      {selectedNote.has_audio 
                        ? "Audio podcast ready"
                        : "Convert note to audio podcast"}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    {audioError && (
                      <span className="text-xs text-accent-rose bg-accent-rose/10 px-2.5 py-1 rounded-full border border-accent-rose/20">
                        Error: {audioError}
                      </span>
                    )}

                    {!selectedNote.has_audio && !generating && (
                      <button
                        onClick={() => handleGenerate(false)}
                        className="px-3 py-1.5 rounded-lg bg-accent-cyan/10 border border-accent-cyan/30 text-accent-cyan hover:bg-accent-cyan/20 transition-all font-medium text-xs shadow-[0_0_15px_rgba(56,189,248,0.1)] hover:shadow-[0_0_20px_rgba(56,189,248,0.2)] cursor-pointer"
                      >
                        Generate Audio
                      </button>
                    )}

                    {generating && (
                      <button disabled className="px-3 py-1.5 rounded-lg bg-border-subtle/50 text-text-muted flex items-center gap-2 text-xs font-medium">
                        <span className="w-3.5 h-3.5 border-2 border-text-muted/30 border-t-text-muted rounded-full animate-spin"></span>
                        Generating...
                      </button>
                    )}

                    {selectedNote.has_audio && !generating && (
                      <button
                        onClick={() => handleGenerate(true)}
                        className="px-3 py-1.5 rounded-lg border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-bg-surface transition-colors text-xs font-medium cursor-pointer"
                      >
                        Regenerate
                      </button>
                    )}

                    {/* Podcast Panel Collapse/Expand Toggle */}
                    <button
                      type="button"
                      onClick={() => setIsPodcastCollapsed((prev) => !prev)}
                      className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors ml-1 cursor-pointer"
                      title={isPodcastCollapsed ? "Expand Podcast Studio" : "Collapse Podcast Studio"}
                      aria-expanded={!isPodcastCollapsed}
                    >
                      <svg
                        className={`w-4 h-4 transition-transform duration-200 ${isPodcastCollapsed ? "-rotate-90" : "rotate-0"}`}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                  </div>
                </div>

                {/* Expanded Audio Player & Studio Details */}
                {!isPodcastCollapsed && selectedNote.has_audio && (
                  <div className="mt-4 p-3 rounded-xl bg-bg-primary/50 border border-border-subtle animate-fade-in-up">
                    <audio 
                      key={selectedNote.path} // force reload when path changes
                      controls 
                      className="w-full h-10 outline-none"
                      style={{ filter: "invert(90%) hue-rotate(180deg)" }} // Make default audio player dark mode friendly
                    >
                      <source src={getPodcastAudioUrl(selectedNote.path)} type="audio/mpeg" />
                      Your browser does not support the audio element.
                    </audio>
                  </div>
                )}
              </div>
            </div>

            {/* ── Document Reader Surface ──────────────────────── */}
            <div className="flex-1 overflow-y-auto p-4 md:p-8 bg-bg-primary">
              {loadingNote ? (
                <div className="max-w-4xl mx-auto py-12 flex flex-col items-center justify-center text-text-muted gap-3">
                  <span className="w-6 h-6 border-2 border-accent-cyan/30 border-t-accent-cyan rounded-full animate-spin"></span>
                  <span className="text-xs font-mono">Reading note from Vault...</span>
                </div>
              ) : viewMode === "raw" ? (
                // Raw Markdown Source View
                <div className="max-w-4xl mx-auto">
                  <div className="rounded-2xl border border-border-subtle bg-[#05070e] p-4 md:p-6 shadow-2xl overflow-x-auto">
                    <pre className="font-mono text-xs text-zinc-300 leading-relaxed whitespace-pre-wrap break-words">
                      {cleanContent}
                    </pre>
                  </div>
                </div>
              ) : (
                // Formatted Sexy Markdown Preview View
                <article className="max-w-4xl mx-auto w-full glass-card border border-border-subtle/60 rounded-2xl p-6 md:p-10 shadow-2xl bg-bg-card">
                  {/* Auto-Collapsing Frontmatter Panel */}
                  {frontmatterRaw && (
                    <div className="mb-6">
                      <NoteFrontmatter
                        rawYaml={frontmatterRaw}
                        isExpanded={isFrontmatterExpanded}
                        onToggleExpand={toggleFrontmatter}
                      />
                    </div>
                  )}

                  {/* Rendered Markdown Body */}
                  <div className="prose prose-invert max-w-none">
                    <MarkdownMessage
                      content={markdownBody || "_Note is empty._"}
                      onWikiLinkClick={handleWikiLinkClick}
                    />
                  </div>
                </article>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
