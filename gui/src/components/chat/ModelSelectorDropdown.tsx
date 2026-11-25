"use client";

/**
 * ModelSelectorDropdown.tsx — Shared accessible model selector dropdown for Nexus Chat.
 * Instantiated in both `ChatSidebar` (opening downward) and `ChatInputBar` (opening upward),
 * with both instances bound to the same lifted `selectedModelTier` state in `ChatPage`.
 */

import { useState, useEffect, useRef, memo } from "react";
import type { ModelOption } from "@/lib/api";

// Union literal types (`"up" | "down"`) constrain `placement` at compile time to supported popover directions
export type ModelDropdownPlacement = "up" | "down";

// ModelSelectorDropdownProps: defines the shared model state, layout options, and selection callback
// - modelOptions: ordered ModelOption catalog returned by `GET /api/agents/models`
// - selectedModelTier: active model ID owned by parent `ChatPage` (single source of truth across sidebar & composer)
// - fallbackLabel: optional label displayed if `selectedModelTier` is not found in `modelOptions`
// - placement: popover opening direction (`"up"` above trigger in composer; `"down"` below trigger in sidebar)
// - fullWidth: stretches wrapper and trigger button across container width (used inside `ChatSidebar`)
// - disabled: disables the trigger button and forces the popover closed (e.g., during active streaming)
// - ariaLabel: accessible label announced by screen readers for the trigger button
// - onSelect: callback invoked with the chosen `opt.id` to update and persist lifted model state
export interface ModelSelectorDropdownProps {
  modelOptions: ModelOption[];
  selectedModelTier: string;
  fallbackLabel?: string;
  placement?: ModelDropdownPlacement;
  fullWidth?: boolean;
  disabled?: boolean;
  ariaLabel?: string;
  onSelect: (tierId: string) => void;
}

// Formats a rich hover tooltip containing the concrete model ID, full per-1M token rates (including cache read), and any caveat
function formatOptionTitle(opt: ModelOption): string {
  const parts: string[] = [opt.model_name];
  if (opt.pricing) {
    parts.push(
      `$${opt.pricing.input_per_m.toFixed(2)} in / $${opt.pricing.cached_per_m} cached / $${opt.pricing.output_per_m.toFixed(2)} out per 1M tokens`
    );
    if (opt.pricing.note) {
      parts.push(opt.pricing.note);
    }
  }
  return parts.join(" · ");
}

