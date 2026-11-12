"use client";

/**
 * ChatSidebar.tsx — Collapsible conversation history menu for the Nexus Chat interface.
 * Renders either a compact 14-unit icon rail or a full 64-unit drawer with quick model preset buttons
 * and nested branch tree views. (Conversation actions are folded into the header three-dots menu).
 */

// memo: Isolates the conversation history sidebar from re-rendering during keystroke updates in the composer
import { useState, useRef, useEffect, useMemo, memo } from "react";
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
// - activeRunConvIds: optional array of conversation UUIDs currently executing an agent turn in the background
// - onToggleCollapse: callback invoked to expand or collapse the desktop conversation history panel
// - onCloseMobile: optional callback invoked to close the mobile slide-over drawer
// - onSelectConversation: callback invoked when the user clicks a conversation row
// - onNewChat: callback to start a blank conversation, optionally pre-selecting a model tier
export interface ChatSidebarProps {
  conversations: Conversation[];
  activeConvId: string | null;
  isCollapsed: boolean;
  isMobileOpen?: boolean;
  modelOptions: ModelOption[];
  selectedModelTier: string;
  drafts?: Record<string, string>;
  activeRunConvIds?: string[];
  onToggleCollapse: (collapsed: boolean) => void;
  onCloseMobile?: () => void;
  onSelectConversation: (id: string) => void;
  onNewChat: (initialTier?: string) => void;
}

const ChatSidebar = memo(function ChatSidebar({
  conversations,
  activeConvId,
  isCollapsed,
  isMobileOpen = false,
  modelOptions,
  selectedModelTier,
  drafts,
  activeRunConvIds,
  onToggleCollapse,
  onCloseMobile,
  onSelectConversation,
  onNewChat,
}: ChatSidebarProps) {
  // collapsedParentIds: tracks which parent conversation UUIDs have their child branch trees collapsed in the sidebar
  const [collapsedParentIds, setCollapsedParentIds] = useState<Record<string, boolean>>({});
  // activeRunSet: O(1) lookup set of conversation UUIDs currently executing in the background
  const activeRunSet = useMemo(() => new Set(activeRunConvIds ?? []), [activeRunConvIds]);

  // Flattens `conversations` into a depth-annotated tree list so child branches render nested beneath their parent
  const treeRows = useMemo(() => {
    const idSet = new Set(conversations.map((c) => c.id));
    const childrenMap = new Map<string, Conversation[]>();
    const roots: Conversation[] = [];

    for (const c of conversations) {
      if (c.parent_conversation_id && idSet.has(c.parent_conversation_id)) {
        const list = childrenMap.get(c.parent_conversation_id) ?? [];
        list.push(c);
        childrenMap.set(c.parent_conversation_id, list);
      } else {
        roots.push(c);
      }
    }

    const result: Array<{ conv: Conversation; depth: number; childCount: number; isBranchCollapsed: boolean }> = [];
    const visit = (node: Conversation, depth: number) => {
      const kids = childrenMap.get(node.id) ?? [];
      const isBranchCollapsed = Boolean(collapsedParentIds[node.id]);
      result.push({ conv: node, depth, childCount: kids.length, isBranchCollapsed });
      if (!isBranchCollapsed) {
        // Render child branches in chronological/recent order beneath the parent
        for (const child of kids) {
          visit(child, depth + 1);
        }
      }
    };

    for (const root of roots) {
      visit(root, 0);
    }
    return result;
  }, [conversations, collapsedParentIds]);

  const toggleParentBranches = (parentId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setCollapsedParentIds((prev) => ({ ...prev, [parentId]: !prev[parentId] }));
  };

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
        {treeRows.map(({ conv, depth, childCount, isBranchCollapsed }) => {
          const hasDraft = Boolean(drafts?.[conv.id]?.trim());
          const isRunning = activeRunSet.has(conv.id);

          return (
            <div
              key={conv.id}
              style={depth > 0 ? { marginLeft: `${Math.min(depth * 14, 42)}px` } : undefined}
              onClick={() => {
                onSelectConversation(conv.id);
                if (isMobileDrawer) onCloseMobile?.();
              }}
              className={`group relative flex items-center px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors overflow-hidden ${
                depth > 0 ? "border-l-2 border-emerald-500/30 pl-2.5 text-xs " : ""
              }${
                activeConvId === conv.id
                  ? "bg-bg-tertiary text-text-primary"
                  : "text-text-secondary hover:bg-bg-tertiary/50"
              }`}
              title={`${conv.title}${isRunning ? " (Agent running)" : ""}${conv.merged_at ? " (Merged to parent)" : ""}${hasDraft ? " (Draft saved)" : ""}`}
            >
              {/* Conversation title: takes full available row width without reserved sibling space; truncates with ellipsis */}
              <div className="flex-1 min-w-0 pr-1 flex flex-col justify-center">
                <div className="flex items-center gap-1.5 min-w-0">
                  {childCount > 0 && (
                    <button
                      type="button"
                      onClick={(e) => toggleParentBranches(conv.id, e)}
                      title={isBranchCollapsed ? `Expand ${childCount} branch(es)` : `Collapse ${childCount} branch(es)`}
                      className="shrink-0 text-[0.65rem] text-emerald-400 hover:text-emerald-300 font-mono px-0.5 rounded hover:bg-bg-primary/60"
                    >
                      {isBranchCollapsed ? `▸${childCount}` : "▾"}
                    </button>
                  )}
                  {isRunning && (
                    <span
                      className="w-2 h-2 rounded-full bg-accent-cyan animate-pulse shrink-0"
                      title="Agent executing in background"
                    />
                  )}
                  <span className="truncate font-medium">{conv.title}</span>
                  {conv.merged_at && (
                    <span
                      className="shrink-0 text-[0.6rem] px-1 py-0.2 rounded bg-emerald-500/15 text-emerald-300 font-mono border border-emerald-500/30"
                      title="Distilled & merged into parent conversation"
                    >
                      ✓
                    </span>
                  )}
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
              const isRunning = activeRunSet.has(conv.id);
              return (
                <button
                  key={conv.id}
                  onClick={() => onSelectConversation(conv.id)}
                  className={`relative w-9 h-9 rounded-lg flex items-center justify-center text-xs transition-all ${activeConvId === conv.id
                    ? "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40 shadow-[0_0_10px_rgba(56,189,248,0.15)] font-bold"
                    : "text-text-muted hover:text-text-primary hover:bg-bg-tertiary"
                    }`}
                  title={`${conv.title}${isRunning ? " (Agent running)" : ""}${hasDraft ? " (Draft saved)" : ""}`}
                >
                  💬
                  {isRunning ? (
                    <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-accent-cyan animate-pulse border border-bg-secondary" />
                  ) : hasDraft ? (
                    <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-accent-cyan border border-bg-secondary" />
                  ) : null}
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

