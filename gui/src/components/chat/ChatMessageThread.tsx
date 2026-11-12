"use client";

/**
 * ChatMessageThread.tsx — Scrollable message feed for the Nexus Chat workspace.
 * Manages automatic bottom-scrolling, empty-state starter prompts, message bubbles,
 * and the live streaming `ThinkingPanel` indicator.
 */

// memo: Isolates the scrollable message feed from sibling/parent state updates (e.g., input typing or sidebar toggles)
import { useRef, useEffect, useState, useCallback, memo } from "react";
import { ThinkingPanel } from "@/components/AgentTraceVisualizer";
import type { BranchMode, Conversation, TraceEvent } from "@/lib/api";
import type { Message } from "./types";
import ChatMessageItem from "./ChatMessageItem";

// Distance in pixels from the bottom of the feed within which auto-scrolling remains sticky/locked
const SCROLL_BOTTOM_THRESHOLD = 80;

// Starter prompt suggestions displayed when a conversation has no messages yet
const PROMPT_SUGGESTIONS: string[] = [
  "What do we got for today?",
  "Do an email sweep.",
  "What are my outstanding Missions?",
];

// ChatMessageThreadProps: defines the state and callbacks needed to render the message stream
// - activeConvId: optional UUID string identifying the active conversation thread
// - messages: ordered list of user and assistant Message objects in the active conversation
// - loading: boolean indicating whether an SSE agent response stream is currently in-flight
// - liveTrace: array of real-time TraceEvent payloads emitted during the active streaming turn
// - activeModelLabel: human-readable label of the selected model tier shown in the live status indicator
// - childBranchesByMessageId: optional lookup dictionary mapping `messages.id` -> child branch conversations
// - branchingMessageIndex: optional 0-based index of the message currently being forked
// - onSelectPromptSuggestion: callback to populate the chat input when a user clicks an example prompt
// - onStopAndRevert: optional callback to immediately abort execution and revert the active turn
// - onRevertLastTurn: optional callback to revert the most recent completed turn
// - onBranchMessage: optional callback to fork a child branch from any message turn
// - onSelectConversation: optional callback to switch to a child branch conversation
export interface ChatMessageThreadProps {
  activeConvId?: string | null;
  messages: Message[];
  loading: boolean;
  liveTrace: TraceEvent[];
  activeModelLabel: string;
  childBranchesByMessageId?: Record<number, Conversation[]>;
  branchingMessageIndex?: number | null;
  onSelectPromptSuggestion: (suggestion: string) => void;
  onStopAndRevert?: () => void;
  onRevertLastTurn?: () => void;
  onBranchMessage?: (messageIndex: number, messageId: number | undefined, mode: BranchMode) => Promise<void> | void;
  onSelectConversation?: (conversationId: string) => void;
}

