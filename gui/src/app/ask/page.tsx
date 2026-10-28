"use client";

import { useState, useRef, useEffect, useCallback } from "react";
// MarkdownMessage: Shared GFM + Obsidian [[Wiki-Link]] renderer (also used by the HITL Pre-Commit Preview)
import MarkdownMessage from "@/components/MarkdownMessage";
// ThinkingPanel & AgentGraphView: Lossless agent execution trace viewer with Graph View, full step payloads, and raw JSON
import { ThinkingPanel } from "@/components/AgentTraceVisualizer";
import { 
  askBrainStream, 
  getAvailableModels,
  getChatHistory, 
  getConversations, 
  createConversation, 
  deleteConversation, 
  resetConversationRouting,
  getBoardBulletins,
  clearBoardBulletins,
  deleteBoardBulletin,
  type Conversation,
  type TraceEvent,
  type BoardBulletin,
  type ModelOption,
} from "@/lib/api";

// ── Types & Constants ────────────────────────────────────────

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  agent?: string;
  domain?: string | null;
  confidence?: number | null;
  modelTier?: string | null;
  modelName?: string | null;
  trace?: TraceEvent[];
}

// LocalStorage key for remembering the user's selected model tier across page reloads
const MODEL_STORAGE_KEY = "nexus_chat_model_tier";

// LocalStorage key for preserving unsubmitted chat prompt drafts across Nexus tab navigation and reloads
const CHAT_DRAFT_STORAGE_KEY = "nexus_chat_input_draft";

// LocalStorage key for remembering the active conversation ID across Nexus tab navigation
const ACTIVE_CONV_STORAGE_KEY = "nexus_chat_active_conv_id";

// Immediate fallback catalog rendered before GET /api/agents/models resolves
const FALLBACK_MODELS: ModelOption[] = [
  {
    id: "strong",
    tier: "strong",
    model_name: "gemini-4-argon",
    label: "Strong (gemini-4-argon)",
    short_label: "Strong",
    description: "Deep reasoning & complex synthesis — Astra (gemini-4-argon)",
  },
  {
    id: "low",
    tier: "low",
    model_name: "gemini-3.8-flash",
    label: "Fast (gemini-3.8-flash)",
    short_label: "Fast",
    description: "High-speed, low-cost execution — Flash (gemini-3.8-flash)",
  },
];

// Extracts the model tier and model name executed during a turn from either explicit fields or persisted trace events
function extractTurnModelInfo(
  trace?: TraceEvent[],
  explicitTier?: string | null,
  explicitModel?: string | null
): { modelTier: string | null; modelName: string | null } {
  if (explicitTier || explicitModel) {
    return { modelTier: explicitTier ?? null, modelName: explicitModel ?? null };
  }
  if (!trace || trace.length === 0) {
    return { modelTier: null, modelName: null };
  }
  // Inspect root NexusAgent `agent_start` or `llm_call` trace events for `model_tier` and `model_name` metadata
  for (const evt of trace) {
    const isRoot = !evt.parent_id && (evt.agent_id === "nexus" || evt.agent === "NexusAgent" || !evt.agent_id);
    if (isRoot && (evt.type === "agent_start" || evt.type === "llm_call") && evt.data) {
      const tier = typeof evt.data.model_tier === "string" ? evt.data.model_tier : null;
      const name = typeof evt.data.model_name === "string" ? evt.data.model_name : null;
      if (tier || name) {
        return { modelTier: tier, modelName: name };
      }
    }
  }
  return { modelTier: null, modelName: null };
}

