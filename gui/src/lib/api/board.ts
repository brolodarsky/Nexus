/**
 * board.ts — Shared Inter-Agent Blackboard / Bulletin Board API client.
 * Connects to FastAPI `/api/board` routes powered by `blackboard.db`.
 */

import { apiFetch } from "./client";

// Interface representing a single bulletin posted by a Flash subagent or Astra on `blackboard.db`
export interface BoardBulletin {
  id: number;                 // Auto-incrementing primary key in `blackboard.db`
  author: string;             // Originating agent label (e.g. "Subagent (low)", "Flash: Gmail Sweep", "Astra")
  title: string;              // Concise summary headline
  content: string;            // Full Markdown findings payload
  pinned: number;             // 1 if pinned to top of board, else 0
  created_at: string;         // SQLite UTC/local timestamp string
}

// Fetches recent bulletins from the Shared Agent Blackboard
export async function getBoardBulletins(limit: number = 25): Promise<{ bulletins: BoardBulletin[]; count: number }> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  return apiFetch<{ bulletins: BoardBulletin[]; count: number }>(`/api/board?${params.toString()}`);
}

// Deletes a single bulletin by ID
export async function deleteBoardBulletin(bulletinId: number): Promise<{ status: string; deleted_id: number }> {
  return apiFetch<{ status: string; deleted_id: number }>(`/api/board/${bulletinId}`, {
    method: "DELETE",
  });
}

// Clears all unpinned bulletins
export async function clearBoardBulletins(): Promise<{ status: string; deleted_count: number }> {
  return apiFetch<{ status: string; deleted_count: number }>("/api/board", {
    method: "DELETE",
  });
}

