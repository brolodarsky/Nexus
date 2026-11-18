"use client";

/**
 * ConversationCacheModal.tsx — Read-only wide centered modal for inspecting
 * per-conversation external captures (`cache://tab/...`, `cache://web/...`, `cache://email/...`).
 * Fetches full capture bodies lazily via `/api/agents/ask/conversations/{id}/captures/item`
 * and renders verbatim Markdown safely via `MarkdownMessage`.
 */

import { useState, useMemo, useEffect, useDeferredValue } from "react";
import {
  getConversationCaptureItem,
  type ConversationCaptureSummary,
  type ConversationCaptureDetail,
} from "@/lib/api";
import MarkdownMessage from "@/components/MarkdownMessage";

// Props controlling the read-only Conversation Capture Cache modal
export interface ConversationCacheModalProps {
  conversationId: string;                     // Active conversation UUID scoping cache lookups
  conversationTitle?: string;                 // Optional display title rendered in the modal header subtitle
  captures: ConversationCaptureSummary[];     // Lightweight metadata entries loaded by parent ChatPage
  isRefreshingList: boolean;                  // True while the parent's metadata list refresh request is in flight
  onRefreshList: () => Promise<void> | void;  // Callback to re-fetch capture metadata for `conversationId`
  onClose: () => void;                        // Callback invoked on backdrop click, Escape key, or close button
}

// Visual pill color classes keyed by capture `source_type` token
const SOURCE_BADGE_CLASSES: Record<string, string> = {
  tab: "bg-accent-cyan/15 text-accent-cyan border-accent-cyan/30",
  web: "bg-accent-violet/15 text-purple-300 border-accent-violet/30",
  email: "bg-amber-500/15 text-amber-300 border-amber-500/30",
};

