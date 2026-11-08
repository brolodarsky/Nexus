"use client";

/**
 * useChatBranching.ts — Custom React hook encapsulating Universal Conversation Branching state,
 * DAG lineage lookups (`parentConversation`, `childBranchesForActive`, `childBranchesByMessageId`),
 * and async fork/merge handlers so `ChatPage` (`page.tsx`) stays modular and concise.
 */

import { useState, useMemo, useCallback } from "react";
import {
  branchConversation,
  mergeBranchToParent,
  type BranchMode,
  type Conversation,
} from "@/lib/api";

// UseChatBranchingParams: dependencies passed from `ChatPage` into the branching hook
export interface UseChatBranchingParams {
  conversations: Conversation[];
  activeConvId: string | null;
  selectedModelTier: string;
  onRefreshConversations: () => Promise<Conversation[]>;
  onSelectConversation: (id: string) => Promise<void> | void;
}

export function useChatBranching({
  conversations,
  activeConvId,
  selectedModelTier,
  onRefreshConversations,
  onSelectConversation,
}: UseChatBranchingParams) {
  // branchingMessageIndex: tracks which 0-based message turn is currently being forked (or null)
  const [branchingMessageIndex, setBranchingMessageIndex] = useState<number | null>(null);
  // isMergingBranch: tracks whether the active child branch is currently being distilled and merged
  const [isMergingBranch, setIsMergingBranch] = useState<boolean>(false);

  // Currently active Conversation record
  const activeConversation = useMemo(
    () => conversations.find((c) => c.id === activeConvId) ?? null,
    [conversations, activeConvId]
  );

  // Parent Conversation record if `activeConversation` is a child branch
  const parentConversation = useMemo(() => {
    const parentId = activeConversation?.parent_conversation_id;
    if (!parentId) return null;
    return conversations.find((c) => c.id === parentId) ?? null;
  }, [conversations, activeConversation]);

  // All direct child branches spawned from the currently active conversation
  const childBranchesForActive = useMemo(() => {
    if (!activeConvId) return [];
    return conversations.filter((c) => c.parent_conversation_id === activeConvId);
  }, [conversations, activeConvId]);

  // Lookup dictionary mapping `parent_message_id` -> array of child Conversation records
  const childBranchesByMessageId = useMemo(() => {
    const map: Record<number, Conversation[]> = {};
    for (const child of childBranchesForActive) {
      if (child.parent_message_id != null) {
        if (!map[child.parent_message_id]) {
          map[child.parent_message_id] = [];
        }
        map[child.parent_message_id].push(child);
      }
    }
    return map;
  }, [childBranchesForActive]);

  // Forks the active conversation from `messageIndex` / `messageId` and switches focus to the new child branch
  const handleBranchFromMessage = useCallback(
    async (messageIndex: number, messageId: number | undefined, mode: BranchMode) => {
      if (!activeConvId || branchingMessageIndex !== null) return;
      setBranchingMessageIndex(messageIndex);
      try {
        const res = await branchConversation(activeConvId, {
          parent_message_id: messageId ?? null,
          parent_message_index: messageIndex,
          branch_mode: mode,
          model_tier: selectedModelTier || "low",
        });
        await onRefreshConversations();
        await onSelectConversation(res.conversation_id);
      } catch (err) {
        console.error("Failed to branch conversation:", err);
      } finally {
        setBranchingMessageIndex(null);
      }
    },
    [activeConvId, branchingMessageIndex, selectedModelTier, onRefreshConversations, onSelectConversation]
  );

  // Distills the active child branch and merges the synthesized takeaways back into its parent thread
  const handleMergeBranchToParent = useCallback(
    async (guidance?: string) => {
      if (!activeConvId || !activeConversation?.parent_conversation_id || isMergingBranch) return;
      setIsMergingBranch(true);
      try {
        const res = await mergeBranchToParent(activeConvId, {
          guidance,
          model_tier: selectedModelTier || "low",
        });
        await onRefreshConversations();
        await onSelectConversation(res.parent_conversation_id);
      } catch (err) {
        console.error("Failed to distill and merge branch:", err);
      } finally {
        setIsMergingBranch(false);
      }
    },
    [activeConvId, activeConversation, isMergingBranch, selectedModelTier, onRefreshConversations, onSelectConversation]
  );

  return {
    activeConversation,
    parentConversation,
    childBranchesForActive,
    childBranchesByMessageId,
    branchingMessageIndex,
    isMergingBranch,
    handleBranchFromMessage,
    handleMergeBranchToParent,
  };
}
