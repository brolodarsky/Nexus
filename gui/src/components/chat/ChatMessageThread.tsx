"use client";

/**
 * ChatMessageThread.tsx — Scrollable message feed for the Nexus Chat workspace.
 * Manages automatic bottom-scrolling, empty-state starter prompts, message bubbles,
 * and the live streaming `ThinkingPanel` indicator.
 */

import { useRef, useEffect } from "react";
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
export interface ChatMessageThreadProps {
  messages: Message[];
  loading: boolean;
  liveTrace: TraceEvent[];
  activeModelLabel: string;
  onSelectPromptSuggestion: (suggestion: string) => void;
}

export default function ChatMessageThread({
  messages,
  loading,
  liveTrace,
  activeModelLabel,
  onSelectPromptSuggestion,
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
      className="flex-1 overflow-y-auto px-8 py-6 space-y-5"
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
        <ChatMessageItem key={i} message={msg} />
      ))}

      {/* Live thinking panel while streaming */}
      {loading && (
        <div className="flex justify-start">
          <div className="glass-card px-5 py-3.5 text-sm text-text-secondary max-w-4xl xl:max-w-5xl w-full">
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
            <ThinkingPanel
              events={liveTrace}
              isLive={true}
              defaultExpanded={true}
            />
          </div>
        </div>
      )}
    </div>
  );
}

