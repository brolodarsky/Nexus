"use client";

/**
 * ChatHeader.tsx — Top header bar for the Nexus Chat workspace.
 * Displays the active conversation title (with inline click-to-rename and AI auto-generation),
 * orchestrator subtitle, and Shared Blackboard toggle button.
 */

import { useState, useRef } from "react";

// ChatHeaderProps: defines the display state and callbacks for the Chat workspace header
// - title: active conversation title string (falls back to "Chat" when starting a fresh session)
// - activeConvId: UUID of the active conversation thread (or null/undefined if in a draft state)
// - showBoard: boolean indicating whether the right-hand Subagent Blackboard drawer is open
// - bulletinCount: number of active bulletins currently on the Blackboard
// - onToggleBoard: callback invoked when the user clicks the Subagent Board toggle button
// - onUpdateTitle: optional async callback invoked when committing an edited conversation title
// - onAutoGenerateTitle: optional async callback invoked to generate a smart AI title via fast low-tier model
export interface ChatHeaderProps {
  title?: string;
  activeConvId?: string | null;
  showBoard: boolean;
  bulletinCount: number;
  onToggleBoard: () => void;
  onUpdateTitle?: (id: string, newTitle: string) => Promise<void> | void;
  onAutoGenerateTitle?: (id: string) => Promise<void> | void;
}

export default function ChatHeader({
  title,
  activeConvId,
  showBoard,
  bulletinCount,
  onToggleBoard,
  onUpdateTitle,
  onAutoGenerateTitle,
}: ChatHeaderProps) {
  // isEditing: boolean controlling whether the title text is replaced by an inline edit input
  const [isEditing, setIsEditing] = useState<boolean>(false);
  // editTitle: draft title string actively typed by the user
  const [editTitle, setEditTitle] = useState<string>("");
  // isGenerating: boolean indicating whether an AI auto-titling request is currently in flight
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  // headerInputRef: HTMLInputElement reference used for auto-focus and text selection
  const headerInputRef = useRef<HTMLInputElement>(null);

  // Initiates inline header rename mode
  const handleStartEdit = () => {
    if (!activeConvId) return;
    setIsEditing(true);
    setEditTitle(title || "New Chat");
    queueMicrotask(() => {
      headerInputRef.current?.focus();
      headerInputRef.current?.select();
    });
  };

  // Commits the modified title
  const handleSaveEdit = async () => {
    const trimmed = editTitle.trim();
    if (trimmed && activeConvId && onUpdateTitle) {
      await onUpdateTitle(activeConvId, trimmed);
    }
    setIsEditing(false);
  };

  // Cancels editing mode
  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditTitle("");
  };

  // Triggers backend AI auto-titling coroutine via low-tier Flash/Sonnet model
  const handleAutoTitle = async () => {
    if (!activeConvId || !onAutoGenerateTitle || isGenerating) return;
    setIsGenerating(true);
    try {
      await onAutoGenerateTitle(activeConvId);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <header className="px-8 py-4 border-b border-border-subtle shrink-0 flex items-center justify-between">
      <div className="flex items-center min-w-0 mr-4">
        {isEditing ? (
          // Inline Edit Mode: Input box with save and cancel buttons
          <div className="flex items-center gap-2">
            <input
              ref={headerInputRef}
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleSaveEdit();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  handleCancelEdit();
                }
              }}
              className="bg-bg-tertiary border border-accent-cyan/50 rounded-lg px-3 py-1 text-lg font-bold text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-cyan shadow-inner"
              placeholder="Conversation title..."
            />
            <button
              type="button"
              onClick={handleSaveEdit}
              className="p-1.5 rounded-lg text-accent-cyan hover:bg-accent-cyan/15 transition-colors font-bold text-sm"
              title="Save title (Enter)"
              aria-label="Save title"
            >
              ✓
            </button>
            <button
              type="button"
              onClick={handleCancelEdit}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors text-sm"
              title="Cancel (Esc)"
              aria-label="Cancel editing"
            >
              ✕
            </button>
          </div>
        ) : (
          // Standard Display Mode: Title with always-visible rename pencil and AI auto-generate sparkle pill
          <div className="flex items-center gap-3 min-w-0">
            <h1
              className={`text-xl font-bold tracking-tight truncate ${activeConvId ? "cursor-pointer hover:opacity-90" : ""}`}
              onClick={handleStartEdit}
              title={activeConvId ? "Click or double-click to rename chat" : undefined}
            >
              <span className="gradient-text">{title || "Chat"}</span>
            </h1>

            {activeConvId ? (
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  type="button"
                  onClick={handleStartEdit}
                  className="p-1.5 rounded-lg text-text-muted hover:text-accent-cyan hover:bg-bg-tertiary transition-colors"
                  title="Rename Chat"
                  aria-label="Rename Chat"
                >
                  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </button>
                {onAutoGenerateTitle && (
                  <button
                    type="button"
                    disabled={isGenerating}
                    onClick={handleAutoTitle}
                    className={`text-xs px-2.5 py-1 rounded-lg border transition-all flex items-center gap-1.5 font-medium ${
                      isGenerating
                        ? "bg-accent-violet/20 border-accent-violet/40 text-purple-300 animate-pulse"
                        : "bg-accent-violet/10 border-accent-violet/30 text-purple-300 hover:bg-accent-violet/20 hover:border-accent-violet/50"
                    }`}
                    title="Auto-generate concise conversation title with AI"
                    aria-label="Auto-generate title with AI"
                  >
                    <span className="text-xs">✨</span>
                    <span>{isGenerating ? "Generating..." : "Auto-title"}</span>
                  </button>
                )}
              </div>
            ) : (
              // Blank draft state: renders a subtle disabled pill so users see the capability upfront
              <div className="flex items-center gap-1.5 shrink-0 opacity-40">
                <span
                  className="text-xs px-2.5 py-1 rounded-lg border border-border-subtle bg-bg-tertiary/40 text-text-muted flex items-center gap-1.5 cursor-not-allowed select-none"
                  title="Send a message first to generate title with AI"
                >
                  <span className="text-xs">✨</span>
                  <span>Auto-title</span>
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={onToggleBoard}
          className={`text-xs px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 ${showBoard
            ? "bg-accent-cyan/15 border-accent-cyan/30 text-accent-cyan"
            : "bg-bg-tertiary border-border-subtle text-text-secondary hover:text-text-primary"
            }`}
          title="Toggle Agent Blackboard"
        >
          <span>Subagent Board</span>
          <span className="px-1.5 py-0.2 rounded-full bg-bg-primary/60 text-[0.65rem] font-mono">
            {bulletinCount}
          </span>
        </button>
      </div>
    </header>
  );
}

