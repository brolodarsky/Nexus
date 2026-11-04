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
  updateConversationTitle,
  autoGenerateConversationTitle,
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
  ACTIVE_CONV_STORAGE_KEY,
  CHAT_SIDEBAR_COLLAPSED_KEY,
  CHAT_BOARD_OPEN_KEY,
  CHAT_INPUT_COLLAPSED_KEY,
  DRAFT_NEW_KEY,
  loadPersistedDrafts,
  persistDrafts,
  extractTurnModelInfo,
  extractTurnCost,
  type Message,
  type ChatDraftMap,
} from "@/components/chat";

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  // input: externally-driven composer seed value (updated on hydration, thread switch, prompt suggestion, or submit clear)
  const [input, setInput] = useState("");
  // inputSyncId: monotonic counter incremented whenever `ChatPage` programmatically overrides `input` in `ChatInputBar`
  const [inputSyncId, setInputSyncId] = useState<number>(0);
  // drafts: dictionary mapping conversation UUIDs (and DRAFT_NEW_KEY) to unsubmitted typed message drafts
  const [drafts, setDrafts] = useState<ChatDraftMap>({});
  const [loading, setLoading] = useState(false);
  const [liveTrace, setLiveTrace] = useState<TraceEvent[]>([]);
  // Shared Agent Blackboard state: live bulletins posted by Flash subagents and Astra
  const [bulletins, setBulletins] = useState<BoardBulletin[]>([]);
  const [showBoard, setShowBoard] = useState<boolean>(true);
  // isSidebarCollapsed: toggles the left conversation history menu between full width (w-64) and compact rail (w-14)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);
  // isInputCollapsed: toggles the bottom message bar between full multiline composer and compact collapsed rail
  const [isInputCollapsed, setIsInputCollapsed] = useState<boolean>(false);
  // Per-turn model selection state: catalog of available models from `/api/agents/models` + currently selected tier
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(FALLBACK_MODELS);
  const [selectedModelTier, setSelectedModelTier] = useState<string>("strong");

  const liveTraceRef = useRef<TraceEvent[]>([]);
  // currentInputRef: holds the live unsubmitted string in the composer so submit/switch callbacks read it without re-rendering ChatPage on every keystroke
  const currentInputRef = useRef<string>("");
  // draftsRef: mutable ref holding current drafts dictionary to avoid stale closures in event handlers
  const draftsRef = useRef<ChatDraftMap>({});
  // draftPersistTimerRef: debounce timer handle delaying synchronous localStorage writes while the user is actively typing
  const draftPersistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // inputRef: HTMLTextAreaElement reference allowing programmatic focus management and dynamic height auto-expansion
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  // isHydratedRef: guards against overwriting saved localStorage drafts with initial empty state during hydration
  const isHydratedRef = useRef<boolean>(false);

  // Programmatically sets the composer input value and increments `inputSyncId` so `ChatInputBar` snaps to `nextText`
  const setProgrammaticInput = useCallback((nextText: string) => {
    currentInputRef.current = nextText;
    setInput(nextText);
    setInputSyncId((prev) => prev + 1);
  }, []);

  // Flushes any pending debounced draft write immediately to localStorage
  const flushDraftPersistence = useCallback(() => {
    if (draftPersistTimerRef.current) {
      clearTimeout(draftPersistTimerRef.current);
      draftPersistTimerRef.current = null;
      persistDrafts(draftsRef.current);
    }
  }, []);

  // Helper to fetch recent bulletins from `/api/board` scoped to active conversation
  const refreshBoard = useCallback(() => {
    if (!activeConvId) {
      setBulletins([]);
      return;
    }
    getBoardBulletins(25, activeConvId)
      .then((res) => setBulletins(res.bulletins || []))
      .catch((err) => console.error("Failed to load Blackboard bulletins:", err));
  }, [activeConvId]);

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

      // Restore unsubmitted chat drafts mapped per conversation ID from localStorage
      const initialDrafts = loadPersistedDrafts();
      draftsRef.current = initialDrafts;
      setDrafts(initialDrafts);

      let savedActiveConv: string | null = null;
      try {
        savedActiveConv = localStorage.getItem(ACTIVE_CONV_STORAGE_KEY);
      } catch {
        // Gracefully ignore storage quota / access errors in private browsing contexts
      }

      // Optimistically restore active conversation's draft (or new chat draft) during hydration
      if (savedActiveConv === "__new__") {
        setActiveConvId(null);
        if (initialDrafts[DRAFT_NEW_KEY]) {
          setProgrammaticInput(initialDrafts[DRAFT_NEW_KEY]);
        }
      } else if (savedActiveConv && initialDrafts[savedActiveConv]) {
        setProgrammaticInput(initialDrafts[savedActiveConv]);
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

      // Restore bottom message bar collapse state from localStorage so panel choice survives tab navigation
      try {
        const savedInputCollapsed = localStorage.getItem(CHAT_INPUT_COLLAPSED_KEY);
        if (savedInputCollapsed !== null) {
          setIsInputCollapsed(savedInputCollapsed === "true");
        }
      } catch {
        // Gracefully fall back to default expanded state if storage is inaccessible
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
          if (savedActiveConv === "__new__") {
            setActiveConvId(null);
            setProgrammaticInput(draftsRef.current[DRAFT_NEW_KEY] ?? "");
            return;
          }
          if (savedActiveConv && convos.some((c) => c.id === savedActiveConv)) {
            setActiveConvId(savedActiveConv);
            setProgrammaticInput(draftsRef.current[savedActiveConv] ?? "");
            return;
          }
        } catch {
          // Gracefully fallback to the most recent conversation
        }
        setActiveConvId(convos[0].id);
        setProgrammaticInput(draftsRef.current[convos[0].id] ?? "");
      } else {
        setActiveConvId(null);
        setProgrammaticInput(draftsRef.current[DRAFT_NEW_KEY] ?? "");
      }
    });
  }, [setProgrammaticInput]);

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

  // Fetch messages and sync Blackboard bulletins when active conversation changes
  useEffect(() => {
    if (!activeConvId) {
      queueMicrotask(() => {
        setMessages([]);
        setBulletins([]);
      });
      return;
    }
    // Sync thread-isolated blackboard bulletins for this conversation
    getBoardBulletins(25, activeConvId)
      .then((res) => setBulletins(res.bulletins || []))
      .catch((err) => console.error("Failed to load Blackboard bulletins:", err));

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
            const costUsd = extractTurnCost(entry.trace, null, modelName, modelTier);
            return {
              role: entry.role,
              content: entry.content,
              agent: entry.agent,
              domain: entry.domain,
              confidence: entry.confidence,
              modelTier,
              modelName,
              costUsd,
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

  // Persist active conversation ID so switching Nexus tabs (e.g., Chat -> Brain Explorer -> Chat) restores the same active chat
  useEffect(() => {
    try {
      if (activeConvId) {
        localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, activeConvId);
      } else {
        localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, "__new__");
      }
    } catch {
      // Gracefully ignore storage quota / access errors in private browsing contexts
    }
  }, [activeConvId]);

  // Clean up SSE stream abort and flush any pending debounced draft writes on unmount or tab unload
  useEffect(() => {
    window.addEventListener("beforeunload", flushDraftPersistence);
    return () => {
      window.removeEventListener("beforeunload", flushDraftPersistence);
      flushDraftPersistence();
      abortRef.current?.();
    };
  }, [flushDraftPersistence]);

  // Updates current input ref and per-conversation draft map without re-rendering ChatPage on intermediate keystrokes,
  // and debounces synchronous localStorage persistence by 300ms so the typing event loop remains unblocked.
  const handleInputChange = useCallback(
    (value: string) => {
      currentInputRef.current = value;
      const key = activeConvId ?? DRAFT_NEW_KEY;
      const hadDraft = Boolean(draftsRef.current[key]?.trim());
      const hasDraft = Boolean(value.trim());

      const updated: ChatDraftMap = { ...draftsRef.current };
      if (hasDraft) {
        updated[key] = value;
      } else {
        delete updated[key];
      }
      draftsRef.current = updated;

      // Only trigger a React state update for `drafts` when the boolean presence of a draft flips (empty <-> non-empty),
      // so ChatSidebar's "Draft" badge appears/disappears on the first/last character without re-rendering on every character.
      if (hadDraft !== hasDraft) {
        setDrafts(updated);
      }

      if (draftPersistTimerRef.current) {
        clearTimeout(draftPersistTimerRef.current);
      }
      draftPersistTimerRef.current = setTimeout(() => {
        draftPersistTimerRef.current = null;
        persistDrafts(draftsRef.current);
      }, 300);
    },
    [activeConvId]
  );

  // Switches the active conversation thread, preserving the outgoing thread's draft and restoring the incoming thread's draft
  const handleSelectConversation = useCallback(
    (newConvId: string) => {
      if (newConvId === activeConvId) return;

      if (draftPersistTimerRef.current) {
        clearTimeout(draftPersistTimerRef.current);
        draftPersistTimerRef.current = null;
      }

      // 1. Commit outgoing conversation's draft (or _new if switching away from an unpersisted thread)
      const currentKey = activeConvId ?? DRAFT_NEW_KEY;
      const currentText = currentInputRef.current;
      const updated: ChatDraftMap = { ...draftsRef.current };
      if (currentText.trim()) {
        updated[currentKey] = currentText;
      } else {
        delete updated[currentKey];
      }
      draftsRef.current = updated;
      setDrafts(updated);
      persistDrafts(updated);

      // 2. Load the target conversation's draft (or blank if none exists)
      const nextDraft = updated[newConvId] ?? "";
      setProgrammaticInput(nextDraft);

      // 3. Switch active thread and persist selection
      setActiveConvId(newConvId);
      try {
        localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, newConvId);
      } catch {
        // Ignore storage errors in restricted browser contexts
      }
      inputRef.current?.focus();
    },
    [activeConvId, setProgrammaticInput]
  );

  // Starts a fresh blank conversation thread, preserving the outgoing thread's draft and restoring the new chat draft (if any)
  const handleNewChat = useCallback(
    (initialTier?: string) => {
      if (initialTier) {
        handleSelectModelTier(initialTier);
      }
      if (activeConvId === null) {
        // Already viewing the new chat composer
        inputRef.current?.focus();
        return;
      }

      if (draftPersistTimerRef.current) {
        clearTimeout(draftPersistTimerRef.current);
        draftPersistTimerRef.current = null;
      }

      // 1. Commit outgoing conversation's draft
      const currentKey = activeConvId;
      const currentText = currentInputRef.current;
      const updated: ChatDraftMap = { ...draftsRef.current };
      if (currentText.trim()) {
        updated[currentKey] = currentText;
      } else {
        delete updated[currentKey];
      }
      draftsRef.current = updated;
      setDrafts(updated);
      persistDrafts(updated);

      // 2. Restore new chat draft (or blank if none exists)
      const nextDraft = updated[DRAFT_NEW_KEY] ?? "";
      setProgrammaticInput(nextDraft);

      // 3. Reset active thread to null and persist new chat indicator
      setActiveConvId(null);
      setMessages([]);
      try {
        localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, "__new__");
      } catch {
        // Ignore storage errors in restricted browser contexts
      }
      inputRef.current?.focus();
    },
    [activeConvId, handleSelectModelTier, setProgrammaticInput]
  );

  const handleDeleteChat = useCallback(
    async (id: string, e: React.MouseEvent) => {
      e.stopPropagation();
      await deleteConversation(id);
      const updatedConvs = conversations.filter((c) => c.id !== id);
      setConversations(updatedConvs);

      if (draftPersistTimerRef.current) {
        clearTimeout(draftPersistTimerRef.current);
        draftPersistTimerRef.current = null;
      }

      // Prune the deleted conversation's draft from the map
      const updatedDrafts: ChatDraftMap = { ...draftsRef.current };
      delete updatedDrafts[id];
      draftsRef.current = updatedDrafts;
      setDrafts(updatedDrafts);
      persistDrafts(updatedDrafts);

      if (activeConvId === id) {
        const nextId = updatedConvs.length > 0 ? updatedConvs[0].id : null;
        setActiveConvId(nextId);
        const nextDraft = (nextId ? updatedDrafts[nextId] : updatedDrafts[DRAFT_NEW_KEY]) ?? "";
        setProgrammaticInput(nextDraft);
        try {
          if (nextId) {
            localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, nextId);
          } else {
            localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, "__new__");
          }
        } catch {
          // Ignore storage errors
        }
      }
    },
    [conversations, activeConvId, setProgrammaticInput]
  );

  // Updates the display title for a conversation in SQLite chats.db and synchronizes local UI state
  // - convId: UUID string identifying the target conversation row
  // - newTitle: trimmed new title string to persist
  const handleUpdateTitle = useCallback(async (convId: string, newTitle: string) => {
    const trimmed = newTitle.trim();
    if (!trimmed) return;
    // Optimistically update conversation title in state for instant UI feedback
    setConversations((prev) =>
      prev.map((c) => (c.id === convId ? { ...c, title: trimmed } : c))
    );
    try {
      await updateConversationTitle(convId, trimmed);
    } catch (err) {
      console.error("Failed to update conversation title:", err);
      // Reconcile against ground-truth database state on error
      getConversations().then(setConversations);
    }
  }, []);

  // Invokes fast AI auto-titling for an existing conversation using the low-tier Flash/Sonnet model
  const handleAutoGenerateTitle = useCallback(async (convId: string) => {
    try {
      const res = await autoGenerateConversationTitle(convId);
      if (res.title) {
        setConversations((prev) =>
          prev.map((c) => (c.id === convId ? { ...c, title: res.title! } : c))
        );
      }
    } catch (err) {
      console.error("Failed to auto-generate conversation title:", err);
    }
  }, []);

  const handleSubmit = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      const query = currentInputRef.current.trim();
      if (!query || loading) return;

      if (draftPersistTimerRef.current) {
        clearTimeout(draftPersistTimerRef.current);
        draftPersistTimerRef.current = null;
      }

      let targetConvId = activeConvId;
      let isNewConv = false;
      if (!targetConvId) {
        // Create new conversation on first message
        isNewConv = true;
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
      setProgrammaticInput("");
      // Clear the submitted draft for this thread (and DRAFT_NEW_KEY if this initiated a fresh thread)
      const updatedDrafts: ChatDraftMap = { ...draftsRef.current };
      if (isNewConv) {
        delete updatedDrafts[DRAFT_NEW_KEY];
      }
      if (targetConvId) {
        delete updatedDrafts[targetConvId];
      }
      draftsRef.current = updatedDrafts;
      setDrafts(updatedDrafts);
      persistDrafts(updatedDrafts);
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
            const costUsd =
              (typeof doneEvt.cost_usd === "number" ? doneEvt.cost_usd : null) ??
              extractTurnCost(liveTraceRef.current, null, modelName, modelTier);
            const assistantMsg: Message = {
              role: "assistant",
              content: event.response ?? "",
              timestamp: new Date(event.timestamp),
              agent: doneEvt.agent as string | undefined,
              domain: (doneEvt.domain as string | null) ?? null,
              confidence: (doneEvt.confidence as number | null) ?? null,
              modelTier: modelTier ?? turnModelOption?.tier ?? selectedModelTier,
              modelName: modelName ?? turnModelOption?.model_name ?? null,
              costUsd,
              trace: liveTraceRef.current,
            };
            setMessages((msgs) => [...msgs, assistantMsg]);
            setLiveTrace([]);
            liveTraceRef.current = [];
            setLoading(false);
            abortRef.current = null;
            inputRef.current?.focus();
            getConversations().then((updatedList) => {
              setConversations(updatedList);
              // For a newly initialized conversation thread, automatically generate a concise topic title with AI
              if (isNewConv && targetConvId) {
                autoGenerateConversationTitle(targetConvId)
                  .then((titleRes) => {
                    if (titleRes.title) {
                      setConversations((prev) =>
                        prev.map((c) =>
                          c.id === targetConvId ? { ...c, title: titleRes.title! } : c
                        )
                      );
                    }
                  })
                  .catch((err) =>
                    console.error("Failed to auto-generate title on first turn:", err)
                  );
              }
            });
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
    [loading, activeConvId, selectedModelTier, modelOptions, refreshBoard, setProgrammaticInput]
  );

  const handleClearBoard = useCallback(async () => {
    await clearBoardBulletins(activeConvId);
    refreshBoard();
  }, [activeConvId, refreshBoard]);

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

  // handleToggleInputCollapse: memoized handler to toggle bottom message input bar between full composer and compact rail
  const handleToggleInputCollapse = useCallback((collapsed?: boolean) => {
    setIsInputCollapsed((prev) => {
      const next = typeof collapsed === "boolean" ? collapsed : !prev;
      try {
        localStorage.setItem(CHAT_INPUT_COLLAPSED_KEY, String(next));
      } catch {
        // Ignore quota/privacy errors in restricted browser contexts
      }
      // If expanding, focus the input textarea on the next microtask so the user can type immediately
      if (!next) {
        queueMicrotask(() => {
          inputRef.current?.focus();
        });
      }
      return next;
    });
  }, []);

  // handleSelectPromptSuggestion: populates chat input, updates per-thread draft map, auto-expands composer, and focuses textarea
  const handleSelectPromptSuggestion = useCallback(
    (suggestion: string) => {
      if (draftPersistTimerRef.current) {
        clearTimeout(draftPersistTimerRef.current);
        draftPersistTimerRef.current = null;
      }
      setProgrammaticInput(suggestion);
      const key = activeConvId ?? DRAFT_NEW_KEY;
      const updated: ChatDraftMap = { ...draftsRef.current };
      if (suggestion.trim()) {
        updated[key] = suggestion;
      } else {
        delete updated[key];
      }
      draftsRef.current = updated;
      setDrafts(updated);
      persistDrafts(updated);
      setIsInputCollapsed(false);
      try {
        localStorage.setItem(CHAT_INPUT_COLLAPSED_KEY, "false");
      } catch {
        // Ignore quota errors in restricted browser contexts
      }
      queueMicrotask(() => {
        inputRef.current?.focus();
      });
    },
    [activeConvId, setProgrammaticInput]
  );

  // Global keyboard shortcut: pressing '/' while viewing the thread expands the message bar and focuses the input
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      const activeElement = document.activeElement;
      const isEditing =
        activeElement instanceof HTMLInputElement ||
        activeElement instanceof HTMLTextAreaElement ||
        activeElement?.getAttribute("contenteditable") === "true";
      if (!isEditing && e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setIsInputCollapsed(false);
        try {
          localStorage.setItem(CHAT_INPUT_COLLAPSED_KEY, "false");
        } catch {
          // Ignore quota errors
        }
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
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
        drafts={drafts}
        onToggleCollapse={handleToggleSidebarCollapse}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
        onUpdateTitle={handleUpdateTitle}
        onAutoGenerateTitle={handleAutoGenerateTitle}
      />

      {/* ── Main Chat Area ──────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">
        <ChatHeader
          title={activeConv?.title}
          activeConvId={activeConvId}
          showBoard={showBoard}
          bulletinCount={bulletins.length}
          onToggleBoard={handleToggleBoard}
          onUpdateTitle={handleUpdateTitle}
          onAutoGenerateTitle={handleAutoGenerateTitle}
        />

        <ChatMessageThread
          messages={messages}
          loading={loading}
          liveTrace={liveTrace}
          activeModelLabel={activeModelLabel}
          onSelectPromptSuggestion={handleSelectPromptSuggestion}
        />

        <ChatInputBar
          input={input}
          inputSyncId={inputSyncId}
          loading={loading}
          isCollapsed={isInputCollapsed}
          modelOptions={modelOptions}
          selectedModelTier={selectedModelTier}
          activeModelLabel={activeModelLabel}
          inputRef={inputRef}
          onChangeInput={handleInputChange}
          onSelectModelTier={handleSelectModelTier}
          onToggleCollapse={handleToggleInputCollapse}
          onSubmit={handleSubmit}
        />
      </div>

      {/* ── Right Drawer: Shared Subagent Blackboard (`blackboard.db`) ───────── */}
      {showBoard && (
        <BlackboardDrawer
          bulletins={bulletins}
          threadId={activeConvId}
          onRefresh={refreshBoard}
          onClear={handleClearBoard}
          onDismiss={handleDismissBulletin}
          onClose={handleCloseBoard}
        />
      )}
    </div>
  );
}

