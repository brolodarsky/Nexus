"use client";

/**
 * ChatSidebar.tsx — Collapsible conversation history menu for the Nexus Chat interface.
 * Renders either a compact 14-unit icon rail or a full 64-unit drawer with quick model preset buttons
 * and inline conversation title renaming.
 */

// memo: Isolates the conversation history sidebar from re-rendering during keystroke updates in the composer
import { useState, useRef, useEffect, memo } from "react";
import type { Conversation, ModelOption } from "@/lib/api";
import {
  CHAT_SIDEBAR_WIDTH_KEY,
  DEFAULT_CHAT_SIDEBAR_WIDTH,
  MIN_CHAT_SIDEBAR_WIDTH,
  MAX_CHAT_SIDEBAR_WIDTH,
  DRAFT_NEW_KEY,
} from "./types";

// ChatSidebarProps: defines data and callbacks required by the conversation history sidebar
// - conversations: array of persisted Conversation records fetched from SQLite chats.db
// - activeConvId: UUID of the currently selected conversation thread (or null for a fresh draft)
// - isCollapsed: boolean controlling whether the desktop sidebar renders as a slim rail (w-14) or full drawer (w-64)
// - isMobileOpen: optional boolean controlling whether the mobile (< 768px) slide-over overlay drawer is open
// - modelOptions: available LLM tiers returned by GET /api/agents/models
// - selectedModelTier: currently selected model tier ID ("strong", "medium", "low")
// - drafts: optional dictionary mapping conversation IDs (and DRAFT_NEW_KEY) to unsubmitted prompt drafts
// - onToggleCollapse: callback invoked to expand or collapse the desktop conversation history panel
// - onCloseMobile: optional callback invoked to close the mobile slide-over drawer
// - onSelectConversation: callback invoked when the user clicks a conversation row
// - onNewChat: callback to start a blank conversation, optionally pre-selecting a model tier
// - onDeleteChat: callback to delete a conversation thread without triggering row selection
// - onUpdateTitle: optional callback invoked when the user saves an edited conversation title
// - onAutoGenerateTitle: optional async callback to auto-generate a smart AI title for a conversation
export interface ChatSidebarProps {
  conversations: Conversation[];
  activeConvId: string | null;
  isCollapsed: boolean;
  isMobileOpen?: boolean;
  modelOptions: ModelOption[];
  selectedModelTier: string;
  drafts?: Record<string, string>;
  onToggleCollapse: (collapsed: boolean) => void;
  onCloseMobile?: () => void;
  onSelectConversation: (id: string) => void;
  onNewChat: (initialTier?: string) => void;
  onDeleteChat: (id: string, e: React.MouseEvent) => void;
  onUpdateTitle?: (id: string, newTitle: string) => void;
  onAutoGenerateTitle?: (id: string) => Promise<void> | void;
}

