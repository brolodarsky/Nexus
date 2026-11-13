"use client";
/* eslint-disable @next/next/no-img-element */

/**
 * ChatInputBar.tsx — Multiline auto-expanding chat input with per-turn model selector dropdown.
 * Handles dynamic textarea height resizing, Enter/Shift+Enter keyboard shortcuts,
 * and an accessible dropdown menu for switching capability tiers and explicit models
 * (e.g. `Strong (gemini-4-argon)`, `Fast (gemini-3.8-flash)`, `Hydrogen (gemini-4-hydrogen)`, Claude Opus/Sonnet).
 * Isolates live keystroke buffer state locally so typing never triggers full-page re-renders.
 */

import { useState, useEffect, useRef, memo } from "react";
import type { ModelOption } from "@/lib/api";
import { uploadImage, resolveImageUrl } from "@/lib/api";

// Height bounds (in pixels) for the auto-expanding multiline chat textarea
const MIN_TEXTAREA_HEIGHT = 10;
const MAX_TEXTAREA_HEIGHT = 240; // Max expansion limit (~10 lines) before vertical scrolling takes over

// Resizes the textarea DOM element to match its content height without unnecessary layout thrashing.
// - el: HTMLTextAreaElement | null — Target textarea element to measure and resize.
function syncTextareaHeight(el: HTMLTextAreaElement | null): void {
  if (!el) return;
  // Reset height temporarily so scrollHeight accurately reflects current content after deletions or wrapping
  el.style.height = "auto";
  const nextHeight = Math.min(Math.max(el.scrollHeight, MIN_TEXTAREA_HEIGHT), MAX_TEXTAREA_HEIGHT);
  el.style.height = `${nextHeight}px`;
}

// ChatInputBarProps: defines controlled/synchronized input state, model options, and event handlers for the chat composer
// - input: externally seeded text value (e.g., restored draft on thread switch, cleared "" on submit, or starter prompt)
// - inputSyncId: optional monotonic counter incremented whenever the parent programmatically overrides `input`
// - loading: boolean disabling submission while an agent stream is active
// - isCollapsed: boolean indicating whether the input bar is minimized to a compact rail to maximize thread space
// - modelOptions: array of selectable ModelOption descriptors from `/api/agents/models`
// - selectedModelTier: active model tier identifier ("strong", "medium", "low")
// - activeModelLabel: human-readable label of the currently selected model tier
// - inputRef: React RefObject pointing to the underlying HTMLTextAreaElement for programmatic focus and auto-sizing
// - pendingImages: optional array of uploaded image URLs staged for the upcoming turn
// - onAddImages: optional callback appending freshly uploaded image URLs to the staged attachments list
// - onRemoveImage: optional callback removing an attachment by array index
// - onChangeInput: callback notifying parent of updated draft text (without forcing parent re-renders on every keystroke)
// - onSelectModelTier: callback updating and persisting the user's selected model tier
// - onToggleCollapse: callback updating and persisting whether the input bar is minimized or expanded
// - onSubmit: form submission handler triggered by clicking Send or pressing Enter
export interface ChatInputBarProps {
  input: string;
  inputSyncId?: number;
  loading: boolean;
  isCollapsed: boolean;
  modelOptions: ModelOption[];
  selectedModelTier: string;
  activeModelLabel: string;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  pendingImages?: string[];
  onAddImages?: (urls: string[]) => void;
  onRemoveImage?: (index: number) => void;
  onChangeInput: (value: string) => void;
  onSelectModelTier: (tierId: string) => void;
  onToggleCollapse: (collapsed: boolean) => void;
  onStopAndRevert?: () => void;
  onSubmit: (e?: React.FormEvent) => void;
}