// Formats an ISO-8601 UTC timestamp string into concise local date/time text
function formatCaptureTimestamp(iso: string): string {
  if (!iso) return "";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// Guards clickable `source_url` links against non-HTTP(S) schemes (e.g. `javascript:` or `data:`)
function isSafeHttpUrl(url: string | null | undefined): url is string {
  if (!url) return false;
  return /^https?:\/\//i.test(url.trim());
}

export default function ConversationCacheModal({
  conversationId,
  conversationTitle,
  captures,
  isRefreshingList,
  onRefreshList,
  onClose,
}: ConversationCacheModalProps) {
  // searchQuery + deferredSearchQuery: keep typing responsive while filtering long capture lists
  const [searchQuery, setSearchQuery] = useState<string>("");
  const deferredSearchQuery = useDeferredValue(searchQuery);
  // selectedKey: explicitly clicked `cache_key`; falls back to first list entry when null/stale
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  // mobileView: toggles between list and reader panes on small viewports (`< md`)
  const [mobileView, setMobileView] = useState<"list" | "detail">("list");
  // detailByVersion: in-memory map keyed by `${conversationId}::${cache_key}::${created_at}` so updated captures auto-invalidate
  const [detailByVersion, setDetailByVersion] = useState<Record<string, ConversationCaptureDetail>>({});
  // detailError: holds fetch failure state scoped to the specific capture version key
  const [detailError, setDetailError] = useState<{ versionKey: string; message: string } | null>(null);
  // retrySeq: monotonic counter incremented to trigger a clean detail re-fetch after transient errors
  const [retrySeq, setRetrySeq] = useState<number>(0);

  // Close modal when user presses Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  // Filter capture summaries by title, `cache://` key, source type, or URL
  const filteredCaptures = useMemo(() => {
    const q = deferredSearchQuery.trim().toLowerCase();
    if (!q) return captures;
    return captures.filter((item) => {
      return (
        item.title.toLowerCase().includes(q) ||
        item.cache_key.toLowerCase().includes(q) ||
        item.source_type.toLowerCase().includes(q) ||
        (item.source_url ?? "").toLowerCase().includes(q)
      );
    });
  }, [captures, deferredSearchQuery]);

  // Derive active selection without mutating state inside `useEffect` (keeps selection valid when list updates)
  const effectiveSelectedSummary = useMemo<ConversationCaptureSummary | null>(() => {
    if (captures.length === 0) return null;
    if (selectedKey) {
      const explicit = captures.find((c) => c.cache_key === selectedKey);
      if (explicit) return explicit;
    }
    return filteredCaptures[0] ?? captures[0] ?? null;
  }, [captures, filteredCaptures, selectedKey]);

  const activeVersionKey = effectiveSelectedSummary
    ? `${conversationId}::${effectiveSelectedSummary.cache_key}::${effectiveSelectedSummary.created_at}`
    : null;
  const activeDetail = activeVersionKey ? (detailByVersion[activeVersionKey] ?? null) : null;
  const activeError =
    activeVersionKey && detailError?.versionKey === activeVersionKey ? detailError.message : null;
  const isLoadingDetail = Boolean(activeVersionKey && !activeDetail && !activeError);

  // Lazily fetch the full verbatim body for the currently selected capture when absent from `detailByVersion`
  useEffect(() => {
    if (!effectiveSelectedSummary || !activeVersionKey) return;
    if (detailByVersion[activeVersionKey]) return;

    // cancelled: guards async completion against committing state after unmount or selection change
    let cancelled = false;
    const targetKey = effectiveSelectedSummary.cache_key;
    const versionKey = activeVersionKey;

    async function loadCaptureDetail() {
      try {
        const detail = await getConversationCaptureItem(conversationId, targetKey);
        if (cancelled) return;
        setDetailByVersion((prev) => ({ ...prev, [versionKey]: detail }));
        setDetailError((prev) => (prev?.versionKey === versionKey ? null : prev));
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "Failed to load cached capture content.";
        setDetailError({ versionKey, message });
      }
    }

    void loadCaptureDetail();
    return () => {
      cancelled = true;
    };
  }, [conversationId, effectiveSelectedSummary, activeVersionKey, detailByVersion, retrySeq]);

  const handleSelectCapture = (cacheKey: string) => {
    setSelectedKey(cacheKey);
    setMobileView("detail");
  };

  const handleRefresh = () => {
    setDetailError(null);
    setRetrySeq((n) => n + 1);
    void onRefreshList();
  };

  const handleRetryDetail = () => {
    setDetailError(null);
    setRetrySeq((n) => n + 1);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Conversation Capture Cache"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 md:p-6 bg-black/70 backdrop-blur-md animate-fade-in-up"
      onClick={onClose}
    >
      <div
        className="w-full max-w-5xl h-[85vh] glass-card border border-border-accent/40 bg-bg-secondary flex flex-col rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Modal Header ──────────────────────────────────────────────────── */}
        <div className="px-4 md:px-5 py-3.5 border-b border-border-subtle bg-bg-surface/50 flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="p-1.5 rounded-lg bg-accent-cyan/10 border border-accent-cyan/30 text-accent-cyan shrink-0">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <ellipse cx="12" cy="5" rx="9" ry="3" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
              </svg>
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-text-primary truncate">
                  Conversation Cache
                </h2>
                <span className="text-[0.7rem] font-mono px-2 py-0.5 rounded-full bg-bg-tertiary text-accent-cyan border border-border-subtle shrink-0">
                  {captures.length}
                </span>
              </div>
              {conversationTitle && (
                <p className="text-[0.7rem] text-text-muted truncate">{conversationTitle}</p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={isRefreshingList}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border border-border-subtle bg-bg-surface/70 text-text-secondary hover:text-text-primary hover:border-accent-cyan/40 transition-colors disabled:opacity-60"
              title="Refresh cached captures"
            >
              <svg
                className={`w-3.5 h-3.5 ${isRefreshingList ? "animate-spin text-accent-cyan" : ""}`}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              <span className="hidden sm:inline">Refresh</span>
            </button>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors"
              title="Close (Esc)"
              aria-label="Close cache viewer"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* ── Modal Body: Empty State or Two-Pane List + Reader ─────────────── */}
        {captures.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
            <div className="w-12 h-12 rounded-2xl bg-bg-surface border border-border-subtle flex items-center justify-center text-text-muted mb-3">
              <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}>
                <ellipse cx="12" cy="5" rx="9" ry="3" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
              </svg>
            </div>
            <p className="text-sm font-medium text-text-primary">
              No external captures cached in this conversation yet
            </p>
            <p className="text-xs text-text-muted max-w-md mt-1.5 leading-relaxed">
              Captures from <code className="font-mono text-text-secondary">read_browser_tabs</code>,{" "}
              <code className="font-mono text-text-secondary">read_webpage</code>, and{" "}
              <code className="font-mono text-text-secondary">fetch_emails</code> (or captures inherited
              from a parent branch) appear here automatically.
            </p>
          </div>
        ) : (
          <div className="flex-1 flex min-h-0 overflow-hidden">
            {/* Left Pane: Filterable Capture List */}
            <aside
              className={`w-full md:w-80 lg:w-96 shrink-0 md:border-r border-border-subtle flex-col bg-bg-surface/30 overflow-hidden ${
                mobileView === "list" ? "flex" : "hidden"
              } md:flex`}
            >
              <div className="p-3 border-b border-border-subtle/80 shrink-0">
                <div className="relative">
                  <svg
                    className="w-3.5 h-3.5 text-text-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <circle cx="11" cy="11" r="8" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Filter by title, key, type, or URL..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-8 pr-12 py-2 rounded-xl border border-border-subtle bg-bg-surface text-text-primary placeholder:text-text-muted text-xs focus:outline-none focus:border-accent-cyan transition-colors"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => setSearchQuery("")}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[0.7rem] text-text-muted hover:text-text-primary"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
                {filteredCaptures.length === 0 ? (
                  <div className="py-12 px-4 text-center text-xs text-text-muted">
                    No cached captures match &ldquo;{searchQuery}&rdquo;.
                  </div>
                ) : (
                  filteredCaptures.map((item) => {
                    const isSelected = effectiveSelectedSummary?.cache_key === item.cache_key;
                    const badgeStyle =
                      SOURCE_BADGE_CLASSES[item.source_type.toLowerCase()] ??
                      "bg-bg-tertiary text-text-secondary border-border-subtle";
                    return (
                      <button
                        key={item.cache_key}
                        type="button"
                        onClick={() => handleSelectCapture(item.cache_key)}
                        className={`w-full text-left p-3 rounded-xl border transition-all ${
                          isSelected
                            ? "bg-accent-cyan/10 border-accent-cyan/40 shadow-sm"
                            : "bg-bg-surface/40 border-border-subtle/50 hover:bg-bg-surface/80 hover:border-border-subtle"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span
                            className={`text-[0.65rem] font-mono uppercase px-1.5 py-0.5 rounded border ${badgeStyle}`}
                          >
                            {item.source_type}
                          </span>
                          <span className="text-[0.65rem] text-text-muted font-mono shrink-0">
                            {item.char_count.toLocaleString()} chars
                          </span>
                        </div>
                        <div className="text-xs font-semibold text-text-primary truncate">
                          {item.title}
                        </div>
                        <div className="text-[0.68rem] font-mono text-text-secondary truncate mt-0.5">
                          {item.cache_key}
                        </div>
                        <div className="text-[0.65rem] text-text-muted mt-1">
                          {formatCaptureTimestamp(item.created_at)}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </aside>

            {/* Right Pane: Rendered Markdown Capture Reader */}
            <section
              className={`flex-1 min-w-0 flex-col overflow-hidden bg-bg-primary/20 ${
                mobileView === "detail" ? "flex" : "hidden"
              } md:flex`}
            >
              {effectiveSelectedSummary ? (
                <>
                  {/* Mobile back navigation bar */}
                  <div className="md:hidden px-4 py-2 border-b border-border-subtle bg-bg-surface/40 shrink-0">
                    <button
                      type="button"
                      onClick={() => setMobileView("list")}
                      className="text-xs font-medium text-accent-cyan hover:underline flex items-center gap-1"
                    >
                      <span>←</span>
                      <span>Back to captures</span>
                    </button>
                  </div>

                  {/* Capture metadata banner */}
                  <div className="px-5 py-3.5 border-b border-border-subtle bg-bg-surface/30 shrink-0 space-y-1.5">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="text-sm md:text-base font-bold text-text-primary break-words min-w-0">
                        {effectiveSelectedSummary.title}
                      </h3>
                      <span
                        className={`text-[0.65rem] font-mono uppercase px-2 py-0.5 rounded border shrink-0 ${
                          SOURCE_BADGE_CLASSES[effectiveSelectedSummary.source_type.toLowerCase()] ??
                          "bg-bg-tertiary text-text-secondary border-border-subtle"
                        }`}
                      >
                        {effectiveSelectedSummary.source_type}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.7rem] text-text-muted">
                      <code className="font-mono text-accent-cyan/90 break-all">
                        {effectiveSelectedSummary.cache_key}
                      </code>
                      <span>·</span>
                      <span className="font-mono">
                        {effectiveSelectedSummary.char_count.toLocaleString()} chars
                      </span>
                      <span>·</span>
                      <span>{formatCaptureTimestamp(effectiveSelectedSummary.created_at)}</span>
                    </div>

                    {isSafeHttpUrl(effectiveSelectedSummary.source_url) && (
                      <div className="text-[0.7rem] truncate">
                        <a
                          href={effectiveSelectedSummary.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent-cyan hover:underline break-all"
                          title={effectiveSelectedSummary.source_url}
                        >
                          {effectiveSelectedSummary.source_url}
                        </a>
                      </div>
                    )}
                  </div>

                  {/* Scrollable verbatim Markdown content */}
                  <div className="flex-1 overflow-y-auto p-5 md:p-6 min-w-0">
                    {isLoadingDetail ? (
                      <div className="py-16 flex flex-col items-center justify-center text-text-muted gap-2">
                        <span className="w-5 h-5 border-2 border-accent-cyan/30 border-t-accent-cyan rounded-full animate-spin" />
                        <span className="text-xs">Loading cached capture...</span>
                      </div>
                    ) : activeError ? (
                      <div className="p-4 rounded-xl border border-red-500/30 bg-red-500/10 text-xs text-red-300 flex items-center justify-between gap-3">
                        <span>{activeError}</span>
                        <button
                          type="button"
                          onClick={handleRetryDetail}
                          className="px-2.5 py-1 rounded-lg border border-red-400/40 hover:bg-red-500/20 text-red-200 font-medium shrink-0"
                        >
                          Retry
                        </button>
                      </div>
                    ) : activeDetail ? (
                      <>
                        {/* TODO: Add an optional toggle button to inspect raw verbatim capture text in addition to rendered Markdown */}
                        <MarkdownMessage content={activeDetail.content} openInNewTab={true} />
                      </>
                    ) : null}
                  </div>
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center p-8 text-xs text-text-muted">
                  Select a capture from the list to inspect its cached content.
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
