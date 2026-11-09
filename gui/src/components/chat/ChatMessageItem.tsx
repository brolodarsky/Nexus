"use client";
/* eslint-disable @next/next/no-img-element */

/**
 * ChatMessageItem.tsx — Renders an individual user or assistant message bubble in the Chat thread.
 * Includes agent routing badges, executed model tier pills, rich GFM + Wiki-Link Markdown,
 * and collapsible execution trace panels (`ThinkingPanel`).
 */

// memo: Wraps individual message bubbles so historical turns never re-render unless their `message` reference changes
import { memo, useMemo } from "react";
// MarkdownMessage: Shared GFM + Obsidian [[Wiki-Link]] renderer (also used by the HITL Pre-Commit Preview)
import MarkdownMessage from "@/components/MarkdownMessage";
import { resolveImageUrl, type BranchMode, type Conversation } from "@/lib/api";
// ThinkingPanel: Lossless agent execution trace viewer with Graph View, full step payloads, and raw JSON
import { ThinkingPanel } from "@/components/AgentTraceVisualizer";
import MessageBranchTrigger from "./MessageBranchTrigger";
import { extractTurnCost, type Message } from "./types";

// ChatMessageItemProps: props for rendering a single conversation turn bubble
// - message: Message object containing role, markdown content, agent/model metadata, and optional trace events
// - messageIndex: 0-based index of this message within the conversation thread
// - isLastTurn: optional boolean indicating whether this message is the latest in the conversation thread
// - spawnedBranches: optional array of child Conversation records forked from this message turn
// - isBranching: optional boolean indicating whether a fork operation is currently running on this message
// - onRevertTurn: optional callback to revert this turn and restore its prompt back to the composer
// - onBranchMessage: optional callback to fork a child branch from this message turn
// - onSelectConversation: optional callback to navigate directly to a child branch conversation
export interface ChatMessageItemProps {
  message: Message;
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
  messageIndex = 0,
  isLastTurn = false,
  spawnedBranches,
  isBranching = false,
  onRevertTurn,
  onBranchMessage,
  onSelectConversation,
}: ChatMessageItemProps) {
  const isUser = message.role === "user";
  const hasTrace = Boolean(message.trace && message.trace.length > 0);
  // Memoize turn cost calculation so trace event scanning only runs once per message
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

        {/* Persisted trace log (collapsed by default for past messages) */}
        {!isUser && message.trace && message.trace.length > 0 && (
          <ThinkingPanel
            events={message.trace}
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

          <MessageBranchTrigger
            messageIndex={messageIndex}
            messageId={message.id}
            spawnedBranches={spawnedBranches}
            isBranching={isBranching}
            onBranch={onBranchMessage}
            onSelectConversation={onSelectConversation}
          />
        </div>
      </div>
    </div>
  );
});

export default ChatMessageItem;

