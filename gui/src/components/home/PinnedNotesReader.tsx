"use client";

/**
 * PinnedNotesReader.tsx — IDE-style split workspace reader for pinned notes.
 *
 * Implements a master-detail split layout:
 * - Left rail: Navigation menu listing all pinned notes with active indicator, folder badge,
 *   hover-to-reveal unpin action, and a quick "+ Pin Another Note" launcher.
 * - Right pane: Full document reader with document stats, copy-markdown action,
 *   direct link to Vault explorer, auto-collapsed YAML frontmatter metadata,
 *   and scrollable rendered Markdown content.
 */

import React, { useState, useCallback } from "react";
import Link from "next/link";
import MarkdownMessage from "@/components/MarkdownMessage";
import NoteFrontmatter from "@/components/NoteFrontmatter";
import type { PinnedNotesReaderProps } from "./types";

/**
 * PinnedNotesReader displays the side-by-side split reader view for focused reading.
 *
 * @param props.pinnedPaths - Ordered array of Vault-relative paths currently pinned.
 * @param props.noteDataMap - Map of note paths to loaded metadata and content.
 * @param props.activeReaderPath - Currently active note path displayed in the right reader pane.
 * @param props.copiedPath - Path of the note recently copied to clipboard (for checkmark feedback).
 * @param props.onSelectReaderPath - Callback when clicking a note in the left rail.
 * @param props.onUnpinNote - Callback to unpin a note.
 * @param props.onCopyNote - Callback to copy note content to clipboard.
 * @param props.onOpenPinModal - Callback to open the pin modal from the left rail.
 */
