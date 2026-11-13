"use client";

/**
 * ChatHeader.tsx — Top header bar for the Nexus Chat workspace.
 * Displays the active conversation title (with inline click-to-rename and AI auto-generation).
 */

// memo: Prevents header re-renders when sibling chat components or drafts mutate
// useEffect: Binds click-outside and keydown listeners to dismiss the conversation options dropdown
import { useState, useRef, useEffect, memo } from "react";

// ChatHeaderProps: defines the display state and callbacks for the Chat workspace header
// - title: active conversation title string (falls back to "Chat" when starting a fresh session)
// - activeConvId: UUID of the active conversation thread (or null/undefined if in a draft state)
// - onOpenMobileSidebar: optional callback invoked on mobile (< 768px) to open the slide-over conversation drawer
// - onUpdateTitle: optional async callback invoked when committing an edited conversation title
// - onAutoGenerateTitle: optional async callback invoked to generate a smart AI title via fast low-tier model
// - onDeleteChat: optional async callback invoked to delete the active conversation thread
export interface ChatHeaderProps {
  title?: string;
  activeConvId?: string | null;
  onOpenMobileSidebar?: () => void;
  onUpdateTitle?: (id: string, newTitle: string) => Promise<void> | void;
  onAutoGenerateTitle?: (id: string) => Promise<void> | void;
  onDeleteChat?: (id: string) => Promise<void> | void;
}

