"use client";

/**
 * ChatSidebar.tsx — Collapsible conversation history menu for the Nexus Chat interface.
 * Renders either a compact 14-unit icon rail or a full 64-unit drawer with quick model preset buttons
 * and inline conversation title renaming.
 */

import { useState, useRef } from "react";
import type { Conversation, ModelOption } from "@/lib/api";

// ChatSidebarProps: defines data and callbacks required by the conversation history sidebar
// - conversations: array of persisted Conversation records fetched from SQLite chats.db
// - activeConvId: UUID of the currently selected conversation thread (or null for a fresh draft)
// - isCollapsed: boolean controlling whether the sidebar renders as a slim rail (w-14) or full drawer (w-64)
// - modelOptions: available LLM tiers returned by GET /api/agents/models
// - selectedModelTier: currently selected model tier ID ("strong", "medium", "low")
// - onToggleCollapse: callback invoked to expand or collapse the conversation history panel
// - onSelectConversation: callback invoked when the user clicks a conversation row
// - onNewChat: callback to start a blank conversation, optionally pre-selecting a model tier
// - onDeleteChat: callback to delete a conversation thread without triggering row selection
// - onUpdateTitle: optional callback invoked when the user saves an edited conversation title
export interface ChatSidebarProps {
  conversations: Conversation[];
  activeConvId: string | null;
  isCollapsed: boolean;
  modelOptions: ModelOption[];
  selectedModelTier: string;
  onToggleCollapse: (collapsed: boolean) => void;
  onSelectConversation: (id: string) => void;
  onNewChat: (initialTier?: string) => void;
  onDeleteChat: (id: string, e: React.MouseEvent) => void;
  onUpdateTitle?: (id: string, newTitle: string) => void;
}

export default function ChatSidebar({
  conversations,
  activeConvId,
  isCollapsed,
  modelOptions,
  selectedModelTier,
  onToggleCollapse,
  onSelectConversation,
  onNewChat,
  onDeleteChat,
  onUpdateTitle,
}: ChatSidebarProps) {
  // editingId: tracks which conversation UUID is currently in inline title editing mode (or null if none)
  const [editingId, setEditingId] = useState<string | null>(null);
  // editTitle: holds the draft title string being actively typed in the rename input
  const [editTitle, setEditTitle] = useState<string>("");
  // editInputRef: HTMLInputElement reference used to auto-focus and auto-select existing title text on mount
  const editInputRef = useRef<HTMLInputElement>(null);

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
  if (isCollapsed) {
    // Collapsed Rail: Slim column with expand button, new chat icon, and conversation switcher
    return (
      <aside
        className="w-14 border-r border-border-subtle bg-bg-secondary flex flex-col items-center py-4 shrink-0 transition-all duration-300 ease-in-out select-none"
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
          className="mt-3 w-9 h-9 rounded-xl bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors flex items-center justify-center text-lg font-bold"
          title="Start New Chat"
          aria-label="Start New Chat"
        >
          +
        </button>

        {/* Conversation history icons for fast switching */}
        <div className="mt-4 flex-1 overflow-y-auto space-y-1.5 w-full px-2 flex flex-col items-center">
          {conversations.map((conv) => (
            <button
              key={conv.id}
              onClick={() => onSelectConversation(conv.id)}
              className={`w-9 h-9 rounded-lg flex items-center justify-center text-xs transition-all ${activeConvId === conv.id
                ? "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40 shadow-[0_0_10px_rgba(56,189,248,0.15)] font-bold"
                : "text-text-muted hover:text-text-primary hover:bg-bg-tertiary"
                }`}
              title={conv.title}
            >
              💬
            </button>
          ))}
        </div>
      </aside>
    );
  }

  // Expanded Conversation Menu: Full titles, model preset buttons, and delete actions
  return (
    <aside
      className="w-64 border-r border-border-subtle bg-bg-secondary flex flex-col shrink-0 transition-all duration-300 ease-in-out"
      aria-label="Conversations Menu"
    >
      <div className="p-4 border-b border-border-subtle space-y-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => onNewChat()}
            className="flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-xl bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors text-sm font-medium"
          >
            <span className="text-lg">+</span> New Chat
          </button>
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
                onClick={() => onNewChat(opt.id)}
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
                  className="flex-1 min-w-0 bg-bg-primary/90 border border-border-subtle rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-accent-cyan"
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

          return (
            <div
              key={conv.id}
              onClick={() => onSelectConversation(conv.id)}
              onDoubleClick={(e) => {
                e.stopPropagation();
                handleStartEdit(conv);
              }}
              className={`group flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer text-sm transition-colors ${activeConvId === conv.id
                ? "bg-bg-tertiary text-text-primary"
                : "text-text-secondary hover:bg-bg-tertiary/50"
                }`}
              title={`${conv.title} (double-click or hover pencil to rename)`}
            >
              <div className="flex flex-col overflow-hidden min-w-0 mr-1.5">
                <span className="truncate font-medium">{conv.title}</span>
              </div>
              <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                <button
                  type="button"
                  onClick={(e) => handleStartEdit(conv, e)}
                  className="p-1 text-text-muted hover:text-accent-cyan hover:bg-bg-secondary rounded transition-colors"
                  title="Rename Chat"
                  aria-label="Rename Chat"
                >
                  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={(e) => onDeleteChat(conv.id, e)}
                  className="p-1 text-text-muted hover:text-red-400 hover:bg-bg-secondary rounded transition-colors"
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
    </aside>
  );
}