const ChatMessageThread = memo(function ChatMessageThread({
  activeConvId,
  messages,
  loading,
  liveTrace,
  activeModelLabel,
  childBranchesByMessageId,
  branchingMessageIndex = null,
  onSelectPromptSuggestion,
  onStopAndRevert,
  onRevertLastTurn,
  onBranchMessage,
  onSelectConversation,
}: ChatMessageThreadProps) {
  // scrollRef: DOM reference to the scrollable thread container for sticky bottom-pinning
  const scrollRef = useRef<HTMLDivElement>(null);
  // isAtBottomRef: mutable ref tracking whether user is currently scrolled to the bottom (within threshold)
  // Auto-Scroll Invariant: When true, incoming messages and AgentTracer liveTrace events keep the view pinned to bottom.
  // When false (user deliberately scrolled up to read earlier notes or tool results), auto-scroll is DISENGAGED
  // so telemetry events never yank the user's viewport away from what they are reading.
  const isAtBottomRef = useRef<boolean>(true);
  // isProgrammaticScrollRef: guards handleScroll from falsely flipping isAtBottom during smooth scroll transitions
  const isProgrammaticScrollRef = useRef<boolean>(false);
  // prevConvIdRef: tracks activeConvId changes to reset scroll-to-bottom on conversation switches
  const prevConvIdRef = useRef<string | null | undefined>(activeConvId);
  // prevMessagesLengthRef: tracks message additions to distinguish user-initiated submissions from streaming updates
  const prevMessagesLengthRef = useRef<number>(messages.length);

  // showScrollBottom: displays floating "Scroll to bottom" button when user scrolls up away from bottom
  const [showScrollBottom, setShowScrollBottom] = useState<boolean>(false);
  // hasNewActivityWhileScrolled: pulses an active badge on the scroll button if new output arrives while scrolled up
  const [hasNewActivityWhileScrolled, setHasNewActivityWhileScrolled] = useState<boolean>(false);

  // Programmatically scrolls the thread container to the bottom and restores bottom stickiness
  const scrollToBottom = useCallback((smooth = false) => {
    const el = scrollRef.current;
    if (!el) return;

    isAtBottomRef.current = true;
    setShowScrollBottom(false);
    setHasNewActivityWhileScrolled(false);
    isProgrammaticScrollRef.current = true;

    if (smooth) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      const timer = setTimeout(() => {
        isProgrammaticScrollRef.current = false;
        if (scrollRef.current) {
          const { scrollHeight, scrollTop, clientHeight } = scrollRef.current;
          isAtBottomRef.current = scrollHeight - scrollTop - clientHeight <= SCROLL_BOTTOM_THRESHOLD;
        }
      }, 350);
      return () => clearTimeout(timer);
    } else {
      el.scrollTop = el.scrollHeight;
      requestAnimationFrame(() => {
        isProgrammaticScrollRef.current = false;
      });
    }
  }, []);

  // Tracks user scroll events to detect scroll detachment and update floating button visibility
  const handleScroll = useCallback(() => {
    if (isProgrammaticScrollRef.current) return;
    const el = scrollRef.current;
    if (!el) return;

    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const isNearBottom = distanceFromBottom <= SCROLL_BOTTOM_THRESHOLD;

    isAtBottomRef.current = isNearBottom;
    setShowScrollBottom((prev) => (prev !== !isNearBottom ? !isNearBottom : prev));

    if (isNearBottom) {
      setHasNewActivityWhileScrolled(false);
    }
  }, []);

  // When switching conversation threads, snap immediately to bottom and reset detachment flags
  useEffect(() => {
    if (prevConvIdRef.current !== activeConvId) {
      prevConvIdRef.current = activeConvId;
      isAtBottomRef.current = true;
      setShowScrollBottom(false);
      setHasNewActivityWhileScrolled(false);
      scrollToBottom(false);
    }
  }, [activeConvId, scrollToBottom]);

  // Handle messages changes:
  // - If user appended a prompt, always snap to bottom
  // - If assistant response is streaming/finishing, only auto-scroll if user is pinned to bottom
  useEffect(() => {
    const prevLen = prevMessagesLengthRef.current;
    const currLen = messages.length;
    prevMessagesLengthRef.current = currLen;

    if (currLen > prevLen) {
      const latestMsg = messages[currLen - 1];
      if (latestMsg?.role === "user") {
        isAtBottomRef.current = true;
        setShowScrollBottom(false);
        setHasNewActivityWhileScrolled(false);
        scrollToBottom(false);
        return;
      }
    }

    if (isAtBottomRef.current) {
      scrollToBottom(false);
    } else if (currLen > prevLen) {
      setHasNewActivityWhileScrolled(true);
    }
  }, [messages, scrollToBottom]);

  // Auto-scroll on incoming AgentTracer telemetry events ONLY if the user is pinned to the bottom.
  // If the user has scrolled up to inspect previous turns, leave scroll position untouched and flag new activity.
  useEffect(() => {
    if (liveTrace.length === 0) return;

    if (isAtBottomRef.current) {
      scrollToBottom(false);
    } else {
      setHasNewActivityWhileScrolled(true);
    }
  }, [liveTrace, scrollToBottom]);

  // Keep pinned to bottom when the live thinking banner mounts or unmounts while pinned
  useEffect(() => {
    if (isAtBottomRef.current) {
      scrollToBottom(false);
    }
  }, [loading, scrollToBottom]);

  return (
    <div className="relative flex-1 min-h-0 flex flex-col">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
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
            key={msg.id ?? i}
            message={msg}
            messageIndex={i}
            isLastTurn={i === messages.length - 1}
            spawnedBranches={msg.id != null ? childBranchesByMessageId?.[msg.id] : undefined}
            isBranching={branchingMessageIndex === i}
            onRevertTurn={onRevertLastTurn}
            onBranchMessage={onBranchMessage}
            onSelectConversation={onSelectConversation}
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
                key={`live-${activeConvId ?? "new"}`}
                events={liveTrace}
                isLive={true}
                defaultExpanded={false}
              />
            </div>
          </div>
        )}
      </div>

      {/* Floating Scroll to Bottom / New Activity Pill */}
      {showScrollBottom && (
        <button
          type="button"
          onClick={() => scrollToBottom(true)}
          aria-label="Scroll to latest messages"
          className="absolute bottom-5 right-6 md:right-10 z-20 flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium glass-card border border-border-subtle/80 bg-bg-secondary/95 hover:bg-bg-tertiary text-text-secondary hover:text-text-primary shadow-xl backdrop-blur-md transition-all hover:scale-105 active:scale-95 animate-in fade-in slide-in-from-bottom-2 duration-150 cursor-pointer"
        >
          {hasNewActivityWhileScrolled ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-cyan opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-accent-cyan" />
              </span>
              <span className="text-accent-cyan font-medium">New activity</span>
            </>
          ) : (
            <span>Scroll to bottom</span>
          )}
          <svg
            className="w-3.5 h-3.5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>
        </button>
      )}
    </div>
  );
});

export default ChatMessageThread;