export default function PinnedNotesReader({
  pinnedPaths,
  noteDataMap,
  activeReaderPath,
  copiedPath,
  onSelectReaderPath,
  onUnpinNote,
  onCopyNote,
  onOpenPinModal,
}: PinnedNotesReaderProps) {
  const activeNote = activeReaderPath ? noteDataMap[activeReaderPath] : null;
  const isCopied = activeReaderPath ? copiedPath === activeReaderPath : false;

  // expandedPath: track which note path currently has its frontmatter expanded (default null = all auto-collapsed)
  // By matching against activeReaderPath, any note switch automatically starts in the collapsed state
  const [expandedPath, setExpandedPath] = useState<string | null>(null);
  const isFrontmatterExpanded = activeReaderPath ? expandedPath === activeReaderPath : false;
  const toggleFrontmatter = useCallback(() => {
    if (!activeReaderPath) return;
    setExpandedPath((prev) => (prev === activeReaderPath ? null : activeReaderPath));
  }, [activeReaderPath]);

  // Strip backend `--- File: <path> ---` tool wrapper header
  const cleanContent = activeNote?.content
    ? activeNote.content.replace(/^---\s*File:[^\n]*---\r?\n\r?\n?/i, "")
    : "";

  // Separate YAML frontmatter block from markdown document body
  const fmMatch = cleanContent ? cleanContent.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/) : null;
  const frontmatterRaw = fmMatch ? fmMatch[1] : null;
  const markdownBody = fmMatch ? cleanContent.slice(fmMatch[0].length) : cleanContent;
  const wordCount = markdownBody ? markdownBody.split(/\s+/).filter(Boolean).length : 0;

  return (
    <div className="flex-1 flex flex-col lg:flex-row gap-5 min-h-[600px]">
      {/* ── Left Rail: Pinned Note Selector List ──────────────────────────── */}
      <aside className="lg:w-80 flex flex-col glass-card border border-border-subtle rounded-2xl overflow-hidden shrink-0">
        <div className="p-3 border-b border-border-subtle bg-bg-secondary/30 flex items-center justify-between">
          <span className="text-xs font-semibold text-text-primary">Pinned Notes</span>
          <span className="text-[0.65rem] text-text-muted">{pinnedPaths.length} notes</span>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
          {pinnedPaths.map((path) => {
            const data = noteDataMap[path];
            const isActive = activeReaderPath === path;
            const title = data?.title || path.split("/").pop()?.replace(/\.md$/, "");
            const folder = data?.folder || "Vault Root";

            return (
              <div
                key={path}
                onClick={() => onSelectReaderPath(path)}
                className={`group w-full p-2.5 rounded-xl text-left cursor-pointer transition-all flex items-start justify-between gap-2 ${
                  isActive
                    ? "bg-accent-cyan/15 border border-accent-cyan/30 text-text-primary shadow-sm"
                    : "hover:bg-bg-surface text-text-secondary hover:text-text-primary border border-transparent"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs">📄</span>
                    <p className="text-xs font-medium truncate">{title}</p>
                  </div>
                  <p className="text-[0.65rem] text-text-muted font-mono truncate mt-0.5">
                    {folder}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={(e) => onUnpinNote(path, e)}
                  className="opacity-100 md:opacity-0 md:group-hover:opacity-100 p-1 text-text-muted hover:text-accent-rose rounded transition-opacity cursor-pointer"
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
            onClick={onOpenPinModal}
            className="w-full py-2 rounded-xl border border-dashed border-border-subtle hover:border-accent-cyan/40 text-text-muted hover:text-accent-cyan text-xs font-medium transition-all flex items-center justify-center gap-1.5 cursor-pointer"
          >
            <span>+</span>
            <span>Pin Another Note</span>
          </button>
        </div>
      </aside>

      {/* ── Right Pane: Full Document Reader ──────────────────────────────── */}
      <main className="flex-1 glass-card border border-border-subtle rounded-2xl flex flex-col overflow-hidden bg-bg-card">
        {activeReaderPath && activeNote ? (
          <>
            {/* Reader Header */}
            <div className="p-4 md:p-5 border-b border-border-subtle/60 bg-bg-secondary/30 flex flex-col sm:flex-row sm:items-start justify-between gap-3 md:gap-4">
              <div className="min-w-0">
                <h2 className="text-lg md:text-xl font-bold text-text-primary mb-1 break-words">
                  {activeNote.title}
                </h2>
                <div className="flex items-center flex-wrap gap-2 text-xs text-text-muted font-mono">
                  <span className="break-all">{activeNote.path}</span>
                  <span>•</span>
                  <span>{wordCount.toLocaleString()} words</span>
                </div>
              </div>

              <div className="flex items-center flex-wrap gap-2 shrink-0">
                {/* Copy Markdown */}
                <button
                  type="button"
                  onClick={() => onCopyNote(activeReaderPath, cleanContent || "")}
                  className="px-2.5 py-1.5 rounded-lg border border-border-subtle bg-bg-surface hover:text-accent-cyan text-xs font-medium transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  {isCopied ? (
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
                  onClick={() => onUnpinNote(activeReaderPath)}
                  className="px-2.5 py-1.5 rounded-lg border border-border-subtle bg-bg-surface hover:text-accent-rose hover:border-accent-rose/30 text-xs font-medium transition-all flex items-center gap-1.5 text-text-muted cursor-pointer"
                >
                  <span>Unpin</span>
                </button>
              </div>
            </div>

            {/* Reader Markdown Content */}
            <div className="flex-1 overflow-y-auto p-6 text-sm leading-relaxed">
              {activeNote.loading ? (
                <div className="py-20 flex flex-col items-center justify-center text-text-muted gap-2">
                  <span className="w-5 h-5 border-2 border-accent-cyan/30 border-t-accent-cyan rounded-full animate-spin"></span>
                  <span className="text-xs font-mono">Reading note from Vault...</span>
                </div>
              ) : activeNote.error ? (
                <div className="p-4 rounded-xl bg-accent-rose/10 border border-accent-rose/20 text-accent-rose text-xs space-y-2">
                  <p className="font-semibold">Unable to load note</p>
                  <p className="text-text-muted">{activeNote.error}</p>
                </div>
              ) : (
                <div className="prose prose-invert max-w-4xl mx-auto space-y-5">
                  {/* Auto-Collapsing Frontmatter Panel */}
                  {frontmatterRaw && (
                    <NoteFrontmatter
                      rawYaml={frontmatterRaw}
                      isExpanded={isFrontmatterExpanded}
                      onToggleExpand={toggleFrontmatter}
                    />
                  )}

                  {/* Rendered Document Body */}
                  <MarkdownMessage
                    content={markdownBody || "_Note is empty._"}
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
  );
}
