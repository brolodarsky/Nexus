/**
 * vault.ts — Knowledge vault browsing, note content retrieval, structure tree, and audio podcast endpoints.
 * Connects to FastAPI `/api/vault` routes.
 */

import { apiFetch, API_BASE } from "./client";

// Interface for tree view representation of the Vault folder structure
export interface VaultStructureResponse {
  tree: string;               // Formatted ASCII/indented folder listing
  path: string | null;        // Scoped root directory path or null for entire vault
}

// Interface for raw markdown file content loaded from the Vault
export interface NoteContentResponse {
  path: string;               // Relative vault path (e.g. "3. Operations/My Skills.md")
  content: string;            // Full UTF-8 text content of the note
}

// Interface for directory entries when browsing the file system
export interface VaultEntry {
  name: string;               // Base file or folder name
  path: string;               // Relative path from vault root
  type: "file" | "directory"; // Discriminated union for folder vs file rendering
  size?: number;              // File size in bytes (omitted for directories)
  mtime?: number;             // Last modified timestamp in seconds since epoch
  has_audio: boolean;         // True if a companion synthesized podcast .mp3 exists
}

// Interface representing lightweight metadata for all markdown notes in the Vault
// Used for search, filtering, and pinning notes to the Home page
export interface VaultNoteSummary {
  name: string;               // Base filename with extension (e.g. "Goals.md")
  title: string;              // Clean display title stripped of .md extension (e.g. "Goals")
  path: string;               // Vault-relative path using forward slashes
  folder: string;             // Vault-relative parent folder or "Vault Root"
  size?: number;              // File size in bytes
  mtime?: number;             // POSIX timestamp of last modification in seconds since epoch
}

// Fetches the structured tree of vault directories
export async function getVaultStructure(
  path?: string
): Promise<VaultStructureResponse> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch<VaultStructureResponse>(`/api/vault/structure${params}`);
}

// Loads full note content for display in the Vault Browser
export async function getNote(path: string): Promise<NoteContentResponse> {
  return apiFetch<NoteContentResponse>(
    `/api/vault/note?path=${encodeURIComponent(path)}`
  );
}

// Lists files and subfolders within a specific vault directory path
export async function listVault(path?: string): Promise<VaultEntry[]> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return apiFetch<VaultEntry[]>(`/api/vault/list${params}`);
}

// Fetches a flat list of all markdown notes in the Vault for fast search, filtering, and pinning
// Promise<VaultNoteSummary[]>: Resolves with an array of note descriptors sorted alphabetically
export async function getAllVaultNotes(): Promise<VaultNoteSummary[]> {
  return apiFetch<VaultNoteSummary[]>("/api/vault/notes");
}

// Triggers background TTS podcast audio generation for a specific markdown note
export async function generatePodcast(path: string, force: boolean = false): Promise<any> {
  return apiFetch<any>("/api/vault/podcast/generate", {
    method: "POST",
    body: JSON.stringify({ path, force }),
  });
}

// Formats direct audio streaming URL for playing note podcasts in the browser
export function getPodcastAudioUrl(path: string): string {
  return `${API_BASE}/api/vault/podcast/download?path=${encodeURIComponent(path)}`;
}

