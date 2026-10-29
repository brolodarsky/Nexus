"use client";

/**
 * ChatSidebar.tsx — Collapsible conversation history menu for the Nexus Chat interface.
 * Renders either a compact 14-unit icon rail or a full 64-unit drawer with quick model preset buttons.
 */

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
}: ChatSidebarProps) {
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
          title="Expand chat history"
          aria-label="Expand chat history"
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
              className={`w-9 h-9 rounded-lg flex items-center justify-center text-xs transition-all ${
                activeConvId === conv.id
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
            title="Collapse chat history"
            aria-label="Collapse chat history"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          </button>
        </div>

        {/* Quick New Chat Model Preset Buttons (Strong vs. Fast/Low-Cost opening) */}
        <div className="flex items-center gap-1.5">
          {modelOptions.map((opt) => {
            const isSelected = selectedModelTier === opt.id;
            const isStrong = opt.tier === "strong";
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => onNewChat(opt.id)}
                title={`Open new chat with ${opt.description}`}
                className={`flex-1 py-1 px-2 rounded-lg text-[0.68rem] font-medium border transition-all flex items-center justify-center gap-1 ${
                  isSelected
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
        {conversations.map((conv) => (
          <div
            key={conv.id}
            onClick={() => onSelectConversation(conv.id)}
            className={`group flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer text-sm transition-colors ${
              activeConvId === conv.id
                ? "bg-bg-tertiary text-text-primary"
                : "text-text-secondary hover:bg-bg-tertiary/50"
            }`}
          >
            <div className="flex flex-col overflow-hidden">
              <span className="truncate font-medium">{conv.title}</span>
            </div>
            <button
              onClick={(e) => onDeleteChat(conv.id, e)}
              className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-red-400 transition-opacity"
              title="Delete Chat"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}

