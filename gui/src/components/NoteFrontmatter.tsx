"use client";

/**
 * NoteFrontmatter.tsx — Auto-collapsing Obsidian YAML frontmatter metadata inspector.
 *
 * Obsidian notes store document metadata (aliases, tags, instructions, type, dates) in
 * YAML frontmatter fences (`--- ... ---`) at the top of markdown files.
 * This component parses that frontmatter and displays it in an auto-collapsed cyber-styled bar:
 * - Collapsed by default: renders a compact pill banner with quick tag/type preview badges.
 * - Expanded: offers an interactive structured property inspector and raw YAML syntax viewer.
 */

import React, { useState, useMemo, useCallback } from "react";

// ParsedFrontmatter: Structured dictionary of extracted note properties
export interface ParsedFrontmatter {
  raw: string;                                // Complete raw YAML text string between the fences
  data: Record<string, unknown>;              // Normalized key-value pairs for arbitrary frontmatter keys
  tags: string[];                             // Normalized array of tag names (without leading '#')
  type?: string;                              // Note category (e.g. "instructions", "overview", "log")
  title?: string;                             // Explicit title override if specified in frontmatter
  aliases?: string[];                         // Alternative names for wiki-link resolution
  updated?: string;                           // Last-modified date stamp (e.g. "2026-11-05")
  instructions?: string[];                    // Self-managing operational rules or directives
  description?: string;                       // High-level summary of the note's purpose
}

// NoteFrontmatterProps: Input configuration for the collapsible metadata panel
export interface NoteFrontmatterProps {
  rawYaml: string;                            // Raw YAML block extracted from note header
  isExpanded?: boolean;                       // Controlled expansion state (defaults to collapsed)
  onToggleExpand?: () => void;                // Callback to toggle expansion state
  className?: string;                         // Optional extra CSS classes for layout adjustment
}

/**
 * parseYamlFrontmatter — Deterministic zero-dependency parser for Obsidian YAML frontmatter.
 * Handles strings, numbers, booleans, inline flow arrays (`[a, b]`), indented block lists (`- item`),
 * and quotes (`"..."` / `'...'`).
 *
 * @param raw - Raw YAML string between the `---` delimiters.
 * @returns ParsedFrontmatter object with normalized convenience getters.
 */
