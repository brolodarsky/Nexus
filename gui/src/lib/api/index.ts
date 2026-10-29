/**
 * index.ts — Barrel file for the Nexus API client modules.
 * Re-exports all domain types, endpoints, and helpers to preserve backwards compatibility
 * with `@/lib/api` imports across all UI pages and components.
 */

export * from "./client";
export * from "./stream";
export * from "./agents";
export * from "./vault";
export * from "./hitl";
export * from "./board";
export * from "./tools";

