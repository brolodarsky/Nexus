/**
 * tools.ts — API client bindings and domain types for the Nexus Tools suite.
 * Interacts with FastAPI endpoints under /api/tools/ for the Resume Engine and future modules.
 */

import { apiFetch, API_BASE } from "./client";

// ── Domain Types & Data Contracts ────────────────────────────────────────────

// PageBudgetMetrics: Geometry measurements calculated by Chromium during headless rendering
export interface PageBudgetMetrics {
  file: string;                      // Document file stem (e.g. "Resume - Master")
  pages: number;                     // Total number of pages spanned (e.g. 1, 2)
  contentHeightPx: number;           // Measured scrollHeight of content in pixels
  pageHeightPx: number;              // Target Letter single-page height capacity (998px)
  lastPageFillPct: number;           // Percentage of final page occupied (0 - 100+%)
  roomRemainingPx: number;           // Pixel headroom remaining on final page
  approxBulletsRemaining: number;    // Estimated bullet points that can still fit before spillover
  verdict: "GOOD FIT" | "TIGHT FIT" | "ROOM" | "UNDERFILL" | "OVERFLOW" | string;
  measured_at?: string;              // ISO timestamp of when calculation took place
}

// ResumeDocument: Summary record of a resume or cover letter discovered in Vault portfolio
export interface ResumeDocument {
  id: string;                        // Relative identifier (e.g. "Resumes/Resume - Master.md")
  name: string;                      // Display title (e.g. "Resume - Master (Active Operations)")
  category: "resume" | "cover_letter"; // Semantic category
  category_label: string;            // Formatted display badge ("Resume" | "Cover Letter")
  path: string;                      // Absolute disk path
  relative_path: string;             // Project-relative path
  size_bytes: number;                // Markdown source file size
  modified_at: string;               // ISO 8601 modification timestamp
  has_pdf: bool_pdf;                 // Whether .pdf artifact exists on disk
  has_docx: bool_docx;               // Whether .docx artifact exists on disk
  pdf_path?: string | null;          // Absolute path to compiled .pdf
  docx_path?: string | null;         // Absolute path to compiled .docx
  pdf_size_bytes?: number | null;    // Compiled PDF byte size
  docx_size_bytes?: number | null;   // Compiled Word docx byte size
  pdf_modified_at?: string | null;   // PDF compilation timestamp
  docx_modified_at?: string | null;  // DOCX compilation timestamp
  metrics?: PageBudgetMetrics | null;// Last recorded page metrics
}
type bool_pdf = boolean;
type bool_docx = boolean;

// DocumentDetail: Detailed document inspection payload including raw markdown text
export interface DocumentDetail {
  id: string;
  name: string;
  path: string;
  relative_path: string;
  content: string;                   // Raw markdown source text
  lines_count: number;               // Total lines
  words_count: number;               // Total word count
  characters_count: number;          // Total character count
  modified_at: string;
  has_pdf: boolean;
  has_docx: boolean;
  pdf_path?: string | null;
  docx_path?: string | null;
  metrics?: PageBudgetMetrics | null;
}

// RenderResultRecord: Per-document outcome returned after compilation completes
export interface RenderResultRecord {
  name: string;
  path: string;
  relative_path: string;
  pdf_exists: boolean;
  docx_exists: boolean;
  pdf_path?: string | null;
  docx_path?: string | null;
  downloads_pdf?: string | null;
  downloads_docx?: string | null;
  metrics?: PageBudgetMetrics | null;
}

// RenderResponse: Aggregate execution summary returned by POST /api/tools/resume/render
export interface RenderResponse {
  success: boolean;
  exit_code: number;
  results: RenderResultRecord[];
  logs: string;                      // Standard output stream from headless compiler
  error?: string | null;
}

// DocumentListResponse: Container response for GET /api/tools/resume/documents
export interface DocumentListResponse {
  documents: ResumeDocument[];
  total: number;
}


// ── API Client Endpoints ─────────────────────────────────────────────────────

/**
 * Fetch all discovered resumes and cover letters in the portfolio.
 * Calls GET /api/tools/resume/documents
 */
export async function getResumeDocuments(): Promise<ResumeDocument[]> {
  const data = await apiFetch<DocumentListResponse>("/api/tools/resume/documents");
  return data.documents;
}

/**
 * Read the full markdown source and metrics for a specific document.
 * Calls GET /api/tools/resume/document?path=...
 *
 * @param path - Absolute or relative path to the markdown document.
 */
export async function getResumeDocument(path: string): Promise<DocumentDetail> {
  // encodeURIComponent: Escapes special characters (spaces, slashes) for safe URL query transmission
  const query = encodeURIComponent(path);
  return apiFetch<DocumentDetail>(`/api/tools/resume/document?path=${query}`);
}

/**
 * Write updated markdown content back to disk.
 * Calls PUT /api/tools/resume/document
 *
 * @param path - Target document file path.
 * @param content - New markdown text body.
 */
export async function saveResumeDocument(path: string, content: string): Promise<DocumentDetail> {
  return apiFetch<DocumentDetail>("/api/tools/resume/document", {
    method: "PUT",
    body: JSON.stringify({ path, content }),
  });
}

/**
 * Trigger the headless Chromium and Word docx compiler.
 * Calls POST /api/tools/resume/render
 *
 * @param files - Array of target paths or ["all"] to batch compile the entire portfolio.
 * @param formats - Target formats: ["pdf", "docx"], ["pdf"], or ["docx"].
 */
export async function renderResumeDocuments(
  files: string[],
  formats: string[] = ["pdf", "docx"]
): Promise<RenderResponse> {
  return apiFetch<RenderResponse>("/api/tools/resume/render", {
    method: "POST",
    body: JSON.stringify({ files, formats }),
  });
}

/**
 * Construct an absolute URL for streaming or downloading a compiled PDF or DOCX asset.
 *
 * @param path - Path to source markdown or compiled file.
 * @param format - "pdf" or "docx".
 * @param download - True to prompt a browser attachment download, false to stream inline.
 */
export function getResumeFileUrl(path: string, format: "pdf" | "docx" = "pdf", download = false): string {
  const encodedPath = encodeURIComponent(path);
  const dlParam = download ? "&download=true" : "";
  return `${API_BASE}/api/tools/resume/file?path=${encodedPath}&format=${format}${dlParam}`;
}