export default function AskBrainPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [liveTrace, setLiveTrace] = useState<TraceEvent[]>([]);
  // Shared Agent Blackboard state: live bulletins posted by Flash subagents and Astra
  const [bulletins, setBulletins] = useState<BoardBulletin[]>([]);
  const [showBoard, setShowBoard] = useState<boolean>(true);
  const [expandedBulletinIds, setExpandedBulletinIds] = useState<Record<number, boolean>>({});
  // isSidebarCollapsed: toggles the left conversation history menu between full width (w-64) and compact rail (w-14)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);
  // Per-turn model selection state: catalog of available models from `/api/agents/models` + currently selected tier
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(FALLBACK_MODELS);
  const [selectedModelTier, setSelectedModelTier] = useState<string>("strong");
  
  const liveTraceRef = useRef<TraceEvent[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  // inputRef: HTMLTextAreaElement reference allowing programmatic focus management and dynamic height auto-expansion
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  // isHydratedRef: guards against overwriting saved localStorage drafts with initial empty state during hydration
  const isHydratedRef = useRef<boolean>(false);

  // Helper to fetch recent bulletins from `/api/board`
  const refreshBoard = useCallback(() => {
    getBoardBulletins(25)
      .then((res) => setBulletins(res.bulletins || []))
      .catch((err) => console.error("Failed to load Blackboard bulletins:", err));
  }, []);

  // Fetch conversations, selectable model catalog, initial Blackboard bulletins, and restore draft state on mount
  useEffect(() => {
    try {
      const savedTier = localStorage.getItem(MODEL_STORAGE_KEY);
      if (savedTier) {
        setSelectedModelTier(savedTier);
      }
    } catch {
      // Ignore storage access errors in restricted browser contexts
    }

    // Restore unsubmitted chat draft from localStorage so typed text survives Nexus tab navigation and reloads
    try {
      const savedDraft = localStorage.getItem(CHAT_DRAFT_STORAGE_KEY);
      if (savedDraft) {
        setInput(savedDraft);
      }
    } catch {
      // Gracefully ignore storage quota / access errors in private browsing contexts
    }
    isHydratedRef.current = true;

    getAvailableModels()
      .then((catalog) => {
        if (catalog.models && catalog.models.length > 0) {
          setModelOptions(catalog.models);
        }
        // Only apply backend default_tier if the user hasn't explicitly chosen a tier in localStorage
        try {
          if (!localStorage.getItem(MODEL_STORAGE_KEY) && catalog.default_tier) {
            setSelectedModelTier(catalog.default_tier);
          }
        } catch {
          if (catalog.default_tier) {
            setSelectedModelTier(catalog.default_tier);
          }
        }
      })
      .catch((err) => console.error("Failed to load available models:", err));

    getConversations().then((convos) => {
      setConversations(convos);
      if (convos.length > 0) {
        // Restore previously active conversation if it exists, maintaining context across tab navigation
        try {
          const savedActiveConv = localStorage.getItem(ACTIVE_CONV_STORAGE_KEY);
          if (savedActiveConv && convos.some((c) => c.id === savedActiveConv)) {
            setActiveConvId(savedActiveConv);
            return;
          }
        } catch {
          // Gracefully fallback to the most recent conversation
        }
        setActiveConvId(convos[0].id);
      }
    });
    refreshBoard();
  }, [refreshBoard]);

  // Persist user's per-turn model selection preference and keep input focused for immediate typing
  const handleSelectModelTier = useCallback((tierId: string) => {
    setSelectedModelTier(tierId);
    try {
      localStorage.setItem(MODEL_STORAGE_KEY, tierId);
    } catch {
      // Ignore storage quota errors
    }
    inputRef.current?.focus();
  }, []);

  // Fetch messages when active conversation changes
  useEffect(() => {
    if (!activeConvId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    getChatHistory(activeConvId)
      .then((history) => {
        setMessages(
          history.map((entry) => {
            const { modelTier, modelName } = extractTurnModelInfo(entry.trace);
            return {
              role: entry.role,
              content: entry.content,
              agent: entry.agent,
              domain: entry.domain,
              confidence: entry.confidence,
              modelTier,
              modelName,
              trace: entry.trace,
              timestamp: new Date(entry.timestamp),
            };
          })
        );
      })
      .catch((err) => console.error("Failed to load chat history:", err))
      .finally(() => setLoading(false));
  }, [activeConvId]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, liveTrace]);

  // Auto-focus input
  useEffect(() => {
    inputRef.current?.focus();
  }, [activeConvId]);

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
  }, [input]);

  // Sync unsubmitted input draft to localStorage on every change once hydration is complete
  useEffect(() => {
    if (!isHydratedRef.current) return;
    try {
      if (input) {
        localStorage.setItem(CHAT_DRAFT_STORAGE_KEY, input);
      } else {
        localStorage.removeItem(CHAT_DRAFT_STORAGE_KEY);
      }
    } catch {
      // Gracefully ignore storage quota / access errors in private browsing contexts
    }
  }, [input]);

  // Persist active conversation ID so switching Nexus tabs (e.g., Ask Brain -> Brain Explorer -> Ask Brain) restores the same active chat
  useEffect(() => {
    try {
      if (activeConvId) {
        localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, activeConvId);
      } else {
        localStorage.removeItem(ACTIVE_CONV_STORAGE_KEY);
      }
    } catch {
      // Gracefully ignore storage quota / access errors in private browsing contexts
    }
  }, [activeConvId]);

  // Clean up abort on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.();
    };
  }, []);

  const handleNewChat = async (initialTier?: string) => {
    if (initialTier) {
      handleSelectModelTier(initialTier);
    }
    setActiveConvId(null);
    setMessages([]);
    try {
      localStorage.removeItem(ACTIVE_CONV_STORAGE_KEY);
    } catch {
      // Ignore storage errors
    }
    inputRef.current?.focus();
  };

  const handleDeleteChat = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await deleteConversation(id);
    const updated = conversations.filter((c) => c.id !== id);
    setConversations(updated);
    if (activeConvId === id) {
      const nextId = updated.length > 0 ? updated[0].id : null;
      setActiveConvId(nextId);
      try {
        if (nextId) {
          localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, nextId);
        } else {
          localStorage.removeItem(ACTIVE_CONV_STORAGE_KEY);
        }
      } catch {
        // Ignore storage errors
      }
    }
  };

  const handleResetRouting = async () => {
    if (!activeConvId) return;
    await resetConversationRouting(activeConvId);
    setConversations(prev => prev.map(c => c.id === activeConvId ? { ...c, active_agent: null } : c));
  };

  const handleSubmit = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      const query = input.trim();
      if (!query || loading) return;

      let targetConvId = activeConvId;
      if (!targetConvId) {
        // Create new conversation on first message
        const title = query.slice(0, 30) + (query.length > 30 ? "..." : "");
        const res = await createConversation(title);
        targetConvId = res.conversation_id;
        setActiveConvId(targetConvId);
        try {
          localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, targetConvId);
        } catch {
          // Ignore storage errors
        }
        // Refresh conversations list to show the new one
        getConversations().then(setConversations);
      }

      const turnModelOption =
        modelOptions.find((m) => m.id === selectedModelTier) ?? modelOptions[0];
      const userMsg: Message = {
        role: "user",
        content: query,
        timestamp: new Date(),
        modelTier: turnModelOption?.tier ?? selectedModelTier,
        modelName: turnModelOption?.model_name ?? null,
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      try {
        localStorage.removeItem(CHAT_DRAFT_STORAGE_KEY);
      } catch {
        // Ignore storage errors
      }
      setLoading(true);
      setLiveTrace([]);
      liveTraceRef.current = [];

      const abort = askBrainStream(
        query,
        targetConvId,
        {
          onTrace: (event) => {
            setLiveTrace((prev) => {
              const newTrace = [...prev, event];
              liveTraceRef.current = newTrace;
              return newTrace;
            });
            // Live-refresh the Blackboard whenever a subagent posts a bulletin or completes
            if (
              event.message?.includes("Blackboard") ||
              event.data?.tool === "post_to_board" ||
              (event.agent === "Subagent" && event.type === "agent_end")
            ) {
              refreshBoard();
            }
          },
          onDone: (event) => {
            // Build the final message with the full trace and executed model metadata attached
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const doneEvt = event as any;
            const { modelTier, modelName } = extractTurnModelInfo(
              liveTraceRef.current,
              doneEvt.model_tier as string | null,
              doneEvt.model_name as string | null
            );
            const assistantMsg: Message = {
              role: "assistant",
              content: event.response ?? "",
              timestamp: new Date(event.timestamp),
              agent: doneEvt.agent as string | undefined,
              domain: doneEvt.domain as string | null,
              confidence: doneEvt.confidence as number | null,
              modelTier: modelTier ?? turnModelOption?.tier ?? selectedModelTier,
              modelName: modelName ?? turnModelOption?.model_name ?? null,
              trace: liveTraceRef.current,
            };
            setMessages((msgs) => [...msgs, assistantMsg]);
            setLiveTrace([]);
            liveTraceRef.current = [];
            setLoading(false);
            abortRef.current = null;
            inputRef.current?.focus();
            getConversations().then(setConversations); // refresh to update active agent status
            refreshBoard();
          },
          onError: (errorMessage) => {
            const errorMsg: Message = {
              role: "assistant",
              content: `❌ ${errorMessage}`,
              timestamp: new Date(),
              modelTier: turnModelOption?.tier ?? selectedModelTier,
              modelName: turnModelOption?.model_name ?? null,
              trace: liveTraceRef.current.length > 0 ? liveTraceRef.current : undefined,
            };
            setMessages((msgs) => [...msgs, errorMsg]);
            setLiveTrace([]);
            liveTraceRef.current = [];
            setLoading(false);
            abortRef.current = null;
            inputRef.current?.focus();
          },
        },
        selectedModelTier
      );

      abortRef.current = abort;
    },
    [input, loading, activeConvId, selectedModelTier, modelOptions, refreshBoard]
  );

  // Keyboard shortcut handler for multiline chat textarea:
  // - Enter (without Shift) triggers immediate submission
  // - Shift+Enter inserts a newline, allowing the user to type structured multi-paragraph prompts
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!loading && input.trim()) {
        handleSubmit();
      }
    }
  };

  const activeConv = conversations.find(c => c.id === activeConvId);
  const activeModelOption =
    modelOptions.find((m) => m.id === selectedModelTier) ?? modelOptions[0];

  return (
    <div className="flex h-full max-h-screen">
      {/* ── Collapsible Conversation History Sidebar Menu ──── */}
      {isSidebarCollapsed ? (
        // Collapsed Rail: Slim column with expand button, new chat icon, and conversation switcher
        <aside
          className="w-14 border-r border-border-subtle bg-bg-secondary flex flex-col items-center py-4 shrink-0 transition-all duration-300 ease-in-out select-none"
          aria-label="Collapsed Conversations Menu"
        >
          <button
            onClick={() => setIsSidebarCollapsed(false)}
            className="p-2 rounded-lg text-text-muted hover:text-accent-cyan hover:bg-bg-tertiary transition-colors flex items-center justify-center"
            title="Expand chat history"
            aria-label="Expand chat history"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            </svg>
          </button>

          {/* Compact New Chat Action */}
          <button
            onClick={() => handleNewChat()}
            className="mt-3 w-9 h-9 rounded-xl bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors flex items-center justify-center text-lg font-bold"
            title="Start New Chat"
            aria-label="Start New Chat"
          >
            +
          </button>

          {/* Conversation history icons for fast switching */}
          <div className="mt-4 flex-1 overflow-y-auto space-y-1.5 w-full px-2 flex flex-col items-center">
            {conversations.map((conv) => (
              <button
                key={conv.id}
                onClick={() => setActiveConvId(conv.id)}
                className={`w-9 h-9 rounded-lg flex items-center justify-center text-xs transition-all ${
                  activeConvId === conv.id
                    ? "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40 shadow-[0_0_10px_rgba(56,189,248,0.15)] font-bold"
                    : "text-text-muted hover:text-text-primary hover:bg-bg-tertiary"
                }`}
                title={conv.title}
              >
                💬
              </button>
            ))}
          </div>
        </aside>
      ) : (
        // Expanded Conversation Menu: Full titles, agent lock indicators, and delete actions
        <aside
          className="w-64 border-r border-border-subtle bg-bg-secondary flex flex-col shrink-0 transition-all duration-300 ease-in-out"
          aria-label="Conversations Menu"
        >
          <div className="p-4 border-b border-border-subtle space-y-2">
            <div className="flex items-center gap-2">
              <button 
                onClick={() => handleNewChat()}
                className="flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-xl bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20 transition-colors text-sm font-medium"
              >
                <span className="text-lg">+</span> New Chat
              </button>
              <button
                onClick={() => setIsSidebarCollapsed(true)}
                className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors shrink-0"
                title="Collapse chat history"
                aria-label="Collapse chat history"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                </svg>
              </button>
            </div>
            {/* Quick New Chat Model Preset Buttons (Strong vs. Fast/Low-Cost opening) */}
            <div className="flex items-center gap-1.5">
              {modelOptions.map((opt) => {
                const isSelected = selectedModelTier === opt.id;
                const isStrong = opt.tier === "strong";
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => handleNewChat(opt.id)}
                    title={`Open new chat with ${opt.description}`}
                    className={`flex-1 py-1 px-2 rounded-lg text-[0.68rem] font-medium border transition-all flex items-center justify-center gap-1 ${
                      isSelected
                        ? isStrong
                          ? "bg-accent-violet/15 border-accent-violet/40 text-purple-300"
                          : "bg-accent-cyan/15 border-accent-cyan/40 text-accent-cyan"
                        : "bg-bg-tertiary/50 border-border-subtle text-text-muted hover:text-text-secondary"
                    }`}
                  >
                    <span>{isStrong ? "🧠" : opt.tier === "medium" ? "⚖️" : "⚡"}</span>
                    <span className="truncate">{opt.short_label}</span>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => setActiveConvId(conv.id)}
                className={`group flex items-center justify-between px-3 py-2.5 rounded-lg cursor-pointer text-sm transition-colors ${
                  activeConvId === conv.id ? "bg-bg-tertiary text-text-primary" : "text-text-secondary hover:bg-bg-tertiary/50"
                }`}
              >
                <div className="flex flex-col overflow-hidden">
                  <span className="truncate font-medium">{conv.title}</span>
                  <span className="text-[0.65rem] text-text-muted mt-0.5">
                    {conv.active_agent ? `🔒 ${conv.active_agent}` : "🔀 Auto-Routing"}
                  </span>
                </div>
                <button 
                  onClick={(e) => handleDeleteChat(conv.id, e)}
                  className="opacity-0 group-hover:opacity-100 p-1 text-text-muted hover:text-red-400 transition-opacity"
                  title="Delete Chat"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </aside>
      )}

      {/* ── Main Chat Area ────────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* ── Header ────────────────────────────────────────── */}
        <header className="px-8 py-4 border-b border-border-subtle shrink-0 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight">
              <span className="gradient-text">{activeConv?.title || "Ask Brain"}</span>
            </h1>
            <p className="text-text-secondary mt-0.5 text-xs">
              Astra Primary Orchestrator • Flash Subagent Swarm • Shared Blackboard
            </p>
          </div>
          <div className="flex items-center gap-2">
            {activeConv?.active_agent && (
              <button
                onClick={handleResetRouting}
                className="text-xs px-3 py-1.5 rounded-lg bg-bg-tertiary text-text-secondary hover:text-text-primary transition-colors"
              >
                Reset Routing
              </button>
            )}
            <button
              onClick={() => setShowBoard((prev) => !prev)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 ${
                showBoard
                  ? "bg-accent-cyan/15 border-accent-cyan/30 text-accent-cyan"
                  : "bg-bg-tertiary border-border-subtle text-text-secondary hover:text-text-primary"
              }`}
              title="Toggle Shared Subagent Blackboard"
            >
              <span>📋</span>
              <span>Subagent Board</span>
              <span className="px-1.5 py-0.2 rounded-full bg-bg-primary/60 text-[0.65rem] font-mono">
                {bulletins.length}
              </span>
            </button>
          </div>
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
              className={`rounded-2xl px-5 py-3.5 text-sm leading-relaxed ${msg.role === "user"
                ? "max-w-2xl bg-accent-cyan/10 border border-accent-cyan/20 text-text-primary"
                : (msg.trace && msg.trace.length > 0)
                  ? "max-w-4xl xl:max-w-5xl w-full glass-card text-text-primary"
                  : "max-w-3xl glass-card text-text-primary"
                }`}
            >
              {msg.role === "assistant" && msg.agent && (
                <div className="flex items-center gap-1.5 flex-wrap mb-2.5">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[0.65rem] font-medium bg-accent-cyan/10 border border-accent-cyan/20 text-accent-cyan">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan" />
                    {msg.agent === "career"
                      ? "Career Agent"
                      : msg.agent === "librarian"
                        ? "Librarian"
                        : "NexusAgent"}
                    {msg.domain && <span className="text-text-muted">• {msg.domain}</span>}
                    {msg.confidence != null && <span className="text-text-muted">• {Math.round(msg.confidence * 100)}%</span>}
                  </span>
                  {(msg.modelName || msg.modelTier) && (
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[0.65rem] font-mono border ${
                        msg.modelTier === "strong"
                          ? "bg-accent-violet/15 border-accent-violet/30 text-purple-300"
                          : "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                      }`}
                      title={`Executed on ${msg.modelName ?? msg.modelTier} (${msg.modelTier ?? "default"} tier)`}
                    >
                      <span>{msg.modelTier === "strong" ? "🧠" : msg.modelTier === "medium" ? "⚖️" : "⚡"}</span>
                      <span>{msg.modelName ?? msg.modelTier}</span>
                    </span>
                  )}
                </div>
              )}
              {msg.role === "assistant" ? (
                <MarkdownMessage content={msg.content} />
              ) : (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              )}

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
            <div className="glass-card px-5 py-3.5 text-sm text-text-secondary max-w-4xl xl:max-w-5xl w-full">
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
                <span className="ml-2">
                  Routing query with{" "}
                  <span className="font-mono text-text-primary">
                    {activeModelOption?.label ?? selectedModelTier}
                  </span>
                  …
                </span>
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

      {/* ── Input Bar with Per-Turn Model Selector ──────────── */}
      <form
        onSubmit={handleSubmit}
        className="px-8 py-4 border-t border-border-subtle shrink-0"
      >
        <div className="glass-card p-3 rounded-2xl flex flex-col gap-2.5 border border-border-subtle focus-within:border-accent-cyan/40 transition-colors">
          <div className="flex items-start gap-3 px-1 pt-1">
            <span className="text-lg text-text-muted select-none mt-1">💬</span>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`Ask your brain anything (${activeModelOption?.label ?? selectedModelTier})...`}
              disabled={loading}
              rows={2}
              className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none resize-none leading-relaxed disabled:opacity-50 min-h-[56px] max-h-60 overflow-y-auto"
              id="ask-brain-input"
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
                    onClick={() => handleSelectModelTier(opt.id)}
                    title={opt.description}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5 disabled:opacity-50 ${
                      isSelected
                        ? isStrong
                          ? "bg-accent-violet/20 text-purple-300 border border-accent-violet/40 shadow-sm"
                          : "bg-accent-cyan/20 text-accent-cyan border border-accent-cyan/40 shadow-sm"
                        : "text-text-muted hover:text-text-primary border border-transparent"
                    }`}
                  >
                    <span>{isStrong ? "🧠" : opt.tier === "medium" ? "⚖️" : "⚡"}</span>
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
      </div>

      {/* ── Right Drawer: Shared Subagent Blackboard (`blackboard.db`) ───────── */}
      {showBoard && (
        <aside className="w-80 xl:w-96 border-l border-border-subtle bg-bg-secondary flex flex-col shrink-0 max-h-screen">
          <div className="p-4 border-b border-border-subtle flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-text-primary flex items-center gap-1.5">
                <span>📋</span>
                <span>Shared Agent Blackboard</span>
              </h2>
              <p className="text-[0.68rem] text-text-muted mt-0.5">
                Live findings from Flash subagents &amp; Astra
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => refreshBoard()}
                className="text-xs px-2 py-1 rounded-md bg-bg-tertiary text-text-secondary hover:text-accent-cyan transition-colors"
                title="Refresh Blackboard"
              >
                ↻
              </button>
              {bulletins.length > 0 && (
                <button
                  onClick={async () => {
                    await clearBoardBulletins();
                    refreshBoard();
                  }}
                  className="text-[0.68rem] px-2 py-1 rounded-md bg-bg-tertiary text-text-muted hover:text-red-400 transition-colors"
                  title="Clear unpinned bulletins"
                >
                  Clear
                </button>
              )}
              {/* Symmetrical drawer collapse toggle */}
              <button
                type="button"
                onClick={() => setShowBoard(false)}
                className="text-xs px-2 py-1 rounded-md bg-bg-tertiary text-text-muted hover:text-text-primary transition-colors flex items-center justify-center"
                title="Collapse Blackboard menu"
                aria-label="Collapse Blackboard menu"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Bulletin Feed */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
            {bulletins.length === 0 ? (
              <div className="text-center py-12 px-4 opacity-60">
                <div className="text-2xl mb-2">⚡</div>
                <p className="text-xs text-text-secondary">
                  No bulletins posted yet. When Astra dispatches Flash subagents for email, calendar, or Vault sweeps, their distilled reports land here automatically.
                </p>
              </div>
            ) : (
              bulletins.map((b) => {
                const isExpanded = expandedBulletinIds[b.id] ?? true;
                return (
                  <div
                    key={b.id}
                    className="rounded-xl border border-border-subtle bg-bg-tertiary/40 p-3 text-xs space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedBulletinIds((prev) => ({
                            ...prev,
                            [b.id]: !isExpanded,
                          }))
                        }
                        className="text-left flex-1 min-w-0"
                      >
                        <div className="flex items-center gap-1.5 flex-wrap mb-1">
                          {b.pinned ? (
                            <span className="text-[0.65rem]" title="Pinned bulletin">
                              📌
                            </span>
                          ) : null}
                          <span className="text-[0.65rem] text-purple-300 font-medium truncate">
                            {b.author}
                          </span>
                          <span className="text-[0.6rem] text-text-muted ml-auto">
                            #{b.id}
                          </span>
                        </div>
                        <div className="font-semibold text-text-primary leading-snug line-clamp-2">
                          {b.title}
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          await deleteBoardBulletin(b.id);
                          refreshBoard();
                        }}
                        className="text-text-muted hover:text-red-400 text-[0.65rem] px-1"
                        title="Dismiss bulletin"
                      >
                        ✕
                      </button>
                    </div>
                    {isExpanded && (
                      <div className="pt-1.5 border-t border-border-subtle/60 text-xs max-h-64 overflow-y-auto">
                        <MarkdownMessage content={b.content} />
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
