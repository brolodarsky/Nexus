"use client";

/**
 * ChatMessageItem.tsx — Renders an individual user or assistant message bubble in the Chat thread.
 * Includes agent routing badges, executed model tier pills, rich GFM + Wiki-Link Markdown,
 * and collapsible execution trace panels (`ThinkingPanel`).
 */

// memo: Wraps individual message bubbles so historical turns never re-render unless their `message` reference changes
import { memo, useMemo } from "react";
// MarkdownMessage: Shared GFM + Obsidian [[Wiki-Link]] renderer (also used by the HITL Pre-Commit Preview)
import MarkdownMessage from "@/components/MarkdownMessage";
// ThinkingPanel: Lossless agent execution trace viewer with Graph View, full step payloads, and raw JSON
import { ThinkingPanel } from "@/components/AgentTraceVisualizer";
import { extractTurnCost, type Message } from "./types";

// ChatMessageItemProps: props for rendering a single conversation turn bubble
// - message: Message object containing role, markdown content, agent/model metadata, and optional trace events
export interface ChatMessageItemProps {
  message: Message;
}

const ChatMessageItem = memo(function ChatMessageItem({ message }: ChatMessageItemProps) {
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
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[0.65rem] font-mono font-medium bg-accent-cyan/10 border border-accent-cyan/20 text-accent-cyan">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan" />
              {message.agent || "nexus"}
              {message.domain && (
                <span className="text-text-muted font-sans">• {message.domain}</span>
              )}
              {message.confidence != null && (
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
          </div>
        )}

        {/* Message body: full GFM + Wiki-Link Markdown for assistant, pre-wrapped text for user */}
        {!isUser ? (
          <MarkdownMessage content={message.content} />
        ) : (
          <p className="whitespace-pre-wrap">{message.content}</p>
        )}

        {/* Persisted trace log (collapsed by default for past messages) */}
        {!isUser && message.trace && message.trace.length > 0 && (
          <ThinkingPanel
            events={message.trace}
            isLive={false}
            defaultExpanded={false}
          />
        )}

        <span className="block mt-2 text-[0.65rem] text-text-muted">
          {message.timestamp.toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>
    </div>
  );
});

export default ChatMessageItem;