const ChatHeader = memo(function ChatHeader({
  title,
  activeConvId,
  onOpenMobileSidebar,
  onUpdateTitle,
  onAutoGenerateTitle,
  onDeleteChat,
}: ChatHeaderProps) {
  // isEditing: boolean controlling whether the title text is replaced by an inline edit input
  const [isEditing, setIsEditing] = useState<boolean>(false);
  // editTitle: draft title string actively typed by the user
  const [editTitle, setEditTitle] = useState<string>("");
  // isGenerating: boolean indicating whether an AI auto-titling request is currently in flight
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  // isMenuOpen: boolean controlling visibility of the folded three-dots options dropdown menu
  const [isMenuOpen, setIsMenuOpen] = useState<boolean>(false);
  // headerInputRef: HTMLInputElement reference used for auto-focus and text selection
  const headerInputRef = useRef<HTMLInputElement>(null);
  // menuRef: HTMLDivElement reference used for detecting outside clicks to dismiss the options dropdown
  const menuRef = useRef<HTMLDivElement>(null);

  // Close dropdown menu on outside click or Escape key press
  useEffect(() => {
    if (!isMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMenuOpen]);

  // Dismiss dropdown menu whenever active conversation changes
  useEffect(() => {
    setIsMenuOpen(false);
  }, [activeConvId]);

  // Initiates inline header rename mode
  const handleStartEdit = () => {
    if (!activeConvId) return;
    setIsMenuOpen(false);
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
    setIsMenuOpen(false);
    setIsGenerating(true);
    try {
      await onAutoGenerateTitle(activeConvId);
    } finally {
      setIsGenerating(false);
    }
  };

  // Deletes active conversation thread via parent orchestrator callback
  const handleDelete = async () => {
    if (!activeConvId || !onDeleteChat) return;
    setIsMenuOpen(false);
    if (window.confirm("Are you sure you want to delete this conversation?")) {
      await onDeleteChat(activeConvId);
    }
  };

  return (
    <header className="px-4 md:px-8 py-3 md:py-4 border-b border-border-subtle shrink-0 flex items-center justify-between gap-2">
      <div className="flex items-center min-w-0 mr-2 md:mr-4 flex-1">
        {/* Mobile Hamburger / Threads Drawer Trigger (`< 768px` / `md:hidden`): Opens ChatSidebar as a slide-over overlay */}
        {onOpenMobileSidebar && (
          <button
            type="button"
            onClick={onOpenMobileSidebar}
            className="md:hidden mr-2.5 p-2 -ml-1 rounded-xl border border-border-subtle bg-bg-tertiary/70 text-text-secondary hover:text-accent-cyan hover:border-accent-cyan/40 transition-colors shrink-0 flex items-center justify-center"
            title="Open conversations drawer"
            aria-label="Open conversations drawer"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h10" />
            </svg>
          </button>
        )}

        {isEditing ? (
          // Inline Edit Mode: Input box with save and cancel buttons (uses text-base on mobile to prevent iOS Safari auto-zoom)
          <div className="flex items-center gap-2 min-w-0 flex-1">
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
              className="min-w-0 flex-1 md:flex-initial bg-bg-tertiary border border-accent-cyan/50 rounded-lg px-3 py-1 text-base md:text-lg font-bold text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-cyan shadow-inner"
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
          // Standard Display Mode: Title with folded three-dots conversation options menu
          <div className="flex items-center gap-2 md:gap-3 min-w-0">
            <h1
              className={`text-lg md:text-xl font-bold tracking-tight truncate ${activeConvId ? "cursor-pointer hover:opacity-90" : ""}`}
              onClick={handleStartEdit}
              title={activeConvId ? "Click or double-click to rename chat" : undefined}
            >
              <span className="gradient-text">{title || "Chat"}</span>
            </h1>

            {activeConvId && (
              <div className="flex items-center gap-1.5 shrink-0">
                {/* Visual indicator when background AI auto-titling is actively generating */}
                {isGenerating && (
                  <span className="text-xs px-2 py-0.5 rounded-md bg-accent-violet/15 text-purple-300 border border-accent-violet/30 animate-pulse flex items-center gap-1 font-mono shrink-0">
                    <span>✨</span>
                    <span className="hidden sm:inline text-[0.7rem]">Titling...</span>
                  </span>
                )}

                {/* Three-dots menu container with outside click detection */}
                <div className="relative shrink-0" ref={menuRef}>
                  <button
                    type="button"
                    onClick={() => setIsMenuOpen((prev) => !prev)}
                    className={`p-1.5 rounded-lg transition-colors flex items-center justify-center ${
                      isMenuOpen
                        ? "bg-bg-tertiary text-text-primary border border-border-subtle"
                        : "text-text-muted hover:text-text-primary hover:bg-bg-tertiary"
                    }`}
                    title="Conversation options"
                    aria-label="Conversation options"
                    aria-haspopup="menu"
                    aria-expanded={isMenuOpen}
                  >
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                      <circle cx="5" cy="12" r="2" />
                      <circle cx="12" cy="12" r="2" />
                      <circle cx="19" cy="12" r="2" />
                    </svg>
                  </button>

                  {/* Popover options dropdown */}
                  {isMenuOpen && (
                    <div
                      role="menu"
                      aria-orientation="vertical"
                      className="absolute left-0 top-full mt-1.5 w-48 rounded-xl bg-bg-secondary/95 backdrop-blur-md border border-border-subtle shadow-xl p-1 z-50 animate-in fade-in zoom-in-95 duration-100"
                    >
                      {/* Rename action */}
                      <button
                        type="button"
                        role="menuitem"
                        onClick={handleStartEdit}
                        className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors text-left"
                      >
                        <svg className="w-3.5 h-3.5 text-text-muted shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                        <span>Rename</span>
                      </button>

                      {/* AI Auto-generate title action */}
                      {onAutoGenerateTitle && (
                        <button
                          type="button"
                          role="menuitem"
                          disabled={isGenerating}
                          onClick={handleAutoTitle}
                          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors text-left ${
                            isGenerating
                              ? "text-purple-300 bg-accent-violet/10 cursor-wait animate-pulse"
                              : "text-text-secondary hover:text-purple-300 hover:bg-accent-violet/10"
                          }`}
                        >
                          <span className="text-xs shrink-0">✨</span>
                          <span>{isGenerating ? "Generating title..." : "Auto-generate title"}</span>
                        </button>
                      )}

                      {/* Visual separator before destructive action */}
                      {onDeleteChat && <div className="my-1 border-t border-border-subtle" />}

                      {/* Delete conversation action */}
                      {onDeleteChat && (
                        <button
                          type="button"
                          role="menuitem"
                          onClick={handleDelete}
                          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-medium text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors text-left"
                        >
                          <svg className="w-3.5 h-3.5 text-red-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                          <span>Delete conversation</span>
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
});

export default ChatHeader;