export function parseYamlFrontmatter(raw: string): ParsedFrontmatter {
  const result: Record<string, unknown> = {};
  if (!raw || !raw.trim()) {
    return { raw, data: {}, tags: [] };
  }

  const lines = raw.split(/\r?\n/);
  let currentKey: string | null = null;
  let currentList: string[] | null = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Case 1: Indented bullet item under a parent list key (e.g. `  - "Rule 1"`)
    const listMatch = line.match(/^\s+-\s*(.*)$/);
    if (listMatch && currentKey) {
      if (!currentList) {
        currentList = [];
        result[currentKey] = currentList;
      }
      let val = listMatch[1].trim();
      // Strip outer enclosing double or single quotes
      if (
        (val.startsWith('"') && val.endsWith('"')) ||
        (val.startsWith("'") && val.endsWith("'"))
      ) {
        val = val.slice(1, -1);
      }
      currentList.push(val);
      continue;
    }

    // Case 2: Top-level `key: value` or `key:` definition
    const keyValMatch = line.match(/^([a-zA-Z0-9_-]+):\s*(.*)$/);
    if (keyValMatch) {
      currentKey = keyValMatch[1].trim();
      currentList = null;
      let rawVal = keyValMatch[2].trim();

      if (rawVal === "") {
        // Empty value indicates upcoming indented list items or block mapping
        result[currentKey] = [];
        currentList = result[currentKey] as string[];
      } else if (rawVal.startsWith("[") && rawVal.endsWith("]")) {
        // Inline flow array: e.g. `[todo, tasks, pkm]`
        const items = rawVal
          .slice(1, -1)
          .split(",")
          .map((s) => s.trim().replace(/^['"]|['"]$/g, ""))
          .filter(Boolean);
        result[currentKey] = items;
      } else {
        // Scalar value: strip enclosing quotes if present
        if (
          (rawVal.startsWith('"') && rawVal.endsWith('"')) ||
          (rawVal.startsWith("'") && rawVal.endsWith("'"))
        ) {
          rawVal = rawVal.slice(1, -1);
        }
        result[currentKey] = rawVal;
      }
    }
  }

  // Normalize tags array from either list or comma string
  const rawTags = result["tags"];
  let tags: string[] = [];
  if (Array.isArray(rawTags)) {
    tags = rawTags.map((t) => String(t).replace(/^#/, "").trim()).filter(Boolean);
  } else if (typeof rawTags === "string" && rawTags.trim()) {
    tags = rawTags.split(",").map((t) => t.replace(/^#/, "").trim()).filter(Boolean);
  }

  // Normalize aliases array
  const rawAliases = result["aliases"];
  let aliases: string[] = [];
  if (Array.isArray(rawAliases)) {
    aliases = rawAliases.map(String).filter(Boolean);
  } else if (typeof rawAliases === "string" && rawAliases.trim()) {
    aliases = [rawAliases.trim()];
  }

  // Normalize instructions array
  const rawInstructions = result["instructions"];
  let instructions: string[] = [];
  if (Array.isArray(rawInstructions)) {
    instructions = rawInstructions.map(String).filter(Boolean);
  } else if (typeof rawInstructions === "string" && rawInstructions.trim()) {
    instructions = [rawInstructions.trim()];
  }

  return {
    raw,
    data: result,
    tags,
    type: typeof result["type"] === "string" ? result["type"] : undefined,
    title: typeof result["title"] === "string" ? result["title"] : undefined,
    aliases: aliases.length > 0 ? aliases : undefined,
    updated:
      typeof result["updated"] === "string"
        ? result["updated"]
        : typeof result["last-updated"] === "string"
        ? (result["last-updated"] as string)
        : typeof result["date"] === "string"
        ? (result["date"] as string)
        : undefined,
    instructions: instructions.length > 0 ? instructions : undefined,
    description: typeof result["description"] === "string" ? result["description"] : undefined,
  };
}

/**
 * NoteFrontmatter — Collapsible card component rendering note YAML metadata.
 * Auto-collapsed by default to maintain reading focus while keeping document properties one click away.
 */
export default function NoteFrontmatter({
  rawYaml,
  isExpanded: controlledExpanded,
  onToggleExpand,
  className = "",
}: NoteFrontmatterProps) {
  // Internal state used if component is rendered uncontrolled
  const [internalExpanded, setInternalExpanded] = useState(false);
  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;

  // Active tab in expanded mode: "properties" (structured table) or "raw" (code block)
  const [activeTab, setActiveTab] = useState<"properties" | "raw">("properties");
  // Feedback state when copying raw YAML to clipboard
  const [isCopied, setIsCopied] = useState(false);

  // Parse YAML memoized against the raw input string
  const parsed = useMemo(() => parseYamlFrontmatter(rawYaml), [rawYaml]);

  // Toggle handler respecting controlled vs uncontrolled patterns
  const handleToggle = useCallback(() => {
    if (onToggleExpand) {
      onToggleExpand();
    } else {
      setInternalExpanded((prev) => !prev);
    }
  }, [onToggleExpand]);

  // Copy raw YAML content to clipboard
  const handleCopyYaml = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      navigator.clipboard.writeText(rawYaml);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    },
    [rawYaml]
  );

  const propertyKeys = Object.keys(parsed.data);
  if (propertyKeys.length === 0) return null;

  return (
    <div
      className={`rounded-xl border border-border-subtle bg-bg-secondary/40 backdrop-blur-sm transition-all overflow-hidden ${className} ${
        isExpanded ? "shadow-lg border-border-accent/40" : "hover:border-border-accent/30"
      }`}
    >
      {/* ── Collapsed / Header Summary Bar ──────────────────────────────── */}
      <div
        onClick={handleToggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            handleToggle();
          }
        }}
        tabIndex={0}
        role="button"
        aria-expanded={isExpanded}
        aria-label="Toggle Note Frontmatter Metadata"
        className="px-4 py-2.5 flex items-center justify-between gap-3 cursor-pointer select-none group transition-colors hover:bg-bg-secondary/60"
      >
        <div className="flex items-center gap-2.5 flex-wrap min-w-0 flex-1">
          {/* Metadata Pill Badge */}
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[0.7rem] font-semibold tracking-wider uppercase bg-accent-cyan/10 border border-accent-cyan/30 text-accent-cyan shrink-0">
            <span className="text-xs">🏷️</span>
            <span>Metadata</span>
          </span>

          {/* Note Type Badge (if present) */}
          {parsed.type && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[0.68rem] font-medium bg-accent-amber/10 border border-accent-amber/25 text-accent-amber shrink-0">
              type: {parsed.type}
            </span>
          )}

          {/* Quick Tags Chips (up to 3 chips + overflow count) */}
          {parsed.tags.length > 0 && (
            <div className="flex items-center gap-1 flex-wrap">
              {parsed.tags.slice(0, 3).map((tag) => (
                <span
                  key={tag}
                  className="px-1.5 py-0.5 rounded text-[0.65rem] font-mono bg-bg-surface text-text-secondary border border-border-subtle"
                >
                  #{tag}
                </span>
              ))}
              {parsed.tags.length > 3 && (
                <span className="text-[0.65rem] text-text-muted font-mono">
                  +{parsed.tags.length - 3}
                </span>
              )}
            </div>
          )}

          {/* Last Updated Timestamp */}
          {parsed.updated && (
            <span className="text-[0.68rem] text-text-muted font-mono hidden sm:inline">
              📅 {parsed.updated}
            </span>
          )}

          {/* Properties Count */}
          <span className="text-[0.65rem] font-mono text-text-muted px-1.5 py-0.5 rounded bg-bg-surface shrink-0">
            {propertyKeys.length} {propertyKeys.length === 1 ? "field" : "fields"}
          </span>
        </div>

        {/* Expand / Collapse Indicator */}
        <div className="flex items-center gap-1.5 shrink-0 text-text-muted group-hover:text-accent-cyan transition-colors text-xs font-medium">
          <span className="hidden sm:inline text-[0.72rem]">
            {isExpanded ? "Collapse" : "Expand"}
          </span>
          <svg
            className={`w-4 h-4 transition-transform duration-200 ${
              isExpanded ? "rotate-180 text-accent-cyan" : "rotate-0"
            }`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      {/* ── Expanded Detail Panel ────────────────────────────────────────── */}
      {isExpanded && (
        <div className="border-t border-border-subtle/80 bg-bg-primary/50 animate-fade-in-up">
          {/* Controls sub-header: Tab switcher and copy action */}
          <div className="px-4 py-2 border-b border-border-subtle/60 flex items-center justify-between gap-2 flex-wrap text-xs bg-bg-secondary/30">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setActiveTab("properties")}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  activeTab === "properties"
                    ? "bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30"
                    : "text-text-secondary hover:text-text-primary hover:bg-bg-surface"
                }`}
              >
                Structured Properties
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("raw")}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  activeTab === "raw"
                    ? "bg-accent-cyan/15 text-accent-cyan border border-accent-cyan/30"
                    : "text-text-secondary hover:text-text-primary hover:bg-bg-surface"
                }`}
              >
                Raw YAML
              </button>
            </div>

            {/* Copy YAML Button */}
            <button
              type="button"
              onClick={handleCopyYaml}
              className="px-2.5 py-1 rounded-lg border border-border-subtle bg-bg-surface text-text-secondary hover:text-accent-cyan text-xs font-medium flex items-center gap-1.5 transition-all"
              title="Copy frontmatter YAML to clipboard"
            >
              {isCopied ? (
                <>
                  <span className="text-accent-emerald">✓</span>
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <rect x="9" y="9" width="13" height="13" rx="2" />
                    <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                  </svg>
                  <span>Copy YAML</span>
                </>
              )}
            </button>
          </div>

          {/* Tab 1: Structured Properties Table */}
          {activeTab === "properties" && (
            <div className="p-4 space-y-2.5 text-xs">
              <div className="grid grid-cols-1 md:grid-cols-[160px_1fr] gap-2 md:gap-4 items-start">
                {propertyKeys.map((key) => {
                  const val = parsed.data[key];
                  return (
                    <React.Fragment key={key}>
                      {/* Property Key */}
                      <div className="font-mono text-accent-cyan/90 font-medium break-all pt-1">
                        {key}:
                      </div>

                      {/* Property Value */}
                      <div className="text-text-primary/90 break-words pb-2 border-b border-border-subtle/40 md:border-b-0">
                        {/* Rendering logic by property type */}
                        {key === "tags" && Array.isArray(val) ? (
                          <div className="flex items-center gap-1.5 flex-wrap">
                            {val.map((t, idx) => (
                              <span
                                key={idx}
                                className="px-2 py-0.5 rounded-md bg-accent-cyan/10 border border-accent-cyan/25 text-accent-cyan font-mono text-[0.7rem]"
                              >
                                #{String(t).replace(/^#/, "")}
                              </span>
                            ))}
                          </div>
                        ) : key === "aliases" && Array.isArray(val) ? (
                          <div className="flex items-center gap-1.5 flex-wrap">
                            {val.map((a, idx) => (
                              <span
                                key={idx}
                                className="px-2 py-0.5 rounded-md bg-accent-violet/10 border border-accent-violet/25 text-accent-violet font-mono text-[0.7rem]"
                              >
                                📄 {String(a)}
                              </span>
                            ))}
                          </div>
                        ) : key === "instructions" && Array.isArray(val) ? (
                          <ul className="list-disc pl-5 space-y-1.5 text-text-secondary leading-relaxed marker:text-accent-cyan/70">
                            {val.map((inst, idx) => (
                              <li key={idx} className="pl-1">
                                {String(inst)}
                              </li>
                            ))}
                          </ul>
                        ) : Array.isArray(val) ? (
                          <ul className="list-disc pl-5 space-y-1 text-text-secondary marker:text-accent-cyan/70">
                            {val.map((item, idx) => (
                              <li key={idx} className="pl-1">
                                {String(item)}
                              </li>
                            ))}
                          </ul>
                        ) : typeof val === "object" && val !== null ? (
                          <pre className="font-mono text-[0.7rem] bg-[#05070e] p-2 rounded-lg overflow-x-auto text-zinc-300">
                            {JSON.stringify(val, null, 2)}
                          </pre>
                        ) : (
                          <span className="font-sans leading-relaxed text-text-primary">
                            {String(val)}
                          </span>
                        )}
                      </div>
                    </React.Fragment>
                  );
                })}
              </div>
            </div>
          )}

          {/* Tab 2: Raw YAML Code Block */}
          {activeTab === "raw" && (
            <div className="p-4">
              <pre className="bg-[#05070e] border border-border-subtle rounded-xl p-3.5 font-mono text-xs leading-relaxed text-zinc-200 overflow-x-auto shadow-inner">
                {rawYaml}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
