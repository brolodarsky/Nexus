"use client";
/* eslint-disable @next/next/no-img-element */

/**
 * ChatMessageItem.tsx — Renders an individual user or assistant message bubble in the Chat thread.
 * Includes agent routing badges, executed model tier pills, rich GFM + Wiki-Link Markdown,
 * and collapsible execution trace panels (`ThinkingPanel`).
 */

// memo: Wraps individual message bubbles so historical turns never re-render unless their `message` reference changes
import { memo, useMemo, useState, useRef, useEffect } from "react";
// MarkdownMessage: Shared GFM + Obsidian [[Wiki-Link]] renderer (also used by the HITL Pre-Commit Preview)
import MarkdownMessage from "@/components/MarkdownMessage";
import { resolveImageUrl, type BranchMode, type Conversation } from "@/lib/api";
// ThinkingPanel: Lossless agent execution trace viewer with Graph View, full step payloads, and raw JSON
import { ThinkingPanel } from "@/components/AgentTraceVisualizer";
import MessageBranchTrigger from "./MessageBranchTrigger";
import { copyTextToClipboard, extractTurnCost, formatShortId, type Message } from "./types";

// ChatMessageItemProps: props for rendering a single conversation turn bubble
// - message: Message object containing role, markdown content, agent/model metadata, and optional trace events
// - conversationId: optional parent conversation UUID (thread_id) shown in the per-message kebab menu
// - messageIndex: 0-based index of this message within the conversation thread
// - isLastTurn: optional boolean indicating whether this message is the latest in the conversation thread
// - spawnedBranches: optional array of child Conversation records forked from this message turn
// - isBranching: optional boolean indicating whether a fork operation is currently running on this message
// - onRevertTurn: optional callback to revert this turn and restore its prompt back to the composer
// - onBranchMessage: optional callback to fork a child branch from this message turn
// - onSelectConversation: optional callback to navigate directly to a child branch conversation
export interface ChatMessageItemProps {
  message: Message;
  conversationId?: string | null;
  messageIndex?: number;
  isLastTurn?: boolean;
  spawnedBranches?: Conversation[];
  isBranching?: boolean;
  onRevertTurn?: () => void;
  onBranchMessage?: (messageIndex: number, messageId: number | undefined, mode: BranchMode) => Promise<void> | void;
  onSelectConversation?: (conversationId: string) => void;
}

