"use client";

/**
 * page.tsx (`/chat`) — Route orchestrator for the Nexus Chat workspace.
 * Coordinates conversation thread state, SSE streaming (`askBrainStream`), per-turn model
 * selection, and unsubmitted draft persistence, delegating all UI presentation to
 * modular subcomponents in `@/components/chat`.
 */

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import {
  askBrainStream,
  attachBrainStream,
  getActiveRuns,
  getActiveRunStatus,
  getAvailableModels,
  getChatHistory,
  getConversations,
  createConversation,
  deleteConversation,
  updateConversationTitle,
  autoGenerateConversationTitle,
  stopAndRevertTurn,
  type ActiveRunStatus,
  type BrainStreamCallbacks,
  type ChatHistoryEntry,
  type Conversation,
  type TraceEvent,
  type ModelOption,
} from "@/lib/api";
import {
  ChatSidebar,
  ChatHeader,
  BranchLineageBar,
  ChatMessageThread,
  ChatInputBar,
  useChatBranching,
  FALLBACK_MODELS,
  MODEL_STORAGE_KEY,
  ACTIVE_CONV_STORAGE_KEY,
  CHAT_SIDEBAR_COLLAPSED_KEY,
  CHAT_INPUT_COLLAPSED_KEY,
  DRAFT_NEW_KEY,
  loadPersistedDrafts,
  persistDrafts,
  extractTurnModelInfo,
  extractTurnCost,
  mapHistoryEntriesToMessages,
  type Message,
  type ChatDraftMap,
} from "@/components/chat";

