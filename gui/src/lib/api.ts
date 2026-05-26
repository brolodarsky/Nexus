/**
 * api.ts — Typed API client for the Nexus Engine FastAPI backend.
 * All fetch calls are routed through these functions for consistency.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// ── Types ─────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  engine: string;
  version: string;
}

export interface AgentStatus {
  name: string;
  display_name: string;
  status: "idle" | "running" | "waiting_hitl" | "not_built" | "error";
  last_run: string | null;
  error_count: number;
  description: string;
}

export interface AskResponse {
  response: string;
  agent: string;
  timestamp: string;
}

export interface VaultStructureResponse {
  tree: string;
  path: string | null;
}

export interface NoteContentResponse {
  path: string;
  content: string;
}

// ── Helpers ───────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }

  return res.json() as Promise<T>;
}

// ── Endpoints ─────────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/health");
}

export async function getAgentStatus(): Promise<AgentStatus[]> {
  return apiFetch<AgentStatus[]>("/api/agents/status");
}

export async function askBrain(query: string): Promise<AskResponse> {
  return apiFetch<AskResponse>("/api/agents/ask", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}

export async function getVaultStructure(
  path?: string
): Promise<VaultStructureResponse> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch<VaultStructureResponse>(`/api/vault/structure${params}`);
}

export interface Transaction {
  id: number;
  agent_name: string;
  action_type: string;
  target_file: string;
  original_content: string | null;
  proposed_content: string;
  reasoning: string | null;
  status: string;
  created_at: string;
}

export async function getNote(path: string): Promise<NoteContentResponse> {
  return apiFetch<NoteContentResponse>(
    `/api/vault/note?path=${encodeURIComponent(path)}`
  );
}

export async function getPendingHitl(): Promise<Transaction[]> {
  return apiFetch<Transaction[]>("/api/hitl/pending");
}

export async function approveHitl(id: number): Promise<{status: string, message: string}> {
  return apiFetch<{status: string, message: string}>(`/api/hitl/${id}/approve`, { method: "POST" });
}

export async function rejectHitl(id: number): Promise<{status: string, message: string}> {
  return apiFetch<{status: string, message: string}>(`/api/hitl/${id}/reject`, { method: "POST" });
}
