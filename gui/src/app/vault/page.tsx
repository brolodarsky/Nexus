"use client";

import { useEffect, useState } from "react";
import { VaultEntry, listVault, generatePodcast, getPodcastAudioUrl, getNote, NoteContentResponse } from "@/lib/api";

export default function BrainExplorerPage() {
  const [currentPath, setCurrentPath] = useState<string>("");
  const [entries, setEntries] = useState<VaultEntry[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  
  const [selectedNote, setSelectedNote] = useState<VaultEntry | null>(null);
  const [noteContent, setNoteContent] = useState<string>("");
  const [loadingNote, setLoadingNote] = useState(false);
  
  const [generating, setGenerating] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);

  // isExplorerCollapsed: toggles the file tree menu between full navigation (w-80) and a compact rail (w-14)
  const [isExplorerCollapsed, setIsExplorerCollapsed] = useState(false);
  // isPodcastCollapsed: allows minimizing the Podcast Studio control box when reading long notes
  const [isPodcastCollapsed, setIsPodcastCollapsed] = useState(false);

  useEffect(() => {
    fetchDirectory(currentPath);
  }, [currentPath]);

  async function fetchDirectory(path: string) {
    setLoadingList(true);
    try {
      const data = await listVault(path);
      setEntries(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingList(false);
    }
  }

  async function handleSelectNote(entry: VaultEntry) {
    setSelectedNote(entry);
    setLoadingNote(true);
    setAudioError(null);
    try {
      const data = await getNote(entry.path);
      setNoteContent(data.content);
    } catch (e) {
      setNoteContent("Error loading note.");
    } finally {
      setLoadingNote(false);
    }
  }

  async function handleGenerate(force = false) {
    if (!selectedNote) return;
    setGenerating(true);
    setAudioError(null);
    try {
      await generatePodcast(selectedNote.path, force);
      // Refresh the directory list so the has_audio flag updates
      await fetchDirectory(currentPath);
      // Update selected note reference so the player shows up
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

  return (
    <div className="flex h-[calc(100vh)] bg-bg-primary">
      {/* ── Left Sidebar (Explorer Menu) ────────────────────── */}
      {isExplorerCollapsed ? (
        // Collapsed Rail: Slim column with expand button and folder glyph
        <aside
          className="w-14 border-r border-border-subtle flex flex-col bg-bg-secondary/40 py-4 items-center shrink-0 transition-all duration-300 ease-in-out select-none"
          aria-label="Collapsed Brain Explorer"
        >
          <button
            onClick={() => setIsExplorerCollapsed(false)}
            className="p-2 rounded-lg text-text-muted hover:text-accent-cyan hover:bg-bg-surface transition-colors flex items-center justify-center"
            title="Expand Brain Explorer"
            aria-label="Expand Brain Explorer"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            </svg>
          </button>

          <div
            onClick={() => setIsExplorerCollapsed(false)}
            className="mt-3 cursor-pointer p-2 rounded-xl text-accent-cyan hover:bg-bg-surface transition-colors flex flex-col items-center gap-1"
            title="Brain Explorer — Click to expand"
          >
            <span className="text-xl">🗂️</span>
          </div>

          {selectedNote && (
            <div
              className="mt-auto mb-4 p-2 text-center"
              title={`Active Note: ${selectedNote.name}`}
            >
              <span className="text-base opacity-70">📄</span>
            </div>
          )}
        </aside>
      ) : (
        // Expanded Explorer Menu: Directory hierarchy, navigate up, and file list
        <aside
          className="w-80 border-r border-border-subtle flex flex-col bg-bg-secondary/40 shrink-0 transition-all duration-300 ease-in-out"
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
              className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors shrink-0"
              title="Collapse Explorer Menu"
              aria-label="Collapse Explorer Menu"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            {currentPath !== "" && (
              <button
                onClick={handleNavigateUp}
                className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-bg-surface transition-colors flex items-center gap-3 text-sm font-medium text-text-secondary group"
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
                          className="w-full text-left px-3 py-2 rounded-lg hover:bg-bg-surface transition-colors flex items-center gap-3 text-sm text-text-primary"
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
                          className={`w-full text-left px-3 py-2 rounded-lg transition-all flex items-center gap-3 text-sm ${
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
      <div className="flex-1 flex flex-col h-full bg-bg-primary overflow-hidden">
        {!selectedNote ? (
          <div className="flex-1 flex flex-col items-center justify-center text-text-muted animate-fade-in-up">
            <div className="text-6xl mb-4 opacity-50">🗂️</div>
            <p className="text-lg font-medium text-text-primary">No Note Selected</p>
            <p className="text-sm mt-2">Select a markdown file from the explorer to preview it or generate a podcast.</p>
          </div>
        ) : (
          <>
            {/* Header / Podcast Control Panel */}
            <div className="p-6 border-b border-border-subtle bg-bg-secondary/20 shrink-0">
              <h1 className="text-2xl font-bold text-text-primary mb-1 truncate">{selectedNote.name.replace(/\.md$/, "")}</h1>
              <p className="text-xs font-mono text-text-muted mb-4">{selectedNote.path}</p>

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
                        className="px-3 py-1.5 rounded-lg bg-accent-cyan/10 border border-accent-cyan/30 text-accent-cyan hover:bg-accent-cyan/20 transition-all font-medium text-xs shadow-[0_0_15px_rgba(56,189,248,0.1)] hover:shadow-[0_0_20px_rgba(56,189,248,0.2)]"
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
                        className="px-3 py-1.5 rounded-lg border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-bg-surface transition-colors text-xs font-medium"
                      >
                        Regenerate
                      </button>
                    )}

                    {/* Podcast Panel Collapse/Expand Toggle */}
                    <button
                      type="button"
                      onClick={() => setIsPodcastCollapsed((prev) => !prev)}
                      className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors ml-1"
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
                      style={{ filter: "invert(90%) hue-rotate(180deg)" }} // Quick hack to make default audio player dark mode friendly
                    >
                      <source src={getPodcastAudioUrl(selectedNote.path)} type="audio/mpeg" />
                      Your browser does not support the audio element.
                    </audio>
                  </div>
                )}
              </div>
            </div>

            {/* Note Preview */}
            <div className="flex-1 overflow-y-auto p-6 bg-bg-primary">
              {loadingNote ? (
                <div className="animate-pulse space-y-3">
                  <div className="h-4 bg-bg-surface rounded w-3/4"></div>
                  <div className="h-4 bg-bg-surface rounded w-1/2"></div>
                  <div className="h-4 bg-bg-surface rounded w-5/6"></div>
                </div>
              ) : (
                <div className="prose prose-invert max-w-3xl">
                  <pre className="text-sm font-mono text-text-secondary whitespace-pre-wrap font-sans">
                    {noteContent}
                  </pre>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