// Compares SQLite history records against currently rendered messages so focus/poll reconciliations skip no-op re-renders
function historyMatchesMessages(history: ChatHistoryEntry[], current: Message[]): boolean {
  if (history.length !== current.length) return false;
  for (let i = 0; i < history.length; i++) {
    const h = history[i];
    const m = current[i];
    if (h.id !== m.id || h.role !== m.role || h.content !== m.content) {
      return false;
    }
  }
  return true;
}

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
  // isSidebarCollapsed: toggles the left conversation history menu between full width (w-64) and compact rail (w-14)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);
  // isMobileSidebarOpen: controls whether the mobile (< 768px) slide-over conversation drawer overlay is open
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState<boolean>(false);
  // isInputCollapsed: toggles the bottom message bar between full multiline composer and compact collapsed rail
  const [isInputCollapsed, setIsInputCollapsed] = useState<boolean>(false);
  // Per-turn model selection state: catalog of available models from `/api/agents/models` + currently selected tier
  const [modelOptions, setModelOptions] = useState<ModelOption[]>(FALLBACK_MODELS);
  const [selectedModelTier, setSelectedModelTier] = useState<string>("strong");
  // Staged image attachments uploaded via composer or clipboard paste for the upcoming turn
  const [pendingImages, setPendingImages] = useState<string[]>([]);
  // activeRunIds: UUIDs of conversations currently executing a background turn on the server (shown as pulsing dots in sidebar)
  const [activeRunIds, setActiveRunIds] = useState<string[]>([]);
  // activeRunModel: model metadata for the currently streaming/re-attached turn so status banner matches even across switches
  const [activeRunModel, setActiveRunModel] = useState<{
    tier?: string | null;
    name?: string | null;
    label?: string | null;
  } | null>(null);

  const liveTraceRef = useRef<TraceEvent[]>([]);
  // activeConvIdRef / messagesRef / loadingRef / activeRunIdsRef: mirror React state for async timers and focus handlers
  const activeConvIdRef = useRef<string | null>(null);
  const messagesRef = useRef<Message[]>([]);
  const loadingRef = useRef<boolean>(false);
  const activeRunIdsRef = useRef<string[]>([]);
  // modelOptionsRef / selectedModelTierRef: mirror model state for stable stream callbacks
  const modelOptionsRef = useRef<ModelOption[]>(FALLBACK_MODELS);
  const selectedModelTierRef = useRef<string>("strong");
  // lastSseActivityAtRef: tracks timestamp of last received SSE chunk/heartbeat to detect half-open or tab-frozen sockets
  const lastSseActivityAtRef = useRef<number>(0);
  // lastCompletedTurnRef: suppresses redundant polling reconciliations right after a clean live 'done' / 'sync_required'
  const lastCompletedTurnRef = useRef<{ convId: string; at: number } | null>(null);
  // missingRunSinceRef: tracks when an active conversation disappeared from /ask/active before SSE settled
  const missingRunSinceRef = useRef<Record<string, number>>({});
  // lastFocusSyncAtRef: throttles simultaneous focus + visibilitychange + online recovery events
  const lastFocusSyncAtRef = useRef<number>(0);
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
  // isInitialLoadDoneRef: guards against premature writes to ACTIVE_CONV_STORAGE_KEY before initial conversations load
  const isInitialLoadDoneRef = useRef<boolean>(false);
  // activeStreamConvIdRef: tracks which conversation thread currently owns an active SSE stream to guard against race conditions
  const activeStreamConvIdRef = useRef<string | null>(null);
  // autoTitleInFlightRef: deduplicates concurrent client-side title sync requests per conversation UUID
  const autoTitleInFlightRef = useRef<Set<string>>(new Set());

  // Keep mirror refs synchronized with React state after commits
  useEffect(() => {
    activeConvIdRef.current = activeConvId;
  }, [activeConvId]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    loadingRef.current = loading;
  }, [loading]);

  useEffect(() => {
    activeRunIdsRef.current = activeRunIds;
  }, [activeRunIds]);

  useEffect(() => {
    modelOptionsRef.current = modelOptions;
  }, [modelOptions]);

  useEffect(() => {
    selectedModelTierRef.current = selectedModelTier;
  }, [selectedModelTier]);

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

  // Appends newly uploaded image URLs to the staged attachments list
  const handleAddImages = useCallback((urls: string[]) => {
    setPendingImages((prev) => [...prev, ...urls]);
  }, []);

  // Removes a staged image attachment by its index
  const handleRemoveImage = useCallback((index: number) => {
    setPendingImages((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // Fetch conversations, selectable model catalog, and restore draft state on mount
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
      if (savedActiveConv && savedActiveConv !== "__new__" && initialDrafts[savedActiveConv]) {
        setProgrammaticInput(initialDrafts[savedActiveConv]);
      } else if (initialDrafts[DRAFT_NEW_KEY]) {
        setProgrammaticInput(initialDrafts[DRAFT_NEW_KEY]);
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

    getActiveRuns()
      .then((res) => setActiveRunIds(res.active_runs.map((r) => r.conversation_id)))
      .catch(() => {});

    getConversations()
      .then((convos) => {
        setConversations(convos);
        if (convos.length > 0) {
          // By default, select the most recent conversation (convos[0] sorted by last_updated DESC in SQLite)
          let targetId = convos[0].id;
          try {
            const savedActiveConv = localStorage.getItem(ACTIVE_CONV_STORAGE_KEY);
            // If a specific conversation ID was saved and exists in the database, restore it
            if (savedActiveConv && savedActiveConv !== "__new__" && convos.some((c) => c.id === savedActiveConv)) {
              targetId = savedActiveConv;
            }
          } catch {
            // Gracefully fallback to the most recent conversation
          }
          activeConvIdRef.current = targetId;
          setActiveConvId(targetId);
          setProgrammaticInput(draftsRef.current[targetId] ?? "");
          try {
            localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, targetId);
          } catch {
            // Ignore storage quota errors
          }
        } else {
          activeConvIdRef.current = null;
          setActiveConvId(null);
          setProgrammaticInput(draftsRef.current[DRAFT_NEW_KEY] ?? "");
        }
        isInitialLoadDoneRef.current = true;
      })
      .catch((err) => {
        // Prevent unhandled promise rejection and ensure initial load flag clears if backend is unreachable
        console.error("Failed to load conversations:", err);
        isInitialLoadDoneRef.current = true;
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

  // Refreshes the sidebar conversation list and automatically syncs any newly completed placeholder titles
  // (`title_source === "placeholder"`) with the backend's Turn-1 auto-title job (`force=false` coalesces without duplicate LLM calls)
  const refreshConversationsAndSyncTitles = useCallback((candidateIds?: string[]) => {
    getConversations()
      .then((updatedList) => {
        setConversations(updatedList);
        const targets = updatedList.filter((c) => {
          if (c.title_source !== "placeholder") return false;
          if (candidateIds && !candidateIds.includes(c.id)) return false;
          return !autoTitleInFlightRef.current.has(c.id);
        });
        for (const conv of targets) {
          autoTitleInFlightRef.current.add(conv.id);
          autoGenerateConversationTitle(conv.id, false)
            .then((titleRes) => {
              if (titleRes.title && (titleRes.status === "updated" || titleRes.status === "unchanged")) {
                setConversations((prev) =>
                  prev.map((c) =>
                    c.id === conv.id
                      ? {
                          ...c,
                          title: titleRes.title!,
                          title_source:
                            titleRes.status === "updated" && !titleRes.fallback
                              ? "auto"
                              : c.title_source,
                        }
                      : c
                  )
                );
              }
            })
            .catch((err) => console.error("Failed to sync auto-generated conversation title:", err))
            .finally(() => {
              autoTitleInFlightRef.current.delete(conv.id);
            });
        }
      })
      .catch(() => {});
  }, []);

  // Helper building unified SSE stream callbacks shared between fresh submissions and mid-turn re-attachments
  const createStreamCallbacks = useCallback(
    (
      targetConvId: string,
      options?: {
        fallbackModelTier?: string | null;
        fallbackModelName?: string | null;
        reconnectAttempt?: number;
        minReplyHistoryLength?: number;
      }
    ): BrainStreamCallbacks => {
      // Recursive inner builder avoids self-referencing the outer `useCallback` binding before initialization
      const buildCallbacks = (attempt: number, attemptOptions?: typeof options): BrainStreamCallbacks => {
        const minReplyLen = attemptOptions?.minReplyHistoryLength;

        const hasCommittedAssistantReply = (history: ChatHistoryEntry[]) => {
          const lastEntry = history[history.length - 1];
          if (!lastEntry || lastEntry.role !== "assistant") return false;
          return minReplyLen === undefined || history.length >= minReplyLen;
        };

        // Clear local live stream flags and optionally remove thread from sidebar active indicator
        const finishLocalStream = (clearActiveRunBadge: boolean) => {
          delete missingRunSinceRef.current[targetConvId];
          setLiveTrace([]);
          liveTraceRef.current = [];
          setLoading(false);
          setActiveRunModel(null);
          activeStreamConvIdRef.current = null;
          abortRef.current = null;
          if (clearActiveRunBadge) {
            setActiveRunIds((prev) => prev.filter((id) => id !== targetConvId));
          }
        };

        // Resolve history ground-truth and synchronize UI state after completion or sync fallback
        const reconcileHistoryFromServer = async () => {
          const history = await getChatHistory(targetConvId);
          if (activeConvIdRef.current !== targetConvId) return;
          setMessages(mapHistoryEntriesToMessages(history));
          lastCompletedTurnRef.current = { convId: targetConvId, at: Date.now() };
          finishLocalStream(true);
          inputRef.current?.focus();
          refreshConversationsAndSyncTitles([targetConvId]);
        };

        return {
          onActivity: () => {
            if (activeStreamConvIdRef.current === targetConvId) {
              lastSseActivityAtRef.current = Date.now();
            }
          },
          onTrace: (event) => {
            // Guard against stale stream callbacks if the user switched conversations
            if (activeStreamConvIdRef.current !== targetConvId) return;
            lastSseActivityAtRef.current = Date.now();

            setLiveTrace((prev) => {
              // Deduplicate events by id to protect against re-deliveries or duplicate stream packets
              if (event.id && prev.some((e) => e.id === event.id)) {
                return prev;
              }
              const newTrace = [...prev, event];
              liveTraceRef.current = newTrace;
              return newTrace;
            });
          },
          onDone: (event) => {
            setActiveRunIds((prev) => prev.filter((id) => id !== targetConvId));
            // Guard against applying final response if user switched away to a different conversation
            if (activeStreamConvIdRef.current !== targetConvId) return;

            const doneEvt = event as unknown as Record<string, unknown>;
            // If Stop & Revert halted execution cleanly (e.g. triggered from another tab), reload clean DB state
            if (doneEvt.stopped) {
              reconcileHistoryFromServer().catch(() => finishLocalStream(true));
              return;
            }

            const currentOptions = modelOptionsRef.current;
            const fallbackTier = attemptOptions?.fallbackModelTier ?? selectedModelTierRef.current;
            const matchedOpt =
              currentOptions.find((m) => m.id === fallbackTier) ?? currentOptions[0];
            const { modelTier, modelName } = extractTurnModelInfo(
              liveTraceRef.current,
              (doneEvt.model_tier as string | null) ?? null,
              (doneEvt.model_name as string | null) ?? null
            );
            const effectiveTier = modelTier ?? attemptOptions?.fallbackModelTier ?? matchedOpt?.tier ?? fallbackTier;
            const effectiveName = modelName ?? attemptOptions?.fallbackModelName ?? matchedOpt?.model_name ?? null;
            const costUsd =
              (typeof doneEvt.cost_usd === "number" ? doneEvt.cost_usd : null) ??
              extractTurnCost(liveTraceRef.current, null, effectiveName, effectiveTier);
            const userMsgId = typeof doneEvt.user_message_id === "number" ? doneEvt.user_message_id : undefined;
            const assistantMsgId =
              typeof doneEvt.assistant_message_id === "number" ? doneEvt.assistant_message_id : undefined;

            const assistantMsg: Message = {
              id: assistantMsgId,
              role: "assistant",
              content: event.response ?? "",
              timestamp: new Date(event.timestamp),
              agent: doneEvt.agent as string | undefined,
              domain: (doneEvt.domain as string | null) ?? null,
              confidence: (doneEvt.confidence as number | null) ?? null,
              modelTier: effectiveTier,
              modelName: effectiveName,
              costUsd,
              trace: liveTraceRef.current,
              hasTrace: liveTraceRef.current.length > 0,
            };
            setMessages((msgs) => {
              // Avoid appending duplicate bubble if history reconciliation already loaded this message ID
              if (assistantMsgId !== undefined && msgs.some((m) => m.id === assistantMsgId)) {
                return msgs;
              }
              const updated = [...msgs];
              // Attach the SQLite `user_message_id` to the user prompt that initiated this turn
              if (userMsgId !== undefined && updated.length > 0 && updated[updated.length - 1].role === "user") {
                updated[updated.length - 1] = { ...updated[updated.length - 1], id: userMsgId };
              }
              return [...updated, assistantMsg];
            });
            lastCompletedTurnRef.current = { convId: targetConvId, at: Date.now() };
            finishLocalStream(true);
            inputRef.current?.focus();
            refreshConversationsAndSyncTitles([targetConvId]);
          },
          onSyncRequired: () => {
            setActiveRunIds((prev) => prev.filter((id) => id !== targetConvId));
            if (activeStreamConvIdRef.current !== targetConvId) return;
            reconcileHistoryFromServer().catch(() => finishLocalStream(true));
          },
          onError: async (errorMessage) => {
            // Guard against applying errors if user switched away to a different conversation
            if (activeStreamConvIdRef.current !== targetConvId) return;

            // Step 1: Probe backend run status (retrying briefly across transient restarts/network blips)
            let activeStatus: ActiveRunStatus | null = null;
            for (let probe = 0; probe < 3; probe++) {
              try {
                activeStatus = await getActiveRunStatus(targetConvId);
                break;
              } catch {
                if (probe < 2) {
                  await new Promise((resolve) => setTimeout(resolve, 1500));
                  if (activeStreamConvIdRef.current !== targetConvId) return;
                }
              }
            }

            if (activeStreamConvIdRef.current !== targetConvId) return;
            if (activeStatus?.active && attempt < 12) {
              const backoffMs = Math.min(5000, Math.round(1000 * Math.pow(1.4, attempt)));
              await new Promise((resolve) => setTimeout(resolve, backoffMs));
              if (activeStreamConvIdRef.current !== targetConvId) return;
              // Reset and replay clean server backlog so re-attached steps have zero gaps or duplicates
              setLiveTrace([]);
              liveTraceRef.current = [];
              lastSseActivityAtRef.current = Date.now();
              const reattachAbort = attachBrainStream(
                targetConvId,
                buildCallbacks(attempt + 1, {
                  ...attemptOptions,
                  fallbackModelTier: activeStatus.model_tier ?? attemptOptions?.fallbackModelTier,
                  fallbackModelName: activeStatus.model_name ?? attemptOptions?.fallbackModelName,
                })
              );
              if (activeStreamConvIdRef.current !== targetConvId) {
                reattachAbort();
                return;
              }
              abortRef.current = reattachAbort;
              return;
            }

            setActiveRunIds((prev) => prev.filter((id) => id !== targetConvId));

            // Step 2: Check if the backend finished and logged a new assistant response to chats.db
            try {
              const history = await getChatHistory(targetConvId);
              if (activeStreamConvIdRef.current !== targetConvId) return;
              if (hasCommittedAssistantReply(history)) {
                setMessages(mapHistoryEntriesToMessages(history));
                lastCompletedTurnRef.current = { convId: targetConvId, at: Date.now() };
                finishLocalStream(true);
                inputRef.current?.focus();
                refreshConversationsAndSyncTitles([targetConvId]);
                return;
              }
            } catch {
              // Ignore history check error and fall back to polling
            }

            // Step 3: Poll up to 5 times (every 2s) in case the background thread is finishing its DB commit
            let recovered = false;
            for (let pollIdx = 0; pollIdx < 5; pollIdx++) {
              await new Promise((resolve) => setTimeout(resolve, 2000));
              if (activeStreamConvIdRef.current !== targetConvId) return;
              try {
                const polled = await getChatHistory(targetConvId);
                if (activeStreamConvIdRef.current !== targetConvId) return;
                if (hasCommittedAssistantReply(polled)) {
                  setMessages(mapHistoryEntriesToMessages(polled));
                  lastCompletedTurnRef.current = { convId: targetConvId, at: Date.now() };
                  finishLocalStream(true);
                  inputRef.current?.focus();
                  refreshConversationsAndSyncTitles([targetConvId]);
                  recovered = true;
                  break;
                }
              } catch {
                // Continue polling
              }
            }

            if (!recovered && activeStreamConvIdRef.current === targetConvId) {
              const currentOptions = modelOptionsRef.current;
              const fallbackTier = attemptOptions?.fallbackModelTier ?? selectedModelTierRef.current;
              const matchedOpt =
                currentOptions.find((m) => m.id === fallbackTier) ?? currentOptions[0];
              const errorMsg: Message = {
                role: "assistant",
                content: `❌ ${errorMessage}`,
                timestamp: new Date(),
                modelTier: attemptOptions?.fallbackModelTier ?? matchedOpt?.tier ?? fallbackTier,
                modelName: attemptOptions?.fallbackModelName ?? matchedOpt?.model_name ?? null,
                trace: liveTraceRef.current.length > 0 ? liveTraceRef.current : undefined,
                hasTrace: liveTraceRef.current.length > 0,
              };
              setMessages((msgs) => [...msgs, errorMsg]);
              finishLocalStream(true);
              inputRef.current?.focus();
            }
          },
        };
      };

      return buildCallbacks(options?.reconnectAttempt ?? 0, options);
    },
    [refreshConversationsAndSyncTitles]
  );

  // Loads persisted history for `convId` and seamlessly re-attaches the live Thinking Panel if a background run is active
  const syncConversation = useCallback(
    async (
      convId: string,
      isCancelled?: () => boolean,
      options?: { forceReattach?: boolean }
    ) => {
      try {
        // Query active-run status BEFORE history so post-completion SQLite commits are never missed in a race window
        const fallbackStatus: ActiveRunStatus = { active: false, conversation_id: convId };
        const [activeStatus, activeListRes] = await Promise.all([
          getActiveRunStatus(convId).catch(() => fallbackStatus),
          getActiveRuns().catch(() => null),
        ]);
        if (isCancelled?.() || activeConvIdRef.current !== convId) return;

        if (activeListRes) {
          setActiveRunIds(activeListRes.active_runs.map((r) => r.conversation_id));
        }

        const history = await getChatHistory(convId);
        if (isCancelled?.() || activeConvIdRef.current !== convId) return;

        if (!historyMatchesMessages(history, messagesRef.current)) {
          setMessages(mapHistoryEntriesToMessages(history));
        }

        // Guard against the sub-millisecond case where the run persisted its assistant reply right before history read
        const alreadyCommittedAssistant =
          activeStatus.active &&
          typeof activeStatus.user_message_id === "number" &&
          history.some(
            (m) =>
              m.role === "assistant" &&
              typeof m.id === "number" &&
              m.id > activeStatus.user_message_id!
          );

        if (activeStatus.active && !alreadyCommittedAssistant) {
          // Guard against racing with an already healthy stream on this same conversation unless caller requested stale recovery
          if (activeStreamConvIdRef.current === convId) {
            if (!options?.forceReattach) return;
            abortRef.current?.();
            abortRef.current = null;
            activeStreamConvIdRef.current = null;
          }

          activeStreamConvIdRef.current = convId;
          lastSseActivityAtRef.current = Date.now();
          delete missingRunSinceRef.current[convId];
          setActiveRunModel({
            tier: activeStatus.model_tier ?? null,
            name: activeStatus.model_name ?? null,
            label: activeStatus.model_label ?? null,
          });
          setLiveTrace([]);
          liveTraceRef.current = [];
          setLoading(true);

          const abort = attachBrainStream(
            convId,
            createStreamCallbacks(convId, {
              fallbackModelTier: activeStatus.model_tier ?? null,
              fallbackModelName: activeStatus.model_name ?? null,
              minReplyHistoryLength: history.length + 1,
            })
          );
          if (isCancelled?.() || activeConvIdRef.current !== convId) {
            abort();
            return;
          }
          abortRef.current = abort;
        } else {
          // Ensure any hung/orphaned stream state for this conversation clears cleanly now that server run is done
          if (activeStreamConvIdRef.current === convId) {
            abortRef.current?.();
            abortRef.current = null;
            activeStreamConvIdRef.current = null;
          }
          delete missingRunSinceRef.current[convId];
          setLiveTrace([]);
          liveTraceRef.current = [];
          setActiveRunModel(null);
          setLoading(false);
        }
      } catch (err) {
        if (!isCancelled?.()) {
          console.error("Failed to load chat history:", err);
          setLoading(false);
        }
      }
    },
    [createStreamCallbacks]
  );

  // Fetch messages and re-attach any live run when active conversation changes
  useEffect(() => {
    if (!activeConvId) {
      queueMicrotask(() => {
        setMessages([]);
        setActiveRunModel(null);
      });
      return;
    }

    // If an SSE agent response stream is actively in-flight for this thread (e.g. just initiated in handleSubmit),
    // do not let initial history fetch wipe out live streaming messages or reset loading state
    if (activeStreamConvIdRef.current === activeConvId) {
      return;
    }

    let cancelled = false;
    void syncConversation(activeConvId, () => cancelled);
    return () => {
      cancelled = true;
    };
  }, [activeConvId, syncConversation]);

  // Auto-focus input when switching conversations
  useEffect(() => {
    inputRef.current?.focus();
  }, [activeConvId]);

  // Persist active conversation ID so switching Nexus tabs (e.g., Chat -> Brain Explorer -> Chat) restores the same active chat
  useEffect(() => {
    // Guard against running before initial hydration and conversation resolution completes
    if (!isInitialLoadDoneRef.current) return;
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

  // Watchdog polling `/api/agents/ask/active` whenever runs are in flight or local state is loading,
  // syncing finished turns automatically if a background/stalled/cross-device SSE stream missed `done`
  useEffect(() => {
    if (activeRunIds.length === 0 && !loading) return;

    let cancelled = false;
    const pollActiveRuns = async () => {
      try {
        const res = await getActiveRuns();
        if (cancelled) return;

        const nextIds = res.active_runs.map((r) => r.conversation_id);
        const prevIds = activeRunIdsRef.current;
        const finishedIds = prevIds.filter((id) => !nextIds.includes(id));

        const idsChanged =
          prevIds.length !== nextIds.length ||
          prevIds.some((id) => !nextIds.includes(id)) ||
          nextIds.some((id) => !prevIds.includes(id));
        if (idsChanged) {
          setActiveRunIds(nextIds);
        }
        if (finishedIds.length > 0) {
          void refreshConversationsAndSyncTitles(finishedIds);
        }

        const convId = activeConvIdRef.current;
        if (!convId) return;

        if (nextIds.includes(convId)) {
          delete missingRunSinceRef.current[convId];
          // Attach automatically if this thread started executing from another client (e.g. phone/Telegram)
          if (!loadingRef.current && activeStreamConvIdRef.current !== convId) {
            void syncConversation(convId);
            return;
          }
          // Self-heal if our open SSE socket missed 2+ backend 10s keepalives while run is still active
          if (
            loadingRef.current &&
            activeStreamConvIdRef.current === convId &&
            lastSseActivityAtRef.current > 0 &&
            Date.now() - lastSseActivityAtRef.current > 20_000
          ) {
            void syncConversation(convId, undefined, { forceReattach: true });
          }
          return;
        }

        // `convId` is not active on the server; reconcile if UI is still loading or missed a remote completion
        const justDoneViaSse =
          lastCompletedTurnRef.current?.convId === convId &&
          Date.now() - lastCompletedTurnRef.current.at < 15_000;

        if (loadingRef.current || (finishedIds.includes(convId) && !justDoneViaSse)) {
          const now = Date.now();
          const firstMissing = missingRunSinceRef.current[convId] ?? now;
          missingRunSinceRef.current[convId] = firstMissing;

          const socketWentSilent =
            lastSseActivityAtRef.current > 0 && now - lastSseActivityAtRef.current >= 15_000;
          // Allow ~2.5s grace for initial POST registration or same-tick 'done' frames before forcing DB sync
          if (now - firstMissing >= 2500 || socketWentSilent || activeStreamConvIdRef.current !== convId) {
            delete missingRunSinceRef.current[convId];
            void syncConversation(convId, undefined, { forceReattach: true });
          }
        }
      } catch {
        // Ignore transient network failures during background active-run checks
      }
    };

    const timer = setInterval(() => {
      void pollActiveRuns();
    }, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [activeRunIds.length, loading, syncConversation, refreshConversationsAndSyncTitles]);

  // Recover stalled/completed conversations when the tab becomes visible, window regains focus, or network comes online
  useEffect(() => {
    const recoverActiveView = async () => {
      const now = Date.now();
      if (now - lastFocusSyncAtRef.current < 800) return;
      lastFocusSyncAtRef.current = now;

      // Refresh global active indicators and sidebar list cleanly
      getActiveRuns()
        .then((res) => {
          const nextIds = res.active_runs.map((r) => r.conversation_id);
          const prevIds = activeRunIdsRef.current;
          const finishedIds = prevIds.filter((id) => !nextIds.includes(id));
          if (finishedIds.length > 0) {
            void refreshConversationsAndSyncTitles(finishedIds);
          }
          setActiveRunIds(nextIds);
        })
        .catch(() => {});

      const convId = activeConvIdRef.current;
      if (!convId) return;

      try {
        const status = await getActiveRunStatus(convId);
        if (activeConvIdRef.current !== convId) return;

        if (!status.active) {
          if (loadingRef.current || activeStreamConvIdRef.current === convId) {
            if (abortRef.current) {
              abortRef.current();
              abortRef.current = null;
            }
            activeStreamConvIdRef.current = null;
          }
          await syncConversation(convId);
          void refreshConversationsAndSyncTitles([convId]);
        } else {
          // Run is still executing on server: attach if unattached, or re-attach if the socket froze while away
          const socketStale =
            lastSseActivityAtRef.current > 0 && Date.now() - lastSseActivityAtRef.current > 15_000;
          if (!loadingRef.current || activeStreamConvIdRef.current !== convId) {
            await syncConversation(convId);
          } else if (socketStale) {
            await syncConversation(convId, undefined, { forceReattach: true });
          }
        }
      } catch {
        // Ignore transient status failures on focus
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void recoverActiveView();
      }
    };
    const handleWindowResume = () => {
      if (document.visibilityState === "visible") {
        void recoverActiveView();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", handleWindowResume);
    window.addEventListener("online", handleWindowResume);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleWindowResume);
      window.removeEventListener("online", handleWindowResume);
    };
  }, [syncConversation, refreshConversationsAndSyncTitles]);

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

      // Cleanly detach local SSE stream listener (backend run keeps executing so returning re-attaches)
      if (abortRef.current) {
        abortRef.current();
        abortRef.current = null;
      }
      setLoading(false);
      setLiveTrace([]);
      liveTraceRef.current = [];
      setActiveRunModel(null);
      activeStreamConvIdRef.current = null;

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
      setPendingImages([]);

      // 3. Switch active thread and persist selection
      activeConvIdRef.current = newConvId;
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

      // Cleanly detach local SSE stream listener if opening a new chat while a turn was streaming
      if (abortRef.current) {
        abortRef.current();
        abortRef.current = null;
      }
      setLoading(false);
      setLiveTrace([]);
      liveTraceRef.current = [];
      setActiveRunModel(null);
      activeStreamConvIdRef.current = null;

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
      setPendingImages([]);

      // 3. Reset active thread to null and persist new chat indicator
      activeConvIdRef.current = null;
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
    async (id: string, e?: React.MouseEvent) => {
      e?.stopPropagation();

      // Cleanly abort in-flight SSE stream if deleting the active streaming thread
      if (activeStreamConvIdRef.current === id) {
        if (abortRef.current) {
          abortRef.current();
          abortRef.current = null;
        }
        setLoading(false);
        setLiveTrace([]);
        liveTraceRef.current = [];
        setActiveRunModel(null);
        activeStreamConvIdRef.current = null;
      }
      setActiveRunIds((prev) => prev.filter((cid) => cid !== id));

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
        activeConvIdRef.current = nextId;
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
    // Optimistically update conversation title and mark as manual so background auto-titling cannot clobber it
    setConversations((prev) =>
      prev.map((c) => (c.id === convId ? { ...c, title: trimmed, title_source: "manual" } : c))
    );
    try {
      await updateConversationTitle(convId, trimmed);
    } catch (err) {
      console.error("Failed to update conversation title:", err);
      // Reconcile against ground-truth database state on error
      getConversations().then(setConversations).catch(() => {});
    }
  }, []);

  // Invokes fast AI auto-titling for an existing conversation using the low-tier Flash/Sonnet model (force=true overrides manual/existing titles)
  const handleAutoGenerateTitle = useCallback(async (convId: string) => {
    try {
      const res = await autoGenerateConversationTitle(convId, true);
      if (res.title) {
        setConversations((prev) =>
          prev.map((c) => (c.id === convId ? { ...c, title: res.title!, title_source: "auto" } : c))
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
      if ((!query && pendingImages.length === 0) || loading) return;

      if (draftPersistTimerRef.current) {
        clearTimeout(draftPersistTimerRef.current);
        draftPersistTimerRef.current = null;
      }

      // Snapshot and clear staged image attachments
      const imagesToSend = [...pendingImages];
      setPendingImages([]);

      let targetConvId = activeConvId;
      let isNewConv = false;
      if (!targetConvId) {
        // Create new conversation on first message
        isNewConv = true;
        const initialTitleText = query || "Image Analysis";
        const title = initialTitleText.slice(0, 30) + (initialTitleText.length > 30 ? "..." : "");
        const res = await createConversation(title);
        targetConvId = res.conversation_id;
        // Mark active stream thread BEFORE updating activeConvId so useEffect([activeConvId]) doesn't clobber live state
        activeStreamConvIdRef.current = targetConvId;
        activeConvIdRef.current = targetConvId;
        setActiveConvId(targetConvId);
        try {
          localStorage.setItem(ACTIVE_CONV_STORAGE_KEY, targetConvId);
        } catch {
          // Ignore storage errors
        }
        // Refresh conversations list to show the new one
        getConversations().then(setConversations);
      } else {
        activeStreamConvIdRef.current = targetConvId;
        // Optimistically bump `last_updated` and move the active thread to index 0 on Send
        // so the sidebar updates recency immediately without waiting for `onDone` to refetch SQLite
        const bumpedIso = new Date().toISOString();
        setConversations((prev) => {
          const target = prev.find((c) => c.id === targetConvId);
          if (!target) return prev;
          return [{ ...target, last_updated: bumpedIso }, ...prev.filter((c) => c.id !== targetConvId)];
        });
      }

      const turnModelOption =
        modelOptions.find((m) => m.id === selectedModelTier) ?? modelOptions[0];
      const expectedReplyMinLength = messagesRef.current.length + 2;
      const userMsg: Message = {
        role: "user",
        content: query,
        images: imagesToSend.length > 0 ? imagesToSend : undefined,
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
      if (lastCompletedTurnRef.current?.convId === targetConvId) {
        lastCompletedTurnRef.current = null;
      }
      delete missingRunSinceRef.current[targetConvId];
      lastSseActivityAtRef.current = Date.now();
      setActiveRunModel({
        tier: turnModelOption?.tier ?? selectedModelTier,
        name: turnModelOption?.model_name ?? null,
        label: turnModelOption?.label ?? selectedModelTier,
      });
      setActiveRunIds((prev) => (prev.includes(targetConvId) ? prev : [...prev, targetConvId]));
      setLoading(true);
      setLiveTrace([]);
      liveTraceRef.current = [];

      const abort = askBrainStream(
        query || "Analyze the attached image(s).",
        targetConvId,
        createStreamCallbacks(targetConvId, {
          fallbackModelTier: turnModelOption?.tier ?? selectedModelTier,
          fallbackModelName: turnModelOption?.model_name ?? null,
          minReplyHistoryLength: expectedReplyMinLength,
        }),
        selectedModelTier,
        imagesToSend.length > 0 ? imagesToSend : undefined
      );

      abortRef.current = abort;
    },
    [loading, activeConvId, selectedModelTier, modelOptions, pendingImages, createStreamCallbacks, setProgrammaticInput]
  );

  // handleStopAndRevert: aborts active stream, halts backend graph execution, purges unapproved HITL mutations,
  // rolls back LangGraph memory and chats.db, and restores the user prompt text + attachments to the composer
  const handleStopAndRevert = useCallback(async () => {
    if (!activeConvId) return;

    // 1. Immediately terminate client SSE stream fetch connection
    if (abortRef.current) {
      abortRef.current();
      abortRef.current = null;
    }

    delete missingRunSinceRef.current[activeConvId];
    setLoading(false);
    setLiveTrace([]);
    liveTraceRef.current = [];
    setActiveRunModel(null);
    activeStreamConvIdRef.current = null;
    setActiveRunIds((prev) => prev.filter((id) => id !== activeConvId));

    try {
      // 2. Halt backend execution thread, cancel pending HITL mutations, rollback checkpoints & chats.db
      const res = await stopAndRevertTurn(activeConvId);

      // 3. Restore query into composer and textarea focus so user does not lose input
      if (res.restored_query) {
        setProgrammaticInput(res.restored_query);
      }
      if (res.restored_images && res.restored_images.length > 0) {
        setPendingImages(res.restored_images);
      }

      // 4. Fetch updated ground-truth message history from database
      const history = await getChatHistory(activeConvId);
      setMessages(mapHistoryEntriesToMessages(history));

      // 5. Refresh conversations list
      getConversations().then(setConversations);
    } catch (err) {
      console.error("Failed to stop and revert turn:", err);
    } finally {
      inputRef.current?.focus();
    }
  }, [activeConvId, setProgrammaticInput]);

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

  // Global keyboard shortcuts:
  // - Escape while streaming: stops active agent execution and reverts the turn immediately
  // - '/' while viewing thread: expands the message bar and focuses the input
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      // Esc shortcut: stops and reverts active streaming turn immediately
      if (loading && e.key === "Escape") {
        e.preventDefault();
        handleStopAndRevert();
        return;
      }

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
  }, [loading, handleStopAndRevert]);

  const handleRefreshConversations = useCallback(async () => {
    const list = await getConversations();
    setConversations(list);
    return list;
  }, []);

  const {
    activeConversation: activeConv,
    parentConversation,
    childBranchesForActive,
    childBranchesByMessageId,
    branchingMessageIndex,
    isMergingBranch,
    handleBranchFromMessage,
    handleMergeBranchToParent,
  } = useChatBranching({
    conversations,
    activeConvId,
    selectedModelTier,
    onRefreshConversations: handleRefreshConversations,
    onSelectConversation: handleSelectConversation,
  });

  const activeModelOption =
    modelOptions.find((m) => m.id === selectedModelTier) ?? modelOptions[0];
  const activeModelLabel = activeModelOption?.label ?? selectedModelTier;
  // Use the running turn's model metadata in the live Thinking Panel banner so switching threads preserves accuracy
  const liveStatusModelLabel = useMemo(() => {
    if (!activeRunModel) return activeModelLabel;
    const matched = modelOptions.find(
      (m) =>
        (activeRunModel.name && m.model_name === activeRunModel.name) ||
        (activeRunModel.tier && m.id === activeRunModel.tier)
    );
    return matched?.label ?? activeRunModel.label ?? activeRunModel.name ?? activeModelLabel;
  }, [activeRunModel, modelOptions, activeModelLabel]);

  return (
    <div className="flex h-[calc(100dvh-4rem)] md:h-full md:max-h-screen relative overflow-hidden">
      {/* ── Collapsible Conversation History Sidebar Menu ──── */}
      <ChatSidebar
        conversations={conversations}
        activeConvId={activeConvId}
        isCollapsed={isSidebarCollapsed}
        isMobileOpen={isMobileSidebarOpen}
        modelOptions={modelOptions}
        selectedModelTier={selectedModelTier}
        drafts={drafts}
        activeRunConvIds={activeRunIds}
        onToggleCollapse={handleToggleSidebarCollapse}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
      />

      {/* ── Main Chat Area ──────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">
        <ChatHeader
          title={activeConv?.title}
          activeConvId={activeConvId}
          onOpenMobileSidebar={() => setIsMobileSidebarOpen(true)}
          onUpdateTitle={handleUpdateTitle}
          onAutoGenerateTitle={handleAutoGenerateTitle}
          onDeleteChat={handleDeleteChat}
        />

        <BranchLineageBar
          activeConversation={activeConv}
          parentConversation={parentConversation}
          childBranches={childBranchesForActive}
          isMerging={isMergingBranch}
          onSelectConversation={handleSelectConversation}
          onMergeToParent={handleMergeBranchToParent}
        />

        <ChatMessageThread
          activeConvId={activeConvId}
          messages={messages}
          loading={loading}
          liveTrace={liveTrace}
          activeModelLabel={liveStatusModelLabel}
          childBranchesByMessageId={childBranchesByMessageId}
          branchingMessageIndex={branchingMessageIndex}
          onSelectPromptSuggestion={handleSelectPromptSuggestion}
          onStopAndRevert={handleStopAndRevert}
          onRevertLastTurn={handleStopAndRevert}
          onBranchMessage={handleBranchFromMessage}
          onSelectConversation={handleSelectConversation}
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
          pendingImages={pendingImages}
          onAddImages={handleAddImages}
          onRemoveImage={handleRemoveImage}
          onChangeInput={handleInputChange}
          onSelectModelTier={handleSelectModelTier}
          onToggleCollapse={handleToggleInputCollapse}
          onStopAndRevert={handleStopAndRevert}
          onSubmit={handleSubmit}
        />
      </div>
    </div>
  );
}

