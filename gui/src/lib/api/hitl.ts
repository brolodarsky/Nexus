/**
 * hitl.ts — Human-in-the-Loop (HITL) safety verification, diff approvals, rebase, rollback, and conflict handling.
 * Connects to FastAPI `/api/hitl` routes.
 */

import { apiFetch, ApiError } from "./client";

// Interface representing a pending file modification in the HITL transaction queue
export interface Transaction {
  id: number;                 // Auto-incrementing primary key in hitl.db
  agent_name: string;         // Agent that proposed the write (e.g. "CareerAgent")
  action_type: string;        // Type of modification (e.g. "write_file", "append_note")
  target_file: string;        // Absolute or vault-relative path to target file
  original_content: string | null; // Previous file content (for pre-commit diff preview)
  proposed_content: string;   // New content drafted by the agent
  reasoning: string | null;   // Plain-English explanation of why change is needed
  status: string;             // "pending" | "approved" | "rejected" | "rolled_back" | "superseded"
  created_at: string;         // ISO-8601 creation timestamp
}

// Structured 409 body returned when approve/rollback/rebase hits a commit-integrity conflict
export interface HitlConflictDetail {
  code: "stale_base" | "merge_conflict"; // stale_base = disk drifted; merge_conflict = rebase edits overlap
  message: string;                       // Human-readable explanation from the engine
  current_content?: string | null;       // Current disk text (stale_base only); null if the note was deleted
}

// Type guard: narrows an unknown `ApiError.detail` to HitlConflictDetail (`detail is X` tells TS the check's meaning)
export function isHitlConflict(detail: unknown): detail is HitlConflictDetail {
  return typeof detail === "object" && detail !== null && "code" in detail;
}

// Lightweight row from the `revisions` snapshot ledger, used for the Undo list
export interface HitlRevision {
  id: number;                 // Revision primary key
  tx_id: number;              // Transaction that produced this write
  target_file: string;        // Vault-relative path that was written
  rolled_back: number;        // 0 = live, 1 = already undone (SQLite has no boolean type)
  created_at: string;         // When the approval was applied
  rolled_back_at: string | null;
  agent_name: string;
  action_type: string;
  reasoning: string | null;
}

// Result returned by approve / rollback
export interface HitlCommitResult {
  status: string;
  message: string;
  revision_id: number;
  target_file: string;
  forced: boolean;            // True only if a real conflict was overridden with force
}

// Lists all uncommitted changes awaiting human approval in the HITL panel
export async function getPendingHitl(): Promise<Transaction[]> {
  return apiFetch<Transaction[]>("/api/hitl/pending");
}

// Commits a pending transaction to disk (Phase 2 of Two-Phase Commit)
// force=true overrides a 409 stale_base conflict (prior disk content is still snapshotted for Undo)
export async function approveHitl(id: number, force = false): Promise<HitlCommitResult> {
  return apiFetch<HitlCommitResult>(`/api/hitl/${id}/approve${force ? "?force=true" : ""}`, { method: "POST" });
}

// Discards a pending transaction without applying changes to disk
export async function rejectHitl(id: number): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>(`/api/hitl/${id}/reject`, { method: "POST" });
}

// Restores an approved note to its pre-approval snapshot (409 if edited since approval unless force=true)
export async function rollbackHitl(id: number, force = false): Promise<HitlCommitResult> {
  return apiFetch<HitlCommitResult>(`/api/hitl/${id}/rollback${force ? "?force=true" : ""}`, { method: "POST" });
}

// Re-stages a stale pending edit on top of the current disk text via 3-way merge (409 merge_conflict on overlap)
export async function rebaseHitl(id: number): Promise<{ status: string; rebased: boolean; message: string }> {
  return apiFetch<{ status: string; rebased: boolean; message: string }>(`/api/hitl/${id}/rebase`, { method: "POST" });
}

// Lists recently applied revisions (newest first) for the Undo list
export async function getRecentRevisions(limit = 10): Promise<HitlRevision[]> {
  return apiFetch<HitlRevision[]>(`/api/hitl/revisions/recent?limit=${limit}`);
}

