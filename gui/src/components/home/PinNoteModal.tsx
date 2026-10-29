"use client";

/**
 * PinNoteModal.tsx — Searchable modal dialog for discovering and pinning Vault notes.
 *
 * Provides a responsive modal interface to search across 300+ Vault markdown notes
 * by title, folder, or keyword, with horizontal folder category filter chips, live
 * pinned status indicators, and keyboard dismissal (Escape key).
 */

import React, { useState, useMemo, useEffect } from "react";
import type { PinNoteModalProps } from "./types";

/**
 * PinNoteModal allows users to browse all notes across the Obsidian Vault and toggle
 * their pinned status on the Home page.
 *
 * @param props.isOpen - Whether the modal dialog is currently visible.
 * @param props.onClose - Function invoked to close the modal.
 * @param props.allNotes - Flat list of all Vault note summaries fetched from `/api/vault/notes`.
 * @param props.isLoadingAllNotes - Boolean indicating whether the initial note index fetch is in-flight.
 * @param props.pinnedPaths - Array of currently pinned paths, used to render active toggle state.
 * @param props.onTogglePin - Callback to pin or unpin a given note path.
 */
export default function PinNoteModal({
  isOpen,
  onClose,
  allNotes,
  isLoadingAllNotes,
  pinnedPaths,
  onTogglePin,
}: PinNoteModalProps) {
  // Local search query input within the modal
  const [searchQuery, setSearchQuery] = useState("");
  // Active top-level folder category filter ("all" or folder prefix like "1. Core")
  const [selectedFolderFilter, setSelectedFolderFilter] = useState("all");

  // Derive unique top-level folder categories from all notes for filter chips
  const folderCategories = useMemo(() => {
    const set = new Set<string>();
    allNotes.forEach((n) => {
      const top = n.folder.split("/")[0];
      if (top) set.add(top);
    });
    return ["all", ...Array.from(set).sort()];
  }, [allNotes]);

  // Compute filtered list based on active folder filter and search query
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

  // Attach Escape key listener to dismiss modal
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-fade-in-up"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[85vh] glass-card border border-border-accent/40 bg-bg-secondary flex flex-col rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Modal Header ──────────────────────────────────────────────────── */}
        <div className="p-4 border-b border-border-subtle bg-bg-surface/50 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-lg">📌</span>
            <h3 className="text-base font-bold text-text-primary">Pin Notes to Home</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors"
            title="Close (Esc)"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* ── Search Input & Folder Category Chips ────────────────────────── */}
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

          {/* Folder Category Filter Chips */}
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

        {/* ── Note Results List ────────────────────────────────────────────── */}
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
                    onClick={() => onTogglePin(note.path)}
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

        {/* ── Modal Footer ──────────────────────────────────────────────────── */}
        <div className="p-3 border-t border-border-subtle bg-bg-secondary/60 flex items-center justify-between text-[0.7rem] text-text-muted">
          <span>{filteredModalNotes.length} notes found</span>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1 rounded-lg bg-bg-surface hover:text-text-primary transition-colors text-xs font-medium"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
