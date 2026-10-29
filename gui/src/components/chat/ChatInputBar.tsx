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
// - modelOptions: array of selectable ModelOption descriptors from `/api/agents/models`
// - selectedModelTier: active model tier identifier ("strong", "medium", "low")
// - activeModelLabel: human-readable label of the currently selected model tier
// - inputRef: React RefObject pointing to the underlying HTMLTextAreaElement for programmatic focus and auto-sizing
// - onChangeInput: callback updating the controlled `input` string state
// - onSelectModelTier: callback updating and persisting the user's selected model tier
// - onSubmit: form submission handler triggered by clicking Send or pressing Enter
export interface ChatInputBarProps {
  input: string;
  loading: boolean;
  modelOptions: ModelOption[];
  selectedModelTier: string;
  activeModelLabel: string;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  onChangeInput: (value: string) => void;
  onSelectModelTier: (tierId: string) => void;
  onSubmit: (e?: React.FormEvent) => void;
}

export default function ChatInputBar({
  input,
  loading,
  modelOptions,
  selectedModelTier,
  activeModelLabel,
  inputRef,
  onChangeInput,
  onSelectModelTier,
  onSubmit,
}: ChatInputBarProps) {
  // Auto-expand textarea height dynamically as the user types, bounded between a comfortable min and max height
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    // Reset height temporarily so scrollHeight accurately reflects current content after deletions or wrapping
    el.style.height = "auto";
    const minHeight = 56; // Roomy base height (~2 lines)
    const maxHeight = 240; // Max expansion limit (~10 lines) before vertical scrolling takes over
    const nextHeight = Math.min(Math.max(el.scrollHeight, minHeight), maxHeight);
    el.style.height = `${nextHeight}px`;
  }, [input, inputRef]);

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

  return (
    <form
      onSubmit={onSubmit}
      className="px-8 py-4 border-t border-border-subtle shrink-0"
    >
      <div className="glass-card p-3 rounded-2xl flex flex-col gap-2.5 border border-border-subtle focus-within:border-accent-cyan/40 transition-colors">
        <div className="flex items-start gap-3 px-1 pt-1">
          <span className="text-lg text-text-muted select-none mt-1">💬</span>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => onChangeInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={`Message Nexus (${activeModelLabel})...`}
            disabled={loading}
            rows={2}
            spellCheck={true}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none resize-none leading-relaxed disabled:opacity-50 min-h-[56px] max-h-60 overflow-y-auto"
            id="chat-input"
          />
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
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 disabled:opacity-50 ${
                    isSelected
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
                  <span className="hidden md:inline font-mono text-[0.65rem] opacity-75">
                    ({opt.model_name})
                  </span>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden md:inline text-[0.7rem] text-text-muted select-none">
              Enter ↵ to send • Shift + Enter ↵ for newline
            </span>
            <button
              type="submit"
              disabled={loading || !input.trim()}
              title="Send message (Enter)"
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

