/**
 * branches.ts — Universal Conversation Branching (`chats.db` DAG) & Subroutine Merge API client.
 * Connects to FastAPI `/api/agents/ask/conversations/{id}/branch` and `/merge` endpoints.
 */

import { apiFetch } from "./client";
import type { ChatHistoryEntry, Conversation } from "./agents";

// Union literal type for supported conversation fork strategies:
// - "tangent": Synthesizes a proportional Parent Context Brief + preserves focal turn in a fresh context window
// - "fork": Clones all parent messages up to the branch point verbatim
export type BranchMode = "tangent" | "fork";

// Request payload sent to POST /api/agents/ask/conversations/{id}/branch
export interface BranchConversationRequest {
  parent_message_id?: number | null;    // SQLite `messages.id` of the message turn being branched from
  parent_message_index?: number | null; // 0-based turn index fallback if `parent_message_id` is absent
  branch_mode?: BranchMode;             // Either "tangent" (default) or "fork"
  title?: string;                       // Optional explicit title for the child branch
  model_tier?: string;                  // Model tier ("low", "medium", "strong") for Parent Context Brief synthesis
}

// Response payload returned by POST /api/agents/ask/conversations/{id}/branch
export interface BranchConversationResponse {
  conversation_id: string;              // Newly created child branch UUID
  conversation: Conversation;           // Full Conversation record for the child branch
  messages: ChatHistoryEntry[];         // Seeded initial messages in the child branch
  parent_conversation_id: string;       // Parent conversation UUID
  parent_message_id: number | null;     // Resolved `messages.id` in the parent thread
  branch_mode: BranchMode;              // Effective branch mode executed
}

// Request payload sent to POST /api/agents/ask/conversations/{id}/merge
export interface MergeBranchRequest {
  guidance?: string;                    // Optional user focus instructions for the distillation
  model_tier?: string;                  // Model tier ("low", "medium", "strong") for branch distillation
}

// Response payload returned by POST /api/agents/ask/conversations/{id}/merge
export interface MergeBranchResponse {
  status: string;                       // "merged"
  branch_conversation_id: string;       // UUID of the child branch that was distilled
  parent_conversation_id: string;       // UUID of the parent thread that received the merge
  merged_at: string;                    // ISO-8601 UTC timestamp of the merge
  merged_message_id: number | null;     // SQLite `messages.id` of the summary message appended to parent
  distilled_content: string;            // Full Markdown body injected into the parent thread
}

/**
 * Forks a parent conversation at a specific message turn into a new isolated child branch.
 *
 * @param parentConversationId UUID of the parent conversation thread.
 * @param options Branch configuration (`parent_message_id`, `parent_message_index`, `branch_mode`, `title`, `model_tier`).
 * @returns Promise resolving to the newly created child branch metadata and seeded message list.
 */
export async function branchConversation(
  parentConversationId: string,
  options: BranchConversationRequest = {}
): Promise<BranchConversationResponse> {
  return apiFetch<BranchConversationResponse>(
    `/api/agents/ask/conversations/${encodeURIComponent(parentConversationId)}/branch`,
    {
      method: "POST",
      body: JSON.stringify(options),
    }
  );
}

/**
 * Distills a child branch conversation (proportional to its complexity) and merges the takeaways
 * back into its parent conversation thread.
 *
 * @param branchConversationId UUID of the child branch conversation to distill and merge.
 * @param options Optional user guidance and model tier override.
 * @returns Promise resolving to the merge outcome and distilled markdown content.
 */
export async function mergeBranchToParent(
  branchConversationId: string,
  options: MergeBranchRequest = {}
): Promise<MergeBranchResponse> {
  return apiFetch<MergeBranchResponse>(
    `/api/agents/ask/conversations/${encodeURIComponent(branchConversationId)}/merge`,
    {
      method: "POST",
      body: JSON.stringify(options),
    }
  );
}

