"use client";

/**
 * ChatHeader.tsx — Top header bar for the Nexus Chat workspace.
 * Displays the active conversation title, orchestrator subtitle, and Shared Blackboard toggle button.
 */

// ChatHeaderProps: defines the display state and toggle callback for the Chat workspace header
// - title: active conversation title (falls back to "Chat" when starting a fresh session)
// - showBoard: boolean indicating whether the right-hand Subagent Blackboard drawer is open
// - bulletinCount: number of active bulletins currently on the Blackboard
// - onToggleBoard: callback invoked when the user clicks the Subagent Board toggle button
export interface ChatHeaderProps {
  title?: string;
  showBoard: boolean;
  bulletinCount: number;
  onToggleBoard: () => void;
}

export default function ChatHeader({
  title,
  showBoard,
  bulletinCount,
  onToggleBoard,
}: ChatHeaderProps) {
  return (
    <header className="px-8 py-4 border-b border-border-subtle shrink-0 flex items-center justify-between">
      <div>
        <h1 className="text-xl font-bold tracking-tight">
          <span className="gradient-text">{title || "Chat"}</span>
        </h1>
      </div>
      <div className="flex items-center gap-2">
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