const ChatSidebar = memo(function ChatSidebar({
  conversations,
  activeConvId,
  isCollapsed,
  isMobileOpen = false,
  modelOptions,
  selectedModelTier,
  drafts,
  onToggleCollapse,
  onCloseMobile,
  onSelectConversation,
  onNewChat,
  onDeleteChat,
  onUpdateTitle,
  onAutoGenerateTitle,
}: ChatSidebarProps) {
  // editingId: tracks which conversation UUID is currently in inline title editing mode (or null if none)
  const [editingId, setEditingId] = useState<string | null>(null);
  // generatingId: tracks which conversation UUID is currently having an AI title generated
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  // editTitle: holds the draft title string being actively typed in the rename input
  const [editTitle, setEditTitle] = useState<string>("");
  // editInputRef: HTMLInputElement reference used to auto-focus and auto-select existing title text on mount
  const editInputRef = useRef<HTMLInputElement>(null);

  // sidebarWidth: custom width in pixels for the expanded conversation sidebar drawer
  const [sidebarWidth, setSidebarWidth] = useState<number>(DEFAULT_CHAT_SIDEBAR_WIDTH);
  // isResizing: boolean flag tracking whether the user is actively dragging the right border handle
  const [isResizing, setIsResizing] = useState<boolean>(false);
  // sidebarRef: DOM reference to the aside element to compute accurate relative mouse drag coordinates
  const sidebarRef = useRef<HTMLElement>(null);

  // Restore persisted sidebar width from localStorage on mount (survives tab switches and reloads)
  useEffect(() => {
    try {
      const saved = localStorage.getItem(CHAT_SIDEBAR_WIDTH_KEY);
      if (saved) {
        const parsed = parseInt(saved, 10);
        if (!isNaN(parsed) && parsed >= MIN_CHAT_SIDEBAR_WIDTH && parsed <= MAX_CHAT_SIDEBAR_WIDTH) {
          setSidebarWidth(parsed);
        }
      }
    } catch {
      // Gracefully ignore storage quota / access errors in private browsing contexts
    }
  }, []);

  // Handle pointer down on the resize handle: initiates dragging and binds global window pointer listeners
  const handleResizeStart = (e: React.PointerEvent) => {
    e.preventDefault();
    setIsResizing(true);

    const handlePointerMove = (moveEvent: PointerEvent) => {
      if (!sidebarRef.current) return;
      // getBoundingClientRect().left gives the exact screen coordinate where the sidebar starts,
      // correctly accounting for the main global Nexus navigation rail to the left of the page
      const rect = sidebarRef.current.getBoundingClientRect();
      const newWidth = moveEvent.clientX - rect.left;
      const maxAllowed = Math.min(MAX_CHAT_SIDEBAR_WIDTH, window.innerWidth - 320);
      const clamped = Math.max(MIN_CHAT_SIDEBAR_WIDTH, Math.min(maxAllowed, newWidth));
      setSidebarWidth(clamped);
    };

    const handlePointerUp = (upEvent: PointerEvent) => {
      setIsResizing(false);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);

      if (sidebarRef.current) {
        const rect = sidebarRef.current.getBoundingClientRect();
        const newWidth = upEvent.clientX - rect.left;
        const maxAllowed = Math.min(MAX_CHAT_SIDEBAR_WIDTH, window.innerWidth - 320);
        const clamped = Math.max(MIN_CHAT_SIDEBAR_WIDTH, Math.min(maxAllowed, newWidth));
        try {
          localStorage.setItem(CHAT_SIDEBAR_WIDTH_KEY, String(clamped));
        } catch {
          // Gracefully ignore storage quota / access errors in private browsing contexts
        }
      }
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
  };

  // Reset sidebar width to default on double-clicking the resize handle
  const handleResetWidth = () => {
    setSidebarWidth(DEFAULT_CHAT_SIDEBAR_WIDTH);
    try {
      localStorage.setItem(CHAT_SIDEBAR_WIDTH_KEY, String(DEFAULT_CHAT_SIDEBAR_WIDTH));
    } catch {
      // Gracefully ignore storage quota / access errors
    }
  };

  // Prevent text selection and maintain col-resize cursor on document body during active dragging
  useEffect(() => {
    if (isResizing) {
      document.body.style.userSelect = "none";
      document.body.style.cursor = "col-resize";
      return () => {
        document.body.style.userSelect = "";
        document.body.style.cursor = "";
      };
    }
  }, [isResizing]);

  // Initiates inline rename mode for a specific conversation row
  const handleStartEdit = (conv: Conversation, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setEditingId(conv.id);
    setEditTitle(conv.title);
    queueMicrotask(() => {
      editInputRef.current?.focus();
      editInputRef.current?.select();
    });
  };

  // Cancels inline edit mode and clears transient draft title
  const handleCancelEdit = () => {
    setEditingId(null);
    setEditTitle("");
  };

  // Commits the updated title to the parent orchestrator and exits edit mode
  const handleSaveEdit = (id: string) => {
    const trimmed = editTitle.trim();
    if (trimmed && onUpdateTitle) {
      onUpdateTitle(id, trimmed);
    }
    handleCancelEdit();
  };
  const hasNewChatDraft = Boolean(drafts?.[DRAFT_NEW_KEY]?.trim());

  // Helper to render the expanded drawer body (shared between desktop expanded `<aside>` and mobile slide-over overlay)
  // - isMobileDrawer: boolean indicating whether the drawer is rendered inside the mobile (< 768px) overlay
  const renderExpandedContent = (isMobileDrawer: boolean) => (
    <>
      <div className="p-4 border-b border-border-subtle space-y-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              onNewChat();
              if (isMobileDrawer) onCloseMobile?.();
            }}
            className="flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-xl bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors text-sm font-medium"
          >
            <span className="text-lg">+</span>
            <span>New Chat</span>
            {hasNewChatDraft && (
              <span
                className="text-[0.62rem] px-1.5 py-0.5 rounded bg-accent-cyan/15 text-accent-cyan font-mono border border-accent-cyan/30 uppercase tracking-wider font-semibold"
                title="Unsubmitted new chat draft saved"
              >
                Draft
              </span>
            )}
          </button>
          {isMobileDrawer ? (
            <button
              onClick={() => onCloseMobile?.()}
              className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors shrink-0"
              title="Close conversations drawer"
              aria-label="Close conversations drawer"
            >
              ✕
            </button>
          ) : (
            <button
              onClick={() => onToggleCollapse(true)}
              className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors shrink-0"
              title="Collapse"
              aria-label="Collapse chat history menu"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              </svg>
            </button>
          )}
        </div>

        {/* Quick New Chat Model Preset Buttons (2-column grid for Gemini & Anthropic Strong/Fast presets) */}
        <div className="grid grid-cols-2 gap-1.5">
          {modelOptions.map((opt) => {
            const isSelected = selectedModelTier === opt.id;
            const isStrong = opt.tier === "strong";
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => {
                  onNewChat(opt.id);
                  if (isMobileDrawer) onCloseMobile?.();
                }}
                title={`Open new chat with ${opt.description}`}
                className={`py-1 px-2 rounded-lg text-[0.68rem] font-medium border transition-all flex items-center justify-center gap-1 ${isSelected
                  ? isStrong
                    ? "bg-accent-violet/15 border-accent-violet/40 text-purple-300"
                    : "bg-accent-cyan/15 border-accent-cyan/40 text-accent-cyan"
                  : "bg-bg-tertiary/50 border-border-subtle text-text-muted hover:text-text-secondary"
                  }`}
              >
                <span>{isStrong ? "🧠" : opt.tier === "medium" ? "⚖️" : "⚡"}</span>
                <span className="truncate">{opt.short_label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {conversations.map((conv) => {
          const isEditing = editingId === conv.id;
          if (isEditing) {
            // Inline Rename Input Form: Allows editing the conversation title with Enter to commit, Escape to cancel
            return (
              <div
                key={conv.id}
                className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-bg-tertiary border border-accent-cyan/40 shadow-sm"
                onClick={(e) => e.stopPropagation()}
              >
                <input
                  ref={editInputRef}
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleSaveEdit(conv.id);
                    } else if (e.key === "Escape") {
                      e.preventDefault();
                      handleCancelEdit();
                    }
                  }}
                  className="flex-1 min-w-0 bg-bg-primary/90 border border-border-subtle rounded px-2 py-1 text-base md:text-xs text-text-primary focus:outline-none focus:border-accent-cyan"
                  placeholder="Chat title..."
                />
                <button
                  type="button"
                  onClick={() => handleSaveEdit(conv.id)}
                  className="p-1 rounded text-accent-cyan hover:bg-accent-cyan/20 transition-colors text-xs font-bold"
                  title="Save title (Enter)"
                  aria-label="Save title"
                >
                  ✓
                </button>
                <button
                  type="button"
                  onClick={handleCancelEdit}
                  className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-secondary transition-colors text-xs"
                  title="Cancel (Esc)"
                  aria-label="Cancel editing title"
                >
                  ✕
                </button>
              </div>
            );
          }

          const hasDraft = Boolean(drafts?.[conv.id]?.trim());

          return (
            <div
              key={conv.id}
              onClick={() => {
                onSelectConversation(conv.id);
                if (isMobileDrawer) onCloseMobile?.();
              }}
              onDoubleClick={(e) => {
                e.stopPropagation();
                handleStartEdit(conv);
              }}
              className={`group relative flex items-center px-3 py-2.5 rounded-lg cursor-pointer text-sm transition-colors overflow-hidden ${
                activeConvId === conv.id
                  ? "bg-bg-tertiary text-text-primary"
                  : "text-text-secondary hover:bg-bg-tertiary/50"
              }`}
              title={`${conv.title}${hasDraft ? " (Draft saved)" : ""} (double-click or hover pencil to rename)`}
            >
              {/* Conversation title: takes full available row width without reserved sibling space; truncates with ellipsis */}
              <div className="flex-1 min-w-0 pr-1 flex flex-col justify-center">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="truncate font-medium">{conv.title}</span>
                  {hasDraft && (
                    <span
                      className="shrink-0 text-[0.62rem] px-1.5 py-0.5 rounded bg-accent-cyan/15 text-accent-cyan font-mono border border-accent-cyan/30 uppercase tracking-wider font-semibold"
                      title="Unsubmitted draft saved"
                    >
                      Draft
                    </span>
                  )}
                </div>
              </div>

              {/* Hover Actions: Floats over the right end on hover on desktop (or stays accessible on mobile drawer) */}
              <div
                className={`absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-0.5 ${
                  isMobileDrawer ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                } transition-opacity rounded-md px-1 py-0.5 z-10 ${
                  activeConvId === conv.id
                    ? "bg-bg-secondary/95 border border-border-subtle shadow-md"
                    : "bg-bg-secondary/95 backdrop-blur-sm border border-border-subtle shadow-md"
                }`}
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={(e) => handleStartEdit(conv, e)}
                  className="p-1 text-text-muted hover:text-accent-cyan hover:bg-bg-tertiary rounded transition-colors"
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
                    disabled={generatingId === conv.id}
                    onClick={async (e) => {
                      e.stopPropagation();
                      setGeneratingId(conv.id);
                      try {
                        await onAutoGenerateTitle(conv.id);
                      } finally {
                        setGeneratingId(null);
                      }
                    }}
                    className={`p-1 text-text-muted hover:text-accent-violet hover:bg-bg-tertiary rounded transition-colors text-xs ${
                      generatingId === conv.id ? "animate-pulse text-accent-violet" : ""
                    }`}
                    title="Auto-generate title with AI"
                    aria-label="Auto-generate title with AI"
                  >
                    ✨
                  </button>
                )}
                <button
                  type="button"
                  onClick={(e) => onDeleteChat(conv.id, e)}
                  className="p-1 text-text-muted hover:text-red-400 hover:bg-bg-tertiary rounded transition-colors"
                  title="Delete Chat"
                  aria-label="Delete Chat"
                >
                  ✕
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );

  return (
    <>
      {/* ── Desktop Persistent Conversation Sidebar (`md:` and up) ───────── */}
      {isCollapsed ? (
        // Collapsed Rail: Slim column with expand button, new chat icon, and conversation switcher
        <aside
          className="hidden md:flex w-14 border-r border-border-subtle bg-bg-secondary flex-col items-center py-4 shrink-0 transition-all duration-300 ease-in-out select-none"
          aria-label="Collapsed Conversations Menu"
        >
          <button
            onClick={() => onToggleCollapse(false)}
            className="p-2 rounded-lg text-text-muted hover:text-accent-cyan hover:bg-bg-tertiary transition-colors flex items-center justify-center"
            title="Expand"
            aria-label="Expand chat history menu"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            </svg>
          </button>

          {/* Compact New Chat Action */}
          <button
            onClick={() => onNewChat()}
            className="relative mt-3 w-9 h-9 rounded-xl bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors flex items-center justify-center text-lg font-bold"
            title={`Start New Chat${hasNewChatDraft ? " (Draft saved)" : ""}`}
            aria-label="Start New Chat"
          >
            +
            {hasNewChatDraft && (
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-accent-cyan border border-bg-secondary" />
            )}
          </button>

          {/* Conversation history icons for fast switching */}
          <div className="mt-4 flex-1 overflow-y-auto space-y-1.5 w-full px-2 flex flex-col items-center">
            {conversations.map((conv) => {
              const hasDraft = Boolean(drafts?.[conv.id]?.trim());
              return (
                <button
                  key={conv.id}
                  onClick={() => onSelectConversation(conv.id)}
                  className={`relative w-9 h-9 rounded-lg flex items-center justify-center text-xs transition-all ${activeConvId === conv.id
                    ? "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40 shadow-[0_0_10px_rgba(56,189,248,0.15)] font-bold"
                    : "text-text-muted hover:text-text-primary hover:bg-bg-tertiary"
                    }`}
                  title={`${conv.title}${hasDraft ? " (Draft saved)" : ""}`}
                >
                  💬
                  {hasDraft && (
                    <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-accent-cyan border border-bg-secondary" />
                  )}
                </button>
              );
            })}
          </div>
        </aside>
      ) : (
        // Expanded Conversation Menu: Full titles, model preset buttons, resizable border handle, and delete actions
        <aside
          ref={sidebarRef}
          style={{ width: `${sidebarWidth}px` }}
          className={`hidden md:flex relative border-r border-border-subtle bg-bg-secondary flex-col shrink-0 ${
            isResizing ? "select-none transition-none" : "transition-[width] duration-300 ease-in-out"
          }`}
          aria-label="Conversations Menu"
        >
          {/* Draggable Resize Handle: Sits along the right border to allow smooth mouse dragging */}
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize conversations menu"
            tabIndex={0}
            onPointerDown={handleResizeStart}
            onDoubleClick={handleResetWidth}
            className={`absolute top-0 -right-1 w-2 h-full cursor-col-resize z-20 transition-colors ${
              isResizing ? "bg-accent-cyan" : "hover:bg-accent-cyan/60 active:bg-accent-cyan"
            }`}
            title="Drag to resize sidebar (double-click to reset width)"
          />
          {renderExpandedContent(false)}
        </aside>
      )}

      {/* ── Mobile Slide-Over Overlay Drawer (`< 768px` / `md:hidden`) ─────── */}
      {isMobileOpen && (
        <div className="md:hidden fixed inset-0 bottom-16 z-40 flex">
          {/* Translucent Backdrop: Tapping anywhere outside the drawer closes it */}
          <div
            className="fixed inset-0 bottom-16 bg-black/60 backdrop-blur-xs"
            onClick={() => onCloseMobile?.()}
            aria-hidden="true"
          />
          <aside
            className="relative z-10 w-72 max-w-[85vw] h-full border-r border-border-subtle bg-bg-secondary flex flex-col shadow-2xl"
            aria-label="Mobile Conversations Drawer"
          >
            {renderExpandedContent(true)}
          </aside>
        </div>
      )}
    </>
  );
});

export default ChatSidebar;