const ChatInputBar = memo(function ChatInputBar({
  input,
  inputSyncId = 0,
  loading,
  isCollapsed,
  modelOptions,
  selectedModelTier,
  activeModelLabel,
  inputRef,
  pendingImages = [],
  onAddImages,
  onRemoveImage,
  onChangeInput,
  onSelectModelTier,
  onToggleCollapse,
  onStopAndRevert,
  onSubmit,
}: ChatInputBarProps) {
  // Local typing buffer: keeps per-keystroke React state updates confined strictly inside ChatInputBar
  const [localInput, setLocalInput] = useState<string>(input);
  // Tracks the last seen external `input` and `inputSyncId` props to detect programmatic parent overrides during render
  const [prevSync, setPrevSync] = useState<{ input: string; inputSyncId: number }>({
    input,
    inputSyncId,
  });
  // Upload status and transient error banner state for chat image attachments
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  // Drag-and-drop hover feedback state
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  // Model selector dropdown open/closed state and container ref for outside-click / Escape dismissal
  const [isModelMenuOpen, setIsModelMenuOpen] = useState<boolean>(false);
  const modelMenuRef = useRef<HTMLDivElement>(null);
  // Hidden input element ref for triggering browser file dialog on paperclip click
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Dismiss model dropdown menu on outside click or Escape key press
  useEffect(() => {
    if (!isModelMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (modelMenuRef.current && !modelMenuRef.current.contains(e.target as Node)) {
        setIsModelMenuOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsModelMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isModelMenuOpen]);

  // Render-phase prop synchronization: when the parent switches conversations, clears on submit, or injects a prompt suggestion,
  // immediately snap `localInput` to the new `input` value in the same render pass without a cascading effect re-render.
  if (input !== prevSync.input || inputSyncId !== prevSync.inputSyncId) {
    setPrevSync({ input, inputSyncId });
    setLocalInput(input);
  }

  // Re-measure textarea height when expanding from collapsed rail or when external input is programmatically loaded/cleared
  useEffect(() => {
    if (isCollapsed) return;
    syncTextareaHeight(inputRef.current);
  }, [input, inputSyncId, inputRef, isCollapsed]);

  // Uploads one or more selected/pasted image or PDF files to the FastAPI /api/agents/upload endpoint
  const handleUploadFiles = async (files: FileList | File[]) => {
    const validFiles = Array.from(files).filter(
      (f) =>
        f.type.startsWith("image/") ||
        f.type === "application/pdf" ||
        /\.(png|jpe?g|webp|gif|bmp|pdf)$/i.test(f.name)
    );
    if (validFiles.length === 0) return;

    setUploadError(null);
    setIsUploading(true);
    try {
      const uploadedUrls: string[] = [];
      for (const file of validFiles) {
        const res = await uploadImage(file);
        // If a multi-page PDF was uploaded and rasterized, stage all rendered page URLs
        if (res.page_urls && res.page_urls.length > 0) {
          uploadedUrls.push(...res.page_urls);
        } else {
          uploadedUrls.push(res.url);
        }
      }
      onAddImages?.(uploadedUrls);
    } catch (err: unknown) {
      console.error("File upload failed:", err);
      setUploadError(err instanceof Error ? err.message : "Failed to upload file.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  // Clipboard paste listener: enables instant screenshot pasting (Ctrl+V) directly into the chat composer
  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    const pastedFiles: File[] = [];
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith("image/")) {
        const file = items[i].getAsFile();
        if (file) pastedFiles.push(file);
      }
    }

    if (pastedFiles.length > 0) {
      e.preventDefault();
      handleUploadFiles(pastedFiles);
    }
  };

  // Drag-and-drop handlers for dropping screenshots or image files directly onto the composer
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDragOver) setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
      handleUploadFiles(e.dataTransfer.files);
    }
  };

  // Handles user typing inside the textarea: updates local buffer, resizes inline in the event handler, and notifies parent
  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const nextValue = e.target.value;
    setLocalInput(nextValue);
    syncTextareaHeight(e.currentTarget);
    onChangeInput(nextValue);
  };

  // Keyboard shortcut handler for multiline chat textarea:
  // - Enter (without Shift) triggers immediate submission if prompt text or pending images exist
  // - Shift+Enter inserts a newline, allowing the user to type structured multi-paragraph prompts
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      const hasContent = Boolean(localInput.trim()) || pendingImages.length > 0;
      if (!loading && !isUploading && hasContent) {
        onSubmit();
      }
    }
  };

  // Render compact collapsed bottom rail if minimized by the user
  if (isCollapsed) {
    return (
      <div className="px-4 md:px-8 py-2.5 border-t border-border-subtle shrink-0">
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
              {localInput.trim() ? (
                <span>
                  <span className="text-accent-cyan font-medium">Draft:</span>{" "}
                  <span className="text-text-primary">
                    &ldquo;{localInput.slice(0, 60)}{localInput.length > 60 ? "…" : ""}&rdquo;
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
      className="px-3 sm:px-4 md:px-8 py-3 md:py-4 border-t border-border-subtle shrink-0"
    >
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`glass-card p-3 rounded-2xl flex flex-col gap-2.5 border transition-all ${
          isDragOver
            ? "border-accent-cyan bg-accent-cyan/5 ring-2 ring-accent-cyan/20"
            : "border-border-subtle focus-within:border-accent-cyan/40"
        }`}
      >
        {/* Staged Image Attachments Ribbon: Displays removable thumbnail preview cards before sending */}
        {((pendingImages && pendingImages.length > 0) || isUploading) && (
          <div className="flex items-center gap-2 px-1 pt-1 overflow-x-auto pb-1 max-w-full">
            {pendingImages?.map((url, idx) => (
              <div
                key={idx}
                className="relative group rounded-xl overflow-hidden border border-border-subtle bg-bg-secondary shrink-0 shadow-sm"
              >
                <img
                  src={resolveImageUrl(url)}
                  alt="Staged attachment"
                  className="w-14 h-14 object-cover"
                />
                <button
                  type="button"
                  onClick={() => onRemoveImage?.(idx)}
                  className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/80 hover:bg-red-500 text-white flex items-center justify-center text-xs opacity-90 group-hover:opacity-100 transition-colors"
                  title="Remove image"
                  aria-label="Remove image attachment"
                >
                  ×
                </button>
              </div>
            ))}

            {isUploading && (
              <div className="w-14 h-14 rounded-xl border border-dashed border-accent-cyan/50 flex flex-col items-center justify-center shrink-0 bg-accent-cyan/5 text-accent-cyan animate-pulse">
                <svg
                  className="animate-spin w-4 h-4 text-accent-cyan mb-1"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v8H4z"
                  />
                </svg>
                <span className="text-[0.6rem] font-mono">Uploading</span>
              </div>
            )}
          </div>
        )}

        {/* Transient upload error alert */}
        {uploadError && (
          <div className="px-2 py-1 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center justify-between">
            <span>⚠️ {uploadError}</span>
            <button
              type="button"
              onClick={() => setUploadError(null)}
              className="text-text-muted hover:text-text-primary ml-2 text-sm"
            >
              ×
            </button>
          </div>
        )}

        <div className="flex items-start gap-3 px-1 pt-1">
          {/* text-base (16px) on mobile (< 768px) prevents iOS Safari from auto-zooming the viewport on focus; md:text-sm restores 14px on desktop */}
          <textarea
            ref={inputRef}
            value={localInput}
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={
              pendingImages.length > 0
                ? "Add an optional prompt or question for the attachments..."
                : "Type message, paste screenshot (Ctrl+V), or drag & drop image/PDF..."
            }
            disabled={loading}
            rows={1}
            spellCheck={true}
            className="flex-1 bg-transparent text-base md:text-sm text-text-primary placeholder:text-text-muted focus:outline-none resize-none leading-relaxed disabled:opacity-50 max-h-60 overflow-y-auto"
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

        {/* Bottom toolbar inside input card: Per-turn model dropdown + attachment + send action */}
        <div className="flex items-center justify-between gap-2 flex-wrap sm:flex-nowrap pt-2 border-t border-border-subtle/50 px-1">
          {/* Per-Turn Model Selector Dropdown */}
          <div className="relative min-w-0" ref={modelMenuRef}>
            {(() => {
              const selectedOpt =
                modelOptions.find((m) => m.id === selectedModelTier) ?? modelOptions[0];
              const isSelectedStrong = selectedOpt?.tier === "strong";
              return (
                <>
                  <button
                    type="button"
                    disabled={loading}
                    onClick={() => setIsModelMenuOpen((prev) => !prev)}
                    aria-haspopup="listbox"
                    aria-expanded={isModelMenuOpen}
                    aria-label="Select model for this turn"
                    title={selectedOpt?.description || "Select model for this turn"}
                    className={`px-2.5 py-1.5 rounded-xl text-xs font-medium transition-all flex items-center gap-2 border disabled:opacity-50 max-w-full ${
                      isSelectedStrong
                        ? "bg-accent-violet/15 text-purple-200 border-accent-violet/35 hover:border-accent-violet/60"
                        : "bg-bg-secondary/90 text-text-primary border-border-subtle hover:border-accent-cyan/45"
                    }`}
                  >
                    <span className="shrink-0">
                      {isSelectedStrong ? "🧠" : selectedOpt?.tier === "medium" ? "⚖️" : "⚡"}
                    </span>
                    <span className="truncate">
                      {selectedOpt?.label || activeModelLabel}
                    </span>
                    <svg
                      viewBox="0 0 24 24"
                      className={`w-3.5 h-3.5 text-text-muted shrink-0 transition-transform duration-150 ${
                        isModelMenuOpen ? "rotate-180" : ""
                      }`}
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </button>

                  {isModelMenuOpen && (
                    <div
                      role="listbox"
                      aria-label="Available models"
                      className="absolute left-0 bottom-full mb-2 w-72 sm:w-80 max-w-[calc(100vw-2rem)] rounded-xl bg-bg-secondary/95 backdrop-blur-md border border-border-subtle shadow-2xl p-1.5 z-50"
                    >
                      {modelOptions.map((opt) => {
                        const isSelected = selectedModelTier === opt.id;
                        const isStrong = opt.tier === "strong";
                        return (
                          <button
                            key={opt.id}
                            type="button"
                            role="option"
                            aria-selected={isSelected}
                            onClick={() => {
                              onSelectModelTier(opt.id);
                              setIsModelMenuOpen(false);
                            }}
                            className={`w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left transition-colors ${
                              isSelected
                                ? isStrong
                                  ? "bg-accent-violet/20 text-purple-200 border border-accent-violet/35"
                                  : "bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/35"
                                : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary border border-transparent"
                            }`}
                          >
                            <span className="text-sm mt-0.5 shrink-0">
                              {isStrong ? "🧠" : opt.tier === "medium" ? "⚖️" : "⚡"}
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-xs font-semibold truncate">{opt.label}</span>
                                {isSelected && <span className="text-xs shrink-0">✓</span>}
                              </div>
                              {opt.description && (
                                <p className="text-[0.68rem] text-text-muted leading-snug mt-0.5 line-clamp-2">
                                  {opt.description}
                                </p>
                              )}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </>
              );
            })()}
          </div>

          <div className="flex items-center gap-2 ml-auto shrink-0">
            {/* Hidden file input invoked by the paperclip attachment button */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif,image/bmp,application/pdf,.pdf"
              multiple
              onChange={(e) => {
                if (e.target.files) handleUploadFiles(e.target.files);
              }}
              className="hidden"
              id="chat-file-upload"
            />
            <button
              type="button"
              disabled={loading || isUploading}
              onClick={() => fileInputRef.current?.click()}
              title="Upload image or PDF document (PNG, JPG, WEBP, GIF, PDF)"
              aria-label="Upload file"
              className="flex items-center justify-center w-10 h-10 md:w-9 md:h-9 rounded-xl text-text-muted hover:text-accent-cyan hover:bg-accent-cyan/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
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
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </button>

            {loading ? (
              <button
                type="button"
                onClick={onStopAndRevert}
                title="Stop agent run and revert turn (Esc)"
                aria-label="Stop and revert turn"
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-rose-500/15 text-rose-400 hover:bg-rose-500/25 border border-rose-500/30 transition-all font-medium text-xs shadow-sm hover:scale-[1.02] active:scale-[0.98] shrink-0"
              >
                <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
                  <rect x="5" y="5" width="14" height="14" rx="2" />
                </svg>
                <span className="hidden sm:inline">Stop &amp; Revert</span>
                <span className="sm:hidden">Stop</span>
              </button>
            ) : (
              <button
                type="submit"
                disabled={
                  isUploading ||
                  (!localInput.trim() && pendingImages.length === 0)
                }
                title="Send message (Enter) • Newline (Shift+Enter)"
                className="flex items-center justify-center w-10 h-10 md:w-9 md:h-9 rounded-xl bg-accent-cyan/15 text-accent-cyan hover:bg-accent-cyan/25 transition-colors disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
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
            )}
          </div>
        </div>
      </div>
    </form>
  );
});

export default ChatInputBar;

