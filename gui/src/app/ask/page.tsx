"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { askBrainStream } from "@/lib/api";
import type { TraceEvent } from "@/lib/api";

// ── Types ────────────────────────────────────────────────────

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  agent?: string;
  domain?: string | null;
  confidence?: number | null;
  trace?: TraceEvent[];
}

// ── Icon map for trace event types ───────────────────────────

const TRACE_ICONS: Record<string, string> = {
  agent_start: "▶",
  agent_end: "■",
  llm_call: "🤖",
  llm_response: "💬",
  tool_call: "🔧",
  tool_result: "✅",
  tool_error: "❌",
  route: "🔀",
  delegate: "📤",
  info: "ℹ️",
};

// Agent color → Tailwind text class
const AGENT_COLORS: Record<string, string> = {
  yellow: "text-amber-400",
  cyan: "text-cyan-400",
  green: "text-emerald-400",
  magenta: "text-fuchsia-400",
  blue: "text-blue-400",
  red: "text-red-400",
  white: "text-zinc-300",
};

// ── Thinking Panel (collapsible trace log) ───────────────────

function ThinkingPanel({
  events,
  isLive,
  defaultExpanded = true,
}: {
  events: TraceEvent[];
  isLive: boolean;
  defaultExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll while live
  useEffect(() => {
    if (expanded && isLive && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, expanded, isLive]);

  // Auto-collapse when pipeline finishes
  useEffect(() => {
    if (!isLive && events.length > 0) {
      setExpanded(false);
    }
  }, [isLive, events.length]);

  if (events.length === 0) return null;

  return (
    <div className="mt-2 rounded-xl border border-border-subtle/50 overflow-hidden">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-[0.65rem] font-medium text-text-muted hover:text-text-secondary transition-colors"
      >
        <svg
          className={`w-3 h-3 transition-transform ${expanded ? "rotate-90" : ""}`}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path d="M9 18l6-6-6-6" />
        </svg>
        {isLive ? (
          <span className="inline-flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-pulse" />
            Thinking… ({events.length} steps)
          </span>
        ) : (
          <span>Pipeline trace ({events.length} steps)</span>
        )}
      </button>

      {expanded && (
        <div
          ref={scrollRef}
          className="max-h-48 overflow-y-auto px-3 pb-2 space-y-0.5 border-t border-border-subtle/30"
        >
          {events.map((evt, i) => {
            const icon = TRACE_ICONS[evt.type] ?? "·";
            const colorClass = AGENT_COLORS[evt.color ?? "white"] ?? "text-zinc-300";

            return (
              <div
                key={i}
                className="flex items-start gap-2 text-[0.65rem] leading-relaxed font-mono"
              >
                <span className="shrink-0 w-4 text-center">{icon}</span>
                <span className={`shrink-0 font-semibold ${colorClass}`}>
                  [{evt.agent ?? "System"}]
                </span>
                <span className="text-text-muted break-all">{evt.message}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main Page Component ──────────────────────────────────────

export default function AskBrainPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [liveTrace, setLiveTrace] = useState<TraceEvent[]>([]);
  const liveTraceRef = useRef<TraceEvent[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<(() => void) | null>(null);

  // Auto-scroll to bottom when new messages arrive or trace updates
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, liveTrace]);

  // Auto-focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Clean up abort on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.();
    };
  }, []);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const query = input.trim();
      if (!query || loading) return;

      const userMsg: Message = {
        role: "user",
        content: query,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setLoading(true);
      setLiveTrace([]);
      liveTraceRef.current = [];

      const abort = askBrainStream(query, {
        onTrace: (event) => {
          setLiveTrace((prev) => {
            const newTrace = [...prev, event];
            liveTraceRef.current = newTrace;
            return newTrace;
          });
        },
        onDone: (event) => {
          // Build the final message with the full trace attached
          // The "done" event carries agent/domain/confidence at the top level
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const doneEvt = event as any;
          const assistantMsg: Message = {
            role: "assistant",
            content: event.response ?? "",
            timestamp: new Date(event.timestamp),
            agent: doneEvt.agent as string | undefined,
            domain: doneEvt.domain as string | null,
            confidence: doneEvt.confidence as number | null,
            trace: liveTraceRef.current,
          };
          setMessages((msgs) => [...msgs, assistantMsg]);
          setLiveTrace([]);
          liveTraceRef.current = [];
          setLoading(false);
          abortRef.current = null;
          inputRef.current?.focus();
        },
        onError: (errorMessage) => {
          const errorMsg: Message = {
            role: "assistant",
            content: `❌ ${errorMessage}`,
            timestamp: new Date(),
            trace: liveTraceRef.current.length > 0 ? liveTraceRef.current : undefined,
          };
          setMessages((msgs) => [...msgs, errorMsg]);
          setLiveTrace([]);
          liveTraceRef.current = [];
          setLoading(false);
          abortRef.current = null;
          inputRef.current?.focus();
        },
      });

      abortRef.current = abort;
    },
    [input, loading]
  );

  return (
    <div className="flex flex-col h-full max-h-screen">
      {/* ── Header ────────────────────────────────────────── */}
      <header className="px-8 py-6 border-b border-border-subtle shrink-0">
        <h1 className="text-2xl font-bold tracking-tight">
          <span className="gradient-text">Ask Brain</span>
        </h1>
        <p className="text-text-secondary mt-1 text-sm">
          Queries route through the Content Router to the right domain agent.
        </p>
      </header>

      {/* ── Message Thread ────────────────────────────────── */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-8 py-6 space-y-5"
      >
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center opacity-60">
            <span className="text-5xl mb-4">🧠</span>
            <p className="text-text-secondary text-sm max-w-md">
              Hi Bill! How can I help you today?
            </p>
            <div className="flex flex-wrap gap-2 mt-6 justify-center">
              {[
                "What are my active projects?",
                "Summarize my career strategy",
                "What medical appointments are upcoming?",
              ].map((example) => (
                <button
                  key={example}
                  onClick={() => setInput(example)}
                  className="glass-card px-4 py-2 text-xs text-text-secondary hover:text-accent-cyan transition-colors"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-2xl rounded-2xl px-5 py-3.5 text-sm leading-relaxed ${msg.role === "user"
                ? "bg-accent-cyan/10 border border-accent-cyan/20 text-text-primary"
                : "glass-card text-text-primary"
                }`}
            >
              {msg.role === "assistant" && msg.agent && (
                <span className="inline-flex items-center gap-1.5 mb-2 px-2.5 py-0.5 rounded-full text-[0.65rem] font-medium bg-accent-cyan/10 border border-accent-cyan/20 text-accent-cyan">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan" />
                  {msg.agent === "career" ? "Career Agent" : "Librarian"}
                  {msg.domain && <span className="text-text-muted">• {msg.domain}</span>}
                  {msg.confidence != null && <span className="text-text-muted">• {Math.round(msg.confidence * 100)}%</span>}
                </span>
              )}
              <pre className="whitespace-pre-wrap font-sans">{msg.content}</pre>

              {/* Persisted trace log (collapsed by default for past messages) */}
              {msg.role === "assistant" && msg.trace && msg.trace.length > 0 && (
                <ThinkingPanel
                  events={msg.trace}
                  isLive={false}
                  defaultExpanded={false}
                />
              )}

              <span className="block mt-2 text-[0.65rem] text-text-muted">
                {msg.timestamp.toLocaleTimeString(undefined, {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
          </div>
        ))}

        {/* Live thinking panel while streaming */}
        {loading && (
          <div className="flex justify-start">
            <div className="glass-card px-5 py-3.5 text-sm text-text-secondary max-w-2xl w-full">
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
                <span className="ml-2">Routing query…</span>
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

      {/* ── Input Bar ─────────────────────────────────────── */}
      <form
        onSubmit={handleSubmit}
        className="px-8 py-5 border-t border-border-subtle shrink-0"
      >
        <div className="flex items-center gap-3 glass-card px-4 py-2.5">
          <span className="text-lg text-text-muted">💬</span>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask your brain anything..."
            disabled={loading}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none disabled:opacity-50"
            id="ask-brain-input"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="flex items-center justify-center w-9 h-9 rounded-xl bg-accent-cyan/15 text-accent-cyan hover:bg-accent-cyan/25 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
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
      </form>
    </div>
  );
}
