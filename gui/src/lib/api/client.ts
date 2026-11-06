/**
 * client.ts — Base HTTP client, generic fetch wrapper, and custom error types for Nexus API.
 */

/**
 * Resolves the base URL for the Nexus FastAPI backend dynamically at runtime.
 *
 * Why this is dynamic instead of a static constant:
 * - When accessing the Next.js Control Panel from a remote device (e.g., a phone over Tailscale
 *   at `http://100.x.y.z:3000` or a local network client at `http://192.168.x.y:3000`), hardcoding
 *   `127.0.0.1:8000` causes browser requests to attempt connecting to the phone's own localhost.
 * - By dynamically extracting `window.location.hostname` in client environments, browser requests
 *   automatically route to the host machine's port 8000 without requiring an intermediary reverse proxy
 *   that could buffer or disrupt Server-Sent Events (SSE) streaming connections.
 *
 * Priority:
 * 1. Explicit `NEXT_PUBLIC_API_URL` override if set in the environment.
 * 2. Browser runtime: `http://${window.location.hostname}:8000` (LAN IP, Tailscale IP, MagicDNS, or localhost).
 * 3. Server-Side Rendering (SSR) fallback: `"http://127.0.0.1:8000"`.
 *
 * @returns The fully qualified HTTP origin string for API calls.
 */
export function getApiBase(): string {
  // If an explicit API URL is provided via environment variables, prioritize it
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  // typeof window !== "undefined": Guards against execution during Node.js SSR / build-time prerendering
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `http://${window.location.hostname}:8000`;
  }

  // Default fallback for SSR or non-browser environments
  return "http://127.0.0.1:8000";
}

// Backward-compatible constant fallback for static contexts or external modules.
// Callers should invoke getApiBase() to guarantee dynamic runtime host resolution in browser sessions.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// Interface describing the health status payload returned by GET /api/health
export interface HealthResponse {
  status: string;  // e.g. "ok"
  engine: string;  // e.g. "Nexus"
  version: string; // e.g. "2.0.0"
}

// Error subclass carrying the HTTP status + parsed FastAPI `detail`, so callers can branch on codes
// (e.g. HITL 409 `stale_base`) instead of string-matching messages. `extends Error` keeps `instanceof Error` true.
export class ApiError extends Error {
  status: number;   // HTTP status code (e.g. 404, 409)
  detail: unknown;  // Parsed `detail` field (string or structured object); `unknown` forces callers to narrow first
  constructor(status: number, detail: unknown, rawText: string) {
    super(`API ${status}: ${rawText}`); // Same message format as before, so existing error banners are unchanged
    this.status = status;
    this.detail = detail;
  }
}

// Generic fetch wrapper providing uniform error handling, JSON serialization, and typing
// <T>: Generic type parameter representing the expected shape of the response JSON (e.g., Conversation[], ModelsCatalogResponse)
// RequestInit: Built-in TypeScript interface for fetch options (method, headers, body, signal)
// Promise<T>: Asynchronous handle that resolves with the parsed JSON data of type T
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  // getApiBase(): Evaluates dynamic host at call time (e.g. phone browser on Tailscale/LAN vs localhost)
  const baseUrl = getApiBase();

  // await: Pauses function execution non-blockingly until the HTTP request completes
  // ...init: Object spread operator copying user-provided options into the request configuration
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  // res.ok: Returns true if HTTP status code is in the 200-299 range
  if (!res.ok) {
    const detail = await res.text(); // Read raw server error text (FastAPI error detail)
    let parsed: unknown = detail;
    // FastAPI errors are JSON `{"detail": ...}`; fall back to raw text if the body isn't JSON (e.g. proxy HTML)
    try { parsed = JSON.parse(detail)?.detail ?? detail; } catch { /* non-JSON body: keep raw text */ }
    throw new ApiError(res.status, parsed, detail);
  }

  // Type assertion 'as Promise<T>' casts the generic JSON result to the caller's expected interface
  return res.json() as Promise<T>;
}

// Checks API liveness and engine version
export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/health");
}

