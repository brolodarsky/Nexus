"use client";

/**
 * ChatInputBar.tsx — Multiline auto-expanding chat input with per-turn model tier selector.
 * Handles dynamic textarea height resizing, Enter/Shift+Enter keyboard shortcuts,
 * and segmented capability tier buttons (`Strong` vs `Fast`).
 */

import { useEffect } from "react";
import type { ModelOption } from "@/lib/api";

// ChatInputBarProps: defines controlled input state, model options, and event handlers for the chat composer
// - input: current unsubmitted text inside the textarea
// - loading: boolean disabling submission while an agent stream is active
// - isCollapsed: boolean indicating whether the input bar is minimized to a compact rail to maximize thread space
// - modelOptions: array of selectable ModelOption descriptors from `/api/agents/models`
// - selectedModelTier: active model tier identifier ("strong", "medium", "low")
// - activeModelLabel: human-readable label of the currently selected model tier
// - inputRef: React RefObject pointing to the underlying HTMLTextAreaElement for programmatic focus and auto-sizing
// - onChangeInput: callback updating the controlled `input` string state
// - onSelectModelTier: callback updating and persisting the user's selected model tier
// - onToggleCollapse: callback updating and persisting whether the input bar is minimized or expanded
// - onSubmit: form submission handler triggered by clicking Send or pressing Enter
export interface ChatInputBarProps {
  input: string;
  loading: boolean;
  isCollapsed: boolean;
  modelOptions: ModelOption[];
  selectedModelTier: string;
  activeModelLabel: string;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  onChangeInput: (value: string) => void;
  onSelectModelTier: (tierId: string) => void;
  onToggleCollapse: (collapsed: boolean) => void;
  onSubmit: (e?: React.FormEvent) => void;
}

export default function ChatInputBar({
  input,
  loading,
  isCollapsed,
  modelOptions,
  selectedModelTier,
  activeModelLabel,
  inputRef,
  onChangeInput,
  onSelectModelTier,
  onToggleCollapse,
  onSubmit,
}: ChatInputBarProps) {
  // Auto-expand textarea height dynamically as the user types, bounded between a comfortable min and max height
  useEffect(() => {
    if (isCollapsed) return;
    const el = inputRef.current;
    if (!el) return;
    // Reset height temporarily so scrollHeight accurately reflects current content after deletions or wrapping
    el.style.height = "auto";
    const minHeight = 10;
    const maxHeight = 240; // Max expansion limit (~10 lines) before vertical scrolling takes over
    const nextHeight = Math.min(Math.max(el.scrollHeight, minHeight), maxHeight);
    el.style.height = `${nextHeight}px`;
  }, [input, inputRef, isCollapsed]);

  // Keyboard shortcut handler for multiline chat textarea:
  // - Enter (without Shift) triggers immediate submission
  // - Shift+Enter inserts a newline, allowing the user to type structured multi-paragraph prompts
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!loading && input.trim()) {
        onSubmit();
      }
    }
  };

  // Render compact collapsed bottom rail if minimized by the user
  if (isCollapsed) {
    return (
      <div className="px-8 py-2.5 border-t border-border-subtle shrink-0">
        <div
          role="button"
          tabIndex={0}
          onClick={() => onToggleCollapse(false)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onToggleCollapse(false);
            }
          }}
          className="glass-card px-4 py-2 rounded-xl flex items-center justify-between gap-3 cursor-pointer hover:border-accent-cyan/40 hover:bg-bg-card-hover transition-all w-full text-xs text-text-muted hover:text-text-secondary select-none"
          title="Click or press Enter to expand message bar"
          aria-label="Expand message bar"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="text-sm shrink-0">💬</span>
            <span className="truncate">
              {input.trim() ? (
                <span>
                  <span className="text-accent-cyan font-medium">Draft:</span>{" "}
                  <span className="text-text-primary">
                    &ldquo;{input.slice(0, 60)}{input.length > 60 ? "…" : ""}&rdquo;
                  </span>
                </span>
              ) : (
                <span>Message bar collapsed — Click or press Enter to type</span>
              )}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="px-2 py-0.5 rounded-md bg-bg-secondary/80 border border-border-subtle text-[0.7rem] font-mono text-text-muted">
              {activeModelLabel}
            </span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onToggleCollapse(false);
              }}
              className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-surface/50 transition-colors"
              title="Expand message bar"
              aria-label="Expand message bar"
            >
              <svg
                viewBox="0 0 24 24"
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="18 15 12 9 6 15" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className="px-8 py-4 border-t border-border-subtle shrink-0"
    >
      <div className="glass-card p-3 rounded-2xl flex flex-col gap-2.5 border border-border-subtle focus-within:border-accent-cyan/40 transition-colors">
        <div className="flex items-start gap-3 px-1 pt-1">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => onChangeInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Type message...`}
            disabled={loading}
            rows={1}
            spellCheck={true}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none resize-none leading-relaxed disabled:opacity-50 max-h-60 overflow-y-auto"
            id="chat-input"
          />
          <button
            type="button"
            onClick={() => onToggleCollapse(true)}
            title="Collapse message bar"
            aria-label="Collapse message bar"
            className="text-text-muted hover:text-text-primary p-1 rounded-lg hover:bg-bg-surface/50 transition-colors shrink-0"
          >
            <svg
              viewBox="0 0 24 24"
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        </div>

        {/* Bottom toolbar inside input card: Per-turn model pills + send action */}
        <div className="flex items-center justify-between gap-2 flex-wrap sm:flex-nowrap pt-2 border-t border-border-subtle/50 px-1">
          {/* Per-Turn Model Selector: segmented toggle pills + native select accessibility */}
          <div
            className="flex items-center gap-1 p-1 rounded-xl bg-bg-secondary/80 border border-border-subtle shrink-0"
            role="group"
            aria-label="Select model for this turn"
          >
            {modelOptions.map((opt) => {
              const isSelected = selectedModelTier === opt.id;
              const isStrong = opt.tier === "strong";
              return (
                <button
                  key={opt.id}
                  type="button"
                  disabled={loading}
                  onClick={() => onSelectModelTier(opt.id)}
                  title={opt.description}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 disabled:opacity-50 ${isSelected
                    ? isStrong
                      ? "bg-accent-violet/20 text-purple-300 border border-accent-violet/40 shadow-sm"
                      : "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40 shadow-sm"
                    : "text-text-muted hover:text-text-primary border border-transparent"
                    }`}
                >
                  <span>
                    {isStrong ? "🧠" : opt.tier === "medium" ? "⚖️" : "⚡"}
                  </span>
                  <span>{opt.short_label}</span>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={loading || !input.trim()}
              title="Send message (Enter) • Newline (Shift+Enter)"
              className="flex items-center justify-center w-9 h-9 rounded-xl bg-accent-cyan/15 text-accent-cyan hover:bg-accent-cyan/25 transition-colors disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
            >
              <svg
                viewBox="0 0 24 24"
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M22 2L11 13" />
                <path d="M22 2L15 22L11 13L2 9L22 2Z" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </form>
  );
}