// memo: prevents re-renders unless model catalog, active tier, disabled flag, or callback identity changes
const ModelSelectorDropdown = memo(function ModelSelectorDropdown({
  modelOptions,
  selectedModelTier,
  fallbackLabel,
  placement = "up",
  fullWidth = false,
  disabled = false,
  ariaLabel = "Select model for this turn",
  onSelect,
}: ModelSelectorDropdownProps) {
  // Local popover open/closed state and container ref per mounted instance (prevents ref/state collisions across desktop sidebar, mobile drawer, and composer)
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Derive effective open state so becoming `disabled` (e.g., mid-stream) closes the popover immediately without an effect
  const isMenuOpen = isOpen && !disabled;

  // Attach global outside-click and Escape listeners only while this dropdown instance is open
  useEffect(() => {
    if (!isMenuOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      // Close when pointer lands outside this instance's wrapper (`contains` checks all descendant DOM nodes)
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // Stop propagation so pressing Escape to dismiss the dropdown does not bubble to `ChatPage`'s Stop & Revert shortcut
        e.stopPropagation();
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMenuOpen]);

  // Resolve active model descriptor via nullish coalescing (`??`) so a stale saved ID safely falls back to the first catalog entry
  const selectedOpt = modelOptions.find((m) => m.id === selectedModelTier) ?? modelOptions[0];
  const displayLabel = selectedOpt?.label || fallbackLabel || selectedModelTier;
  const placementClasses = placement === "down" ? "top-full mt-1.5" : "bottom-full mb-2";
  const triggerTitle = selectedOpt
    ? [
        selectedOpt.description,
        selectedOpt.pricing ? `${selectedOpt.pricing.summary} per 1M tokens` : null,
        selectedOpt.pricing?.note ?? null,
      ]
        .filter(Boolean)
        .join(" · ")
    : ariaLabel;

  return (
    <div className={`relative min-w-0 ${fullWidth ? "w-full" : ""}`} ref={menuRef}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        // ARIA listbox attributes announce interactive menu semantics and current open/closed state to assistive tech
        aria-haspopup="listbox"
        aria-expanded={isMenuOpen}
        aria-label={ariaLabel}
        title={triggerTitle}
        className={`${fullWidth ? "w-full justify-between " : ""}px-2.5 py-1.5 rounded-xl text-xs font-medium transition-colors flex items-center gap-2 border border-border-subtle bg-bg-secondary/90 text-text-primary hover:bg-bg-tertiary/70 hover:border-border-subtle/80 disabled:opacity-50 max-w-full`}
      >
        <span className="truncate">{displayLabel}</span>
        <svg
          viewBox="0 0 24 24"
          className={`w-3.5 h-3.5 text-text-muted shrink-0 transition-transform duration-150 ${
            isMenuOpen ? "rotate-180" : ""
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

      {isMenuOpen && (
        <div
          role="listbox"
          aria-label="Available models"
          className={`absolute left-0 ${placementClasses} w-80 sm:w-96 max-w-[calc(100vw-2rem)] max-h-[70vh] overflow-y-auto rounded-xl bg-bg-secondary/95 backdrop-blur-md border border-border-subtle shadow-2xl p-1.5 z-50`}
        >
          {/* Minimal menu header pairing "Model" label with the USD / 1M rate column legend */}
          <div className="flex items-center justify-between px-2.5 pt-1 pb-1.5">
            <span className="text-[0.7rem] font-medium text-text-muted">Model</span>
            <span className="text-[0.62rem] font-mono text-text-muted/75">
              USD / 1M (in / out)
            </span>
          </div>

          <div className="space-y-0.5">
            {modelOptions.map((opt, idx) => {
              const isSelected = selectedModelTier === opt.id;
              // Insert a subtle horizontal divider whenever the provider family switches (e.g., Gemini -> Claude)
              const prevProvider = idx > 0 ? modelOptions[idx - 1].provider : opt.provider;
              const showProviderDivider = idx > 0 && opt.provider !== prevProvider;

              return (
                <div
                  key={opt.id}
                  className={showProviderDivider ? "mt-1 pt-1 border-t border-border-subtle/50" : undefined}
                >
                  <button
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    title={formatOptionTitle(opt)}
                    onClick={() => {
                      onSelect(opt.id);
                      setIsOpen(false);
                    }}
                    className={`w-full flex items-center justify-between gap-2 px-2.5 py-2 rounded-lg text-left transition-colors ${
                      isSelected
                        ? "bg-bg-tertiary/90 text-text-primary"
                        : "text-text-secondary hover:text-text-primary hover:bg-bg-tertiary/55"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 min-w-0 flex-wrap">
                        <span
                          className={`text-xs truncate ${
                            isSelected ? "font-semibold text-text-primary" : "font-medium"
                          }`}
                        >
                          {opt.label}
                        </span>
                        {opt.pricing?.summary && (
                          <span className="text-[0.68rem] font-mono text-text-muted shrink-0">
                            {opt.pricing.summary}
                          </span>
                        )}
                        {opt.pricing?.note && (
                          <span className="px-1.5 py-0.5 rounded-full bg-bg-primary/60 border border-border-subtle/70 text-[0.6rem] font-mono text-text-muted shrink-0 leading-none">
                            {opt.pricing.note}
                          </span>
                        )}
                      </div>
                      {opt.description && (
                        <p className="text-[0.68rem] text-text-muted/85 leading-snug mt-0.5">
                          {opt.description}
                        </p>
                      )}
                    </div>

                    {isSelected && (
                      <svg
                        viewBox="0 0 24 24"
                        className="w-3.5 h-3.5 text-text-primary shrink-0"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
});

export default ModelSelectorDropdown;
