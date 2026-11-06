"use client";

/**
 * ChatMessageThread.tsx — Scrollable message feed for the Nexus Chat workspace.
 * Manages automatic bottom-scrolling, empty-state starter prompts, message bubbles,
 * and the live streaming `ThinkingPanel` indicator.
 */

// memo: Isolates the scrollable message feed from sibling/parent state updates (e.g., input typing or sidebar toggles)
import { useRef, useEffect, memo } from "react";
import { ThinkingPanel } from "@/components/AgentTraceVisualizer";
import type { TraceEvent } from "@/lib/api";
import type { Message } from "./types";
import ChatMessageItem from "./ChatMessageItem";

// Starter prompt suggestions displayed when a conversation has no messages yet
const PROMPT_SUGGESTIONS: string[] = [
  "What do we got for today?",
  "Do an email sweep.",
  "What are my outstanding Missions?",
];

// ChatMessageThreadProps: defines the state and callbacks needed to render the message stream
// - messages: ordered list of user and assistant Message objects in the active conversation
// - loading: boolean indicating whether an SSE agent response stream is currently in-flight
// - liveTrace: array of real-time TraceEvent payloads emitted during the active streaming turn
// - activeModelLabel: human-readable label of the selected model tier shown in the live status indicator
// - onSelectPromptSuggestion: callback to populate the chat input when a user clicks an example prompt
// - onStopAndRevert: optional callback to immediately abort execution and revert the active turn
// - onRevertLastTurn: optional callback to revert the most recent completed turn
export interface ChatMessageThreadProps {
  messages: Message[];
  loading: boolean;
  liveTrace: TraceEvent[];
  activeModelLabel: string;
  onSelectPromptSuggestion: (suggestion: string) => void;
  onStopAndRevert?: () => void;
  onRevertLastTurn?: () => void;
}

const ChatMessageThread = memo(function ChatMessageThread({
  messages,
  loading,
  liveTrace,
  activeModelLabel,
  onSelectPromptSuggestion,
  onStopAndRevert,
  onRevertLastTurn,
}: ChatMessageThreadProps) {
  // scrollRef: DOM reference to the scrollable thread container for automatic bottom-pinning
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom whenever new messages arrive or live trace steps stream in
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, liveTrace]);

  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto px-4 md:px-8 py-4 md:py-6 space-y-5"
    >
      {/* Empty state starter screen */}
      {messages.length === 0 && !loading && (
        <div className="flex flex-col items-center justify-center h-full text-center opacity-60">
          <span className="text-5xl mb-4">🧠</span>
          <p className="text-text-secondary text-sm max-w-md">
            How can I help today?
          </p>
          <div className="flex flex-wrap gap-2 mt-6 justify-center">
            {PROMPT_SUGGESTIONS.map((example) => (
              <button
                key={example}
                onClick={() => onSelectPromptSuggestion(example)}
                className="glass-card px-4 py-2 text-xs text-text-secondary hover:text-accent-cyan transition-colors"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Historical & current session message bubbles */}
      {messages.map((msg, i) => (
        <ChatMessageItem
          key={i}
          message={msg}
          isLastTurn={i === messages.length - 1}
          onRevertTurn={onRevertLastTurn}
        />
      ))}

      {/* Live thinking panel while streaming (collapsed by default to prevent visual jumpiness during live token delivery) */}
      {loading && (
        <div className="flex justify-start">
          <div className="glass-card px-5 py-3.5 text-sm text-text-secondary max-w-4xl xl:max-w-5xl w-full">
            <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
              <span className="inline-flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-pulse" />
                <span
                  className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-pulse"
                  style={{ animationDelay: "0.2s" }}
                />
                <span
                  className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-pulse"
                  style={{ animationDelay: "0.4s" }}
                />
                <span className="ml-2">
                  Routing query with{" "}
                  <span className="font-mono text-text-primary">
                    {activeModelLabel}
                  </span>
                  …
                </span>
              </span>

              {onStopAndRevert && (
                <button
                  type="button"
                  onClick={onStopAndRevert}
                  title="Stop agent run and revert turn (Esc)"
                  aria-label="Stop and revert turn"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-rose-500/15 text-rose-400 hover:bg-rose-500/25 border border-rose-500/30 transition-all shadow-sm shrink-0 hover:scale-[1.02] active:scale-[0.98]"
                >
                  <svg className="w-3 h-3 fill-current" viewBox="0 0 24 24">
                    <rect x="5" y="5" width="14" height="14" rx="2" />
                  </svg>
                  <span>Stop &amp; Revert</span>
                </button>
              )}
            </div>
            <ThinkingPanel
              events={liveTrace}
              isLive={true}
              defaultExpanded={false}
            />
          </div>
        </div>
      )}
    </div>
  );
});

export default ChatMessageThread;