const ChatMessageItem = memo(function ChatMessageItem({
  message,
  conversationId,
  messageIndex = 0,
  isLastTurn = false,
  spawnedBranches,
  isBranching = false,
  onRevertTurn,
  onBranchMessage,
  onSelectConversation,
}: ChatMessageItemProps) {
  const isUser = message.role === "user";
  const hasTrace = Boolean(message.hasTrace || (message.trace && message.trace.length > 0));
  // isMenuOpen: controls visibility of the per-message kebab popover displaying Thread/Message & Conversation IDs
  const [isMenuOpen, setIsMenuOpen] = useState<boolean>(false);
  // copiedTarget: tracks which ID item ("msg" | "conv") recently copied so the menu shows transient "Copied!" feedback
  const [copiedTarget, setCopiedTarget] = useState<"msg" | "conv" | null>(null);
  // menuRef: container ref used for outside-click dismissal of the per-message kebab popover
  const menuRef = useRef<HTMLDivElement>(null);
  // copyTimerRef: timeout handle cleared on unmount or rapid re-copy
  const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clean up transient copy-feedback timer on unmount
  useEffect(() => {
    return () => {
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  // Dismiss message kebab popover on outside click or Escape key press
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

  // Copies either the message/thread ID or parent conversation UUID and displays transient "Copied!" feedback
  const handleCopyMessageId = async (target: "msg" | "conv", value: string) => {
    const copied = await copyTextToClipboard(value);
    if (!copied) return;
    setCopiedTarget(target);
    if (copyTimerRef.current) {
      clearTimeout(copyTimerRef.current);
    }
    copyTimerRef.current = setTimeout(() => {
      setCopiedTarget(null);
      copyTimerRef.current = null;
    }, 1500);
  };

  // Canonical raw value and display label for this message turn (falls back to 1-based turn index before DB commit)
  const msgIdStr = message.id != null ? String(message.id) : `turn-${messageIndex + 1}`;
  const msgIdLabel = message.id != null ? `#${message.id}` : `turn-${messageIndex + 1}`;
  // Memoize turn cost calculation; use explicit cost_usd column if present, falling back to trace scan
  const effectiveCost = useMemo(
    () =>
      message.costUsd ??
      extractTurnCost(message.trace, null, message.modelName, message.modelTier),
    [message.costUsd, message.trace, message.modelName, message.modelTier]
  );

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`rounded-2xl px-5 py-3.5 text-sm leading-relaxed ${isUser
          ? "max-w-2xl bg-accent-cyan/10 border border-accent-cyan/20 text-text-primary"
          : hasTrace
            ? "max-w-4xl xl:max-w-5xl w-full glass-card text-text-primary"
            : "max-w-3xl glass-card text-text-primary"
          }`}
      >
        {/* Assistant routing & model execution metadata pills */}
        {!isUser && message.agent && (
          <div className="flex items-center gap-1.5 flex-wrap mb-2.5">
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[0.65rem] font-mono font-medium border ${
                message.agent === "branch_context" || message.agent === "branch_merge"
                  ? "bg-emerald-500/15 border-emerald-500/35 text-emerald-300"
                  : "bg-accent-cyan/10 border-accent-cyan/20 text-accent-cyan"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  message.agent === "branch_context" || message.agent === "branch_merge"
                    ? "bg-emerald-400"
                    : "bg-accent-cyan"
                }`}
              />
              {message.agent === "branch_context"
                ? "🌿 Parent Context Brief"
                : message.agent === "branch_merge"
                  ? "🌿 Distilled Branch Merge"
                  : message.agent === "nexus" || message.agent === "NexusAgent"
                    ? "Head Agent"
                    : message.agent || "Head Agent"}
              {message.domain && (
                <span className="text-text-muted font-sans">• {message.domain}</span>
              )}
              {message.confidence != null &&
                message.agent !== "branch_context" &&
                message.agent !== "branch_merge" && (
                  <span className="text-text-muted font-sans">
                    • {Math.round(message.confidence * 100)}%
                  </span>
                )}
            </span>

            {(message.modelName || message.modelTier) && (
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.65rem] font-mono border ${message.modelTier === "strong"
                  ? "bg-accent-violet/15 border-accent-violet/30 text-purple-300"
                  : "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                  }`}
                title={`Executed on ${message.modelName ?? message.modelTier} (${message.modelTier ?? "default"} tier)`}
              >
                <span>
                  {message.modelTier === "strong"
                    ? "🧠"
                    : message.modelTier === "medium"
                      ? "⚖️"
                      : "⚡"}
                </span>
                <span>{message.modelName ?? message.modelTier}</span>
              </span>
            )}

            {effectiveCost != null && effectiveCost > 0 && (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.65rem] font-mono border bg-amber-500/10 border-amber-500/30 text-amber-300"
                title={`Estimated inference cost: $${effectiveCost.toFixed(4)} USD`}
              >
                <span>💰</span>
                <span>${effectiveCost < 0.01 ? effectiveCost.toFixed(4) : effectiveCost.toFixed(3)}</span>
              </span>
            )}

            {isLastTurn && onRevertTurn && (
              <button
                type="button"
                onClick={onRevertTurn}
                title="Revert this turn, cancel staged mutations, and restore prompt to composer"
                aria-label="Revert turn"
                className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[0.65rem] font-mono font-medium border bg-rose-500/10 hover:bg-rose-500/20 border-rose-500/30 text-rose-300 transition-colors ml-auto cursor-pointer"
              >
                <span>↩</span>
                <span>Revert turn</span>
              </button>
            )}
          </div>
        )}

        {/* Message body: full GFM + Wiki-Link Markdown for assistant; note links open into new tabs so the active chat thread is never interrupted */}
        {!isUser ? (
          <MarkdownMessage content={message.content} openInNewTab={true} />
        ) : (
          <div className="space-y-2">
            {/* Attached images preview grid */}
            {message.images && message.images.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-0.5">
                {message.images.map((imgUrl, idx) => {
                  const resolved = resolveImageUrl(imgUrl);
                  return (
                    <div
                      key={idx}
                      className="relative group rounded-xl overflow-hidden border border-white/10 bg-black/30 shadow-md max-w-xs"
                    >
                      <a
                        href={resolved}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block focus:outline-none"
                        title="Click to view full image in new tab"
                      >
                        <img
                          src={resolved}
                          alt="Attached user image"
                          className="max-h-60 w-auto object-contain rounded-lg hover:scale-[1.02] transition-transform duration-200 cursor-pointer"
                          loading="lazy"
                        />
                      </a>
                    </div>
                  );
                })}
              </div>
            )}
            {/* User prompt text: rendered with full GFM + Wiki-Link Markdown support so note links typed by the user also click into new tabs */}
            {message.content && (
              <MarkdownMessage
                content={message.content}
                openInNewTab={true}
                className="whitespace-pre-wrap"
              />
            )}
          </div>
        )}

        {/* Persisted trace log (collapsed by default for past messages; lazy-loaded on demand if traces exist) */}
        {!isUser && hasTrace && (
          <ThinkingPanel
            events={message.trace}
            messageId={message.id}
            isLive={false}
            defaultExpanded={false}
          />
        )}

        <div className="mt-2.5 flex items-center justify-between gap-2 flex-wrap">
          <span className="text-[0.65rem] text-text-muted">
            {message.timestamp.toLocaleTimeString(undefined, {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>

          <div className="flex items-center gap-1.5 flex-wrap">
            <MessageBranchTrigger
              messageIndex={messageIndex}
              messageId={message.id}
              spawnedBranches={spawnedBranches}
              isBranching={isBranching}
              onBranch={onBranchMessage}
              onSelectConversation={onSelectConversation}
            />

            {/* Per-message kebab menu: exposes Thread/Message ID & Conversation ID for copying */}
            <div className="relative inline-flex items-center" ref={menuRef}>
              <button
                type="button"
                onClick={() => setIsMenuOpen((prev) => !prev)}
                title="Message options & IDs"
                aria-label="Message options & IDs"
                aria-haspopup="menu"
                aria-expanded={isMenuOpen}
                className={`p-1 rounded-full transition-colors flex items-center justify-center cursor-pointer ${
                  isMenuOpen
                    ? "bg-bg-tertiary text-text-primary border border-border-subtle"
                    : "text-text-muted hover:text-text-primary hover:bg-bg-tertiary/70"
                }`}
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="12" cy="5" r="2" />
                  <circle cx="12" cy="12" r="2" />
                  <circle cx="12" cy="19" r="2" />
                </svg>
              </button>

              {/* Upward popover prevents clipping at the bottom edge of the scrollable chat feed */}
              {isMenuOpen && (
                <div
                  role="menu"
                  aria-orientation="vertical"
                  className="absolute bottom-full right-0 mb-1.5 w-56 max-w-[calc(100vw-2rem)] rounded-xl bg-bg-secondary/95 backdrop-blur-md border border-border-subtle shadow-2xl p-1 z-30 animate-in fade-in zoom-in-95 duration-100"
                >
                  {/* Thread / Message ID click-to-copy item */}
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => void handleCopyMessageId("msg", msgIdStr)}
                    title={`Click to copy Thread / Message ID: ${msgIdStr}`}
                    className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs font-medium transition-colors text-left ${
                      copiedTarget === "msg"
                        ? "text-emerald-300 bg-emerald-500/10"
                        : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
                    }`}
                  >
                    {copiedTarget === "msg" ? (
                      <span className="w-3.5 text-center shrink-0 font-bold">✓</span>
                    ) : (
                      <svg className="w-3.5 h-3.5 text-text-muted shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                      </svg>
                    )}
                    <span className="truncate">
                      {copiedTarget === "msg" ? (
                        <>
                          Copied! (<span className="font-mono">{msgIdLabel}</span>)
                        </>
                      ) : (
                        <>
                          Thread ID: <span className="font-mono text-text-primary">{msgIdLabel}</span>
                        </>
                      )}
                    </span>
                  </button>

                  {/* Parent Conversation ID click-to-copy item */}
                  {conversationId && (
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => void handleCopyMessageId("conv", conversationId)}
                      title={`Click to copy Conversation ID: ${conversationId}`}
                      className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs font-medium transition-colors text-left ${
                        copiedTarget === "conv"
                          ? "text-emerald-300 bg-emerald-500/10"
                          : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary"
                      }`}
                    >
                      {copiedTarget === "conv" ? (
                        <span className="w-3.5 text-center shrink-0 font-bold">✓</span>
                      ) : (
                        <svg className="w-3.5 h-3.5 text-text-muted shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                          <path strokeLinecap="round" strokeLinejoin="round" d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                        </svg>
                      )}
                      <span className="truncate">
                        {copiedTarget === "conv" ? (
                          <>
                            Copied! (<span className="font-mono">{formatShortId(conversationId)}</span>)
                          </>
                        ) : (
                          <>
                            Conv ID:{" "}
                            <span className="font-mono text-text-primary">
                              {formatShortId(conversationId)}
                            </span>
                          </>
                        )}
                      </span>
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});

export default ChatMessageItem;

