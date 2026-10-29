"use client";

/**
 * page.tsx (`/chat`) — Route orchestrator for the Nexus Chat workspace.
 * Coordinates conversation thread state, SSE streaming (`askBrainStream`), per-turn model tier
 * selection, unsubmitted draft persistence, and Shared Agent Blackboard synchronization,
 * delegating all UI presentation to modular subcomponents in `@/components/chat`.
 */

import { useState, useRef, useEffect, useCallback } from "react";
import {
  askBrainStream,
  getAvailableModels,
  getChatHistory,
  getConversations,
  createConversation,
  deleteConversation,
  getBoardBulletins,
  clearBoardBulletins,
  deleteBoardBulletin,
  type Conversation,
  type TraceEvent,
  type BoardBulletin,
  type ModelOption,
} from "@/lib/api";
import {
  ChatSidebar,
  ChatHeader,
  ChatMessageThread,
  ChatInputBar,
  BlackboardDrawer,
  FALLBACK_MODELS,
  MODEL_STORAGE_KEY,
  CHAT_DRAFT_STORAGE_KEY,
  ACTIVE_CONV_STORAGE_KEY,
  CHAT_SIDEBAR_COLLAPSED_KEY,
  CHAT_BOARD_OPEN_KEY,
  extractTurnModelInfo,
  type Message,
} from "@/components/chat";

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [liveTrace, setLiveTrace] = useState<TraceEvent[]>([]);
  // Shared Agent Blackboard state: live bulletins posted by Flash subagents and Astra
  const [bulletins, setBulletins] = useState<BoardBulletin[]>([]);
  const [showBoard, setShowBoard] = useState<boolean>(true);
  // isSidebarCollapsed: toggles the left conversation history menu between full width (w-64) and compact rail (w-14)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);
  // Per-turn model selection state: catalog of available models from `/api/agents/models` + currently selected tier
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(FALLBACK_MODELS);
  const [selectedModelTier, setSelectedModelTier] = useState<string>("strong");

  const liveTraceRef = useRef<TraceEvent[]>([]);
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
    queueMicrotask(() => {
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

      // Restore left conversation history sidebar collapse state from localStorage so panel choice survives tab navigation
      try {
        const savedSidebarCollapsed = localStorage.getItem(CHAT_SIDEBAR_COLLAPSED_KEY);
        if (savedSidebarCollapsed !== null) {
          setIsSidebarCollapsed(savedSidebarCollapsed === "true");
        }
      } catch {
        // Gracefully fall back to default expanded state if storage is inaccessible
      }

      // Restore right Subagent Blackboard drawer visibility from localStorage so drawer choice survives tab navigation
      try {
        const savedBoardOpen = localStorage.getItem(CHAT_BOARD_OPEN_KEY);
        if (savedBoardOpen !== null) {
          setShowBoard(savedBoardOpen === "true");
        }
      } catch {
        // Gracefully fall back to default open drawer if storage is inaccessible
      }
      isHydratedRef.current = true;
    });

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
      queueMicrotask(() => setMessages([]));
      return;
    }
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) setLoading(true);
    });
    getChatHistory(activeConvId)
      .then((history) => {
        if (cancelled) return;
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
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeConvId]);

  // Auto-focus input when switching conversations
  useEffect(() => {
    inputRef.current?.focus();
  }, [activeConvId]);

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

  // Persist active conversation ID so switching Nexus tabs (e.g., Chat -> Brain Explorer -> Chat) restores the same active chat
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

  const handleNewChat = useCallback(
    (initialTier?: string) => {
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
    },
    [handleSelectModelTier]
  );

  const handleDeleteChat = useCallback(
    async (id: string, e: React.MouseEvent) => {
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
    },
    [conversations, activeConvId]
  );

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
            const doneEvt = event as unknown as Record<string, unknown>;
            const { modelTier, modelName } = extractTurnModelInfo(
              liveTraceRef.current,
              (doneEvt.model_tier as string | null) ?? null,
              (doneEvt.model_name as string | null) ?? null
            );
            const assistantMsg: Message = {
              role: "assistant",
              content: event.response ?? "",
              timestamp: new Date(event.timestamp),
              agent: doneEvt.agent as string | undefined,
              domain: (doneEvt.domain as string | null) ?? null,
              confidence: (doneEvt.confidence as number | null) ?? null,
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
            getConversations().then(setConversations);
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

  const handleClearBoard = useCallback(async () => {
    await clearBoardBulletins();
    refreshBoard();
  }, [refreshBoard]);

  const handleDismissBulletin = useCallback(
    async (id: number) => {
      await deleteBoardBulletin(id);
      refreshBoard();
    },
    [refreshBoard]
  );

  // handleToggleSidebarCollapse: memoized handler to toggle left conversation history menu and persist choice
  const handleToggleSidebarCollapse = useCallback((collapsed: boolean) => {
    setIsSidebarCollapsed(collapsed);
    try {
      localStorage.setItem(CHAT_SIDEBAR_COLLAPSED_KEY, String(collapsed));
    } catch {
      // Ignore quota/privacy errors in restricted browser contexts
    }
  }, []);

  // handleToggleBoard: memoized handler to toggle right Subagent Blackboard drawer and persist choice
  const handleToggleBoard = useCallback(() => {
    setShowBoard((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(CHAT_BOARD_OPEN_KEY, String(next));
      } catch {
        // Ignore quota/privacy errors in restricted browser contexts
      }
      return next;
    });
  }, []);

  // handleCloseBoard: memoized handler to collapse/close right Subagent Blackboard drawer and persist choice
  const handleCloseBoard = useCallback(() => {
    setShowBoard(false);
    try {
      localStorage.setItem(CHAT_BOARD_OPEN_KEY, "false");
    } catch {
      // Ignore quota/privacy errors in restricted browser contexts
    }
  }, []);

  const activeConv = conversations.find((c) => c.id === activeConvId);
  const activeModelOption =
    modelOptions.find((m) => m.id === selectedModelTier) ?? modelOptions[0];
  const activeModelLabel = activeModelOption?.label ?? selectedModelTier;

  return (
    <div className="flex h-full max-h-screen">
      {/* ── Collapsible Conversation History Sidebar Menu ──── */}
      <ChatSidebar
        conversations={conversations}
        activeConvId={activeConvId}
        isCollapsed={isSidebarCollapsed}
        modelOptions={modelOptions}
        selectedModelTier={selectedModelTier}
        onToggleCollapse={handleToggleSidebarCollapse}
        onSelectConversation={setActiveConvId}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
      />

      {/* ── Main Chat Area ──────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">
        <ChatHeader
          title={activeConv?.title}
          showBoard={showBoard}
          bulletinCount={bulletins.length}
          onToggleBoard={handleToggleBoard}
        />

        <ChatMessageThread
          messages={messages}
          loading={loading}
          liveTrace={liveTrace}
          activeModelLabel={activeModelLabel}
          onSelectPromptSuggestion={setInput}
        />

        <ChatInputBar
          input={input}
          loading={loading}
          modelOptions={modelOptions}
          selectedModelTier={selectedModelTier}
          activeModelLabel={activeModelLabel}
          inputRef={inputRef}
          onChangeInput={setInput}
          onSelectModelTier={handleSelectModelTier}
          onSubmit={handleSubmit}
        />
      </div>

      {/* ── Right Drawer: Shared Subagent Blackboard (`blackboard.db`) ───────── */}
      {showBoard && (
        <BlackboardDrawer
          bulletins={bulletins}
          onRefresh={refreshBoard}
          onClear={handleClearBoard}
          onDismiss={handleDismissBulletin}
          onClose={handleCloseBoard}
        />
      )}
    </div>
  );
}

