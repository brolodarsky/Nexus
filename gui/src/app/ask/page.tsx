"use client";

import { useState, useRef, useEffect } from "react";
import { askBrain } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  agent?: string;
  domain?: string | null;
  confidence?: number | null;
}

export default function AskBrainPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Auto-focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
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

    try {
      const data = await askBrain(query);
      const assistantMsg: Message = {
        role: "assistant",
        content: data.response,
        timestamp: new Date(data.timestamp),
        agent: data.agent,
        domain: data.domain,
        confidence: data.confidence,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg: Message = {
        role: "assistant",
        content: `❌ ${err instanceof Error ? err.message : "Failed to reach the engine."}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

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
        {messages.length === 0 && (
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
              <span className="block mt-2 text-[0.65rem] text-text-muted">
                {msg.timestamp.toLocaleTimeString(undefined, {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="glass-card px-5 py-3.5 text-sm text-text-secondary">
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
