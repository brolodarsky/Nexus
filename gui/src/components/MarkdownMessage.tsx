"use client";

// memo: Higher-order React wrapper that skips re-rendering when props (`content`) are shallowly equal
// useMemo: Caches the regex-preprocessed Markdown string between renders unless `content` changes
// createContext, useContext: Supplies optional onWikiLinkClick callback to nested VaultNotePill components
import React, { memo, useMemo, createContext, useContext } from "react";
// Link: Next.js client-side router navigation for cross-page Vault note deep-linking
import Link from "next/link";
// ReactMarkdown: Renders raw Markdown strings into React DOM elements safely without `dangerouslySetInnerHTML`
// Components: TypeScript dictionary type mapping HTML tag names to custom React renderer functions
import ReactMarkdown, { type Components } from "react-markdown";
// remarkGfm: Remark plugin enabling GitHub-Flavored Markdown (tables, task checkboxes `- [ ]`, strikethrough, autolinks)
import remarkGfm from "remark-gfm";
// remarkMath: Remark plugin recognizing $inline$ and $$block$$ mathematical formulas
import remarkMath from "remark-math";
// rehypeKatex: Rehype plugin typesetting LaTeX math AST nodes via KaTeX
import rehypeKatex from "rehype-katex";
// PluggableList: Unified type definition for Remark/Rehype plugin tuples and configurations
import type { PluggableList } from "unified";

// ── Obsidian Wiki-Link Context ───────────────────────────────────────────────

// WikiLinkConfig: Configuration options and callbacks provided to nested VaultNotePill components
// - onWikiLinkClick: optional in-place selection callback (e.g. inside /vault to switch notes in-place)
// - openInNewTab: boolean indicating whether note pills navigating via Next.js <Link> should open in a new browser tab (target="_blank")
export interface WikiLinkConfig {
  onWikiLinkClick?: (target: string) => void;
  openInNewTab?: boolean;
}

// WikiLinkContext: Supplies optional in-place selection callback or navigation options to Vault note pills.
// Supports both a raw callback function `(target: string) => void` (legacy pattern) and a structured `WikiLinkConfig` object.
// If an in-place callback is provided (e.g. inside /vault), clicking a pill switches the active note in-place.
// If omitted (e.g. in /chat or /hitl), clicking navigates to `/vault?note=${target}` in a new tab.
export const WikiLinkContext = createContext<WikiLinkConfig | ((target: string) => void) | undefined>(undefined);

// ── Obsidian Wiki-Link & LaTeX Preprocessor & Rich Markdown Renderer ─

// PROSE_LATEX_SYMBOLS: Lookup map converting bare LaTeX arrow/operator commands in plain prose
// (when emitted without `$` math delimiters, e.g. `Step 1 \rightarrow Step 2`) into clean Unicode characters.
// Formal math equations inside `$...$` or `$$...$$` are preserved intact and rendered by KaTeX.
const PROSE_LATEX_SYMBOLS: Record<string, string> = {
  "\\longleftrightarrow": "↔",
  "\\Longleftrightarrow": "⇔",
  "\\leftrightarrow": "↔",
  "\\Leftrightarrow": "⇔",
  "\\longrightarrow": "→",
  "\\Longrightarrow": "⇒",
  "\\longleftarrow": "←",
  "\\Longleftarrow": "⇐",
  "\\rightarrow": "→",
  "\\Rightarrow": "⇒",
  "\\leftarrow": "←",
  "\\Leftarrow": "⇐",
  "\\updownarrow": "↕",
  "\\Uparrow": "⇑",
  "\\Downarrow": "⇓",
  "\\uparrow": "↑",
  "\\downarrow": "↓",
  "\\mapsto": "↦",
  "\\implies": "⇒",
  "\\iff": "⇔",
  "\\to": "→",
  "\\gets": "←",
  "\\approx": "≈",
  "\\equiv": "≡",
  "\\neq": "≠",
  "\\leq": "≤",
  "\\geq": "≥",
};

// BARE_PROSE_LATEX_PATTERN: Matches bare LaTeX arrow/operator commands (longest-first) outside of math blocks.
const BARE_PROSE_LATEX_PATTERN = new RegExp(
  Object.keys(PROSE_LATEX_SYMBOLS)
    .sort((a, b) => b.length - a.length)
    .map((k) => k.replace(/\\/g, "\\\\") + "\\b")
    .join("|"),
  "g"
);

// escapeProseCurrency: Escapes standalone currency expressions (e.g. `$41.20`, `$150k`, `$50–$100`)
// into `\$...` so remark-math does not mistakenly pair conversational currency figures across prose.
// If the number is immediately followed by a closing `$` (e.g. `$0.4$` or `$100$`), it is recognized
// as an intentional single-number math literal and preserved without escaping.
function escapeProseCurrency(text: string): string {
  return text.replace(/(?<![\w$\\])\$(\d+(?:\.\d+)?(?:[kKmMbB])?)/g, (match, _num, offset, str) => {
    const nextChar = str[offset + match.length];
    if (nextChar === "$") {
      // Followed immediately by closing $ -> math literal (e.g. `$0.4$`), do not escape
      return match;
    }
    return `\\${match}`;
  });
}

// Strips trailing `.md` from note display labels so `[[Plan.md]]`, `` `Plan.md` ``, and `[[Plan]]` render identically
function formatNoteDisplay(rawDisplay: string): string {
  return rawDisplay.trim().replace(/\.md$/i, "");
}

// VaultNotePill: Renders an Obsidian [[Wiki-Link]] or Markdown note title as an unbroken glowing cyan badge.
// Interacts with WikiLinkContext to either perform an in-place note switch or open via Next.js <Link> in a new tab.
function VaultNotePill({ target, children }: { target: string; children: React.ReactNode }) {
  const context = useContext(WikiLinkContext);
  // Support both legacy functional context and structured WikiLinkConfig object
  const onWikiLinkClick = typeof context === "function" ? context : context?.onWikiLinkClick;
  // Default openInNewTab to true when onWikiLinkClick is omitted so external/chat contexts don't blow away active threads
  const openInNewTab = typeof context === "object" && context !== null && "openInNewTab" in context
    ? Boolean(context.openInNewTab)
    : true;

  // Strip heading anchors (e.g. "Table of Contents#6. Engineering" -> "Table of Contents") so the URL query param targets the file cleanly
  const baseTarget = target.split("#")[0].trim();

  const isExternalTab = !onWikiLinkClick && openInNewTab;

  const badge = (
    <span
      title={onWikiLinkClick ? `Vault Note: ${target}` : `Vault Note: ${target} (Click to open in new tab)`}
      className="inline-flex items-center gap-1.5 px-2 py-0.5 mx-0.5 my-0.5 rounded-lg text-xs font-medium bg-accent-cyan/10 border border-accent-cyan/25 text-accent-cyan hover:bg-accent-cyan/20 hover:border-accent-cyan/40 hover:shadow-[0_0_12px_rgba(56,189,248,0.18)] transition-all cursor-pointer align-baseline select-none group"
    >
      <span className="opacity-70 group-hover:opacity-100 text-[0.7rem] shrink-0 transition-opacity">📄</span>
      <span className="group-hover:underline underline-offset-2">{children}</span>
      {isExternalTab && (
        <span className="opacity-40 group-hover:opacity-80 text-[0.65rem] shrink-0 transition-opacity -ml-0.5" aria-hidden="true">
          ↗
        </span>
      )}
    </span>
  );

  if (onWikiLinkClick) {
    return (
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onWikiLinkClick(target);
        }}
        className="inline border-0 bg-transparent p-0 align-baseline text-left font-normal cursor-pointer"
      >
        {badge}
      </button>
    );
  }

  return (
    <Link
      href={`/vault?note=${encodeURIComponent(baseTarget)}`}
      target={openInNewTab ? "_blank" : undefined}
      rel={openInNewTab ? "noopener noreferrer" : undefined}
      className="inline align-baseline no-underline"
    >
      {badge}
    </Link>
  );
}

// CALLOUT_THEMES: Theming configuration for Obsidian-style callout blocks (`> [!NOTE]`, `> [!TIP]`, etc.)
const CALLOUT_THEMES: Record<string, { icon: string; border: string; bg: string; text: string; label: string }> = {
  NOTE: { icon: "📝", border: "border-accent-cyan/40", bg: "bg-accent-cyan/10", text: "text-accent-cyan", label: "Note" },
  INFO: { icon: "ℹ️", border: "border-accent-cyan/40", bg: "bg-accent-cyan/10", text: "text-accent-cyan", label: "Info" },
  TIP: { icon: "💡", border: "border-accent-emerald/40", bg: "bg-accent-emerald/10", text: "text-accent-emerald", label: "Tip" },
  WARNING: { icon: "⚠️", border: "border-accent-amber/40", bg: "bg-accent-amber/10", text: "text-accent-amber", label: "Warning" },
  CAUTION: { icon: "🚨", border: "border-accent-rose/40", bg: "bg-accent-rose/10", text: "text-accent-rose", label: "Caution" },
  IMPORTANT: { icon: "❗", border: "border-accent-rose/40", bg: "bg-accent-rose/10", text: "text-accent-rose", label: "Important" },
  DANGER: { icon: "🔥", border: "border-accent-rose/40", bg: "bg-accent-rose/10", text: "text-accent-rose", label: "Danger" },
  TODO: { icon: "📌", border: "border-accent-violet/40", bg: "bg-accent-violet/10", text: "text-accent-violet", label: "Todo" },
  EXAMPLE: { icon: "🔍", border: "border-accent-violet/40", bg: "bg-accent-violet/10", text: "text-accent-violet", label: "Example" },
};

/**
 * ObsidianCallout: Detects and renders callout banners (`> [!TYPE] Title`) with distinct iconography and colors.
 * Falls back to standard blockquote presentation if no callout pattern is found.
 */
function ObsidianCallout({ children }: { children: React.ReactNode }) {
  // Extract text from React child elements to check for `[!TYPE]` syntax
  const childArray = React.Children.toArray(children);
  const firstChild = childArray[0];

  if (React.isValidElement(firstChild)) {
    const pChildren = (firstChild.props as { children?: React.ReactNode })?.children;
    const textContent = Array.isArray(pChildren)
      ? pChildren.map((c) => (typeof c === "string" ? c : "")).join("")
      : typeof pChildren === "string"
      ? pChildren
      : "";

    const calloutMatch = textContent.match(/^\[!([a-zA-Z]+)\](?:\s+(.*))?/);
    if (calloutMatch) {
      const typeKey = calloutMatch[1].toUpperCase();
      const theme = CALLOUT_THEMES[typeKey] || CALLOUT_THEMES.NOTE;
      const customTitle = calloutMatch[2]?.trim() || theme.label;

      return (
        <div className={`my-3.5 rounded-xl border ${theme.border} ${theme.bg} p-3.5 space-y-2 text-xs`}>
          <div className={`flex items-center gap-2 font-semibold uppercase tracking-wider ${theme.text}`}>
            <span>{theme.icon}</span>
            <span>{customTitle}</span>
          </div>
          <div className="text-text-primary/90 leading-relaxed space-y-1">
            {childArray.slice(1)}
          </div>
        </div>
      );
    }
  }

  // Standard blockquote fallback
  return (
    <blockquote className="border-l-2 border-accent-cyan/70 bg-accent-cyan/5 px-3.5 py-2 my-2.5 rounded-r-xl text-text-secondary space-y-1">
      {children}
    </blockquote>
  );
}

// ── Markdown Code Fence Sanitizer & Splitter ─────────────────────────────────

// FenceStackFrame: Tracks an open code fence boundary within the line-by-line fence parser.
// - lineIndex: 0-based array index of the line where this code fence was declared
// - indent: Leading whitespace indentation (e.g. "  " or "\t") preceding the fence characters
// - char: The fence delimiter character, either "`" (backtick) or "~" (tilde)
// - count: Quantity of consecutive fence characters (e.g. 3 for "```", 4 for "````")
// - rawInfo: Full text following the fence characters on that line (e.g. "markdown", " json", "typescript")
// - hasNested: Flag indicating whether an inner code block was opened while this block was active
// - maxInnerFenceCount: Maximum delimiter length observed among all nested inner fences
interface FenceStackFrame {
  lineIndex: number;
  indent: string;
  char: string;
  count: number;
  rawInfo: string;
  hasNested: boolean;
  maxInnerFenceCount: number;
}

// CodeBlockSegment: Represents a contiguous slice of Markdown text categorized as either code or plain prose.
// Used by splitFencedCodeBlocks to safeguard multi-backtick blocks during Obsidian and KaTeX pre-processing.
export interface CodeBlockSegment {
  isCode: boolean;
  text: string;
}

/**
 * sanitizeMarkdownFences: Deterministic healing pass for malformed or nested LLM code fences.
 *
 * Why this exists:
 * LLMs frequently generate prompts, README templates, or tutorials that contain example code blocks.
 * Almost universally, LLMs emit standard triple backticks (```) for BOTH the outer container and the
 * inner example snippet. Under the CommonMark specification (§4.5):
 * 1. Code blocks do NOT nest.
 * 2. Any line with at least 3 backticks and NO info string closes the active code block immediately.
 *
 * Consequently, when the inner example snippet closes, CommonMark terminates the outer block prematurely.
 * Subsequent lines leak into plain prose (re-starting numbered lists at "1."), and the outer block's
 * intended closing fence is misinterpreted as OPENING a brand new code block—swallowing subsequent
 * headings, answers, and note links into an inverted, monospaced code container.
 *
 * How this heals it:
 * 1. Scans fences line-by-line using a fence stack.
 * 2. When an open code block encounters another fence with an info string (e.g. ```` ```markdown ```` or ```` ```json ````)
 *    or relative sub-indentation, it recognizes that an inner block was spawned.
 * 3. Upon reaching the matching closing fence, it automatically promotes the outer block's opening and
 *    closing fences to `N = Math.max(outerCount, maxInnerCount + 1, 4)` backticks (e.g. ```` ```` ````).
 *    Under CommonMark, an outer fence of length 4+ treats all inner 3-backtick lines as literal code text!
 * 4. Automatically detects unclosed trailing fences (common in streaming or token-truncated LLM outputs)
 *    and appends the matching closing fence to prevent downstream layout corruption.
 */
export function sanitizeMarkdownFences(raw: string): string {
  if (!raw) return "";

  const lines = raw.split("\n");
  // Matches a code fence line: optional leading indent, 3+ backticks or tildes, followed by raw info string
  const fenceRegex = /^([ \t]*)(`{3,}|~{3,})([^\n`~]*)$/;

  const stack: FenceStackFrame[] = [];
  // Map of lineIndex -> replacement string for modified opening and closing fence lines
  const modifications = new Map<number, string>();

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const match = line.match(fenceRegex);
    if (!match) continue;

    const indent = match[1];
    const fenceChars = match[2];
    const char = fenceChars[0];
    const count = fenceChars.length;
    const rawInfo = match[3];
    const info = rawInfo.trim();

    if (stack.length === 0) {
      // Starting a top-level code block
      stack.push({
        lineIndex: i,
        indent,
        char,
        count,
        rawInfo,
        hasNested: false,
        maxInnerFenceCount: 0,
      });
    } else {
      const currentBlock = stack[stack.length - 1];

      if (stack.length === 1) {
        // In CommonMark, a closing fence CANNOT have an info string.
        // Therefore, any fence line with a non-empty info string (e.g. ```markdown or ```json),
        // or one that is indented deeper than the outer block, is unambiguously opening a nested block.
        const isInnerOpen = info !== "" || indent.length > currentBlock.indent.length;

        if (isInnerOpen) {
          stack.push({
            lineIndex: i,
            indent,
            char,
            count,
            rawInfo,
            hasNested: false,
            maxInnerFenceCount: 0,
          });
          currentBlock.hasNested = true;
          currentBlock.maxInnerFenceCount = Math.max(currentBlock.maxInnerFenceCount, count);
        } else if (char === currentBlock.char && count >= currentBlock.count && info === "") {
          // Cleanly closing the top-level block
          const top = stack.pop()!;
          if (top.hasNested) {
            // Promote outer opening and closing fences so CommonMark encapsulates all inner fences
            const newCount = Math.max(top.count, top.maxInnerFenceCount + 1, 4);
            modifications.set(top.lineIndex, `${top.indent}${top.char.repeat(newCount)}${top.rawInfo}`);
            modifications.set(i, `${indent}${char.repeat(newCount)}`);
          }
        }
      } else {
        // stack.length > 1: currently traversing inside a nested code block
        const isDeeperOpen = info !== "" || indent.length > currentBlock.indent.length;

        if (isDeeperOpen) {
          // Deeper nested code block (e.g. triple nesting)
          stack.push({
            lineIndex: i,
            indent,
            char,
            count,
            rawInfo,
            hasNested: false,
            maxInnerFenceCount: 0,
          });
          const parent = stack[0];
          parent.hasNested = true;
          parent.maxInnerFenceCount = Math.max(parent.maxInnerFenceCount, count);
        } else if (char === currentBlock.char && count >= currentBlock.count && info === "") {
          // Closing the inner nested block
          const closed = stack.pop()!;
          const parent = stack[0];
          parent.hasNested = true;
          parent.maxInnerFenceCount = Math.max(parent.maxInnerFenceCount, closed.count, count);
        }
      }
    }
  }

  // Handle any unclosed blocks (e.g. streaming LLM responses or token truncation)
  let trailingCloses = "";
  while (stack.length > 0) {
    const unclosed = stack.pop()!;
    if (stack.length === 0) {
      // Top-level block reached the end of the text without a closing fence
      if (unclosed.hasNested) {
        const newCount = Math.max(unclosed.count, unclosed.maxInnerFenceCount + 1, 4);
        modifications.set(unclosed.lineIndex, `${unclosed.indent}${unclosed.char.repeat(newCount)}${unclosed.rawInfo}`);
        trailingCloses += `\n${unclosed.indent}${unclosed.char.repeat(newCount)}`;
      } else {
        trailingCloses += `\n${unclosed.indent}${unclosed.char.repeat(unclosed.count)}`;
      }
    }
  }

  // Reassemble lines with modifications applied
  let result = lines.map((line, idx) => (modifications.has(idx) ? modifications.get(idx)! : line)).join("\n");
  if (trailingCloses) {
    result += trailingCloses;
  }

  return result;
}

/**
 * splitFencedCodeBlocks: Slices a Markdown document into alternating prose and code block segments.
 *
 * Accommodates fenced code blocks of arbitrary length (3, 4, 5+ backticks or tildes).
 * Guarantees that joining all segment texts matches the input string exactly, ensuring
 * zero character loss or text drift during subsequent Obsidian wiki-link or LaTeX transformations.
 */
export function splitFencedCodeBlocks(raw: string): CodeBlockSegment[] {
  // Regex matching any fenced code block (3+ backticks or tildes) with matching closing fence
  const FENCED_BLOCK_PATTERN = /(?:^|\n)([ \t]*(`{3,}|~{3,})[^\n`~]*\n[\s\S]*?\n[ \t]*\2[ \t]*(?:\n|$))/g;
  const segments: CodeBlockSegment[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = FENCED_BLOCK_PATTERN.exec(raw)) !== null) {
    // If the matched string started with a newline separator, exclude it from the code slice
    const matchStart = match.index + (match[0].startsWith("\n") ? 1 : 0);
    const codeBlock = match[1];

    if (matchStart > lastIndex) {
      segments.push({ isCode: false, text: raw.slice(lastIndex, matchStart) });
    }
    segments.push({ isCode: true, text: codeBlock });
    lastIndex = matchStart + codeBlock.length;
    FENCED_BLOCK_PATTERN.lastIndex = lastIndex;
  }

  if (lastIndex < raw.length) {
    segments.push({ isCode: false, text: raw.slice(lastIndex) });
  }

  return segments;
}

// Converts Obsidian `[[Target|Alias]]` / `[[Target]]` syntax, backticked `.md` note titles (`Plan.md`),
// escapes conversational currency figures, heals malformed/nested code fences, and normalizes LaTeX math delimiters outside of fenced code blocks.
export function preprocessObsidianMarkdown(raw: string): string {
  if (!raw) return "";

  // 1. Sanitize code fences: promote nested outer fences to 4+ backticks and auto-close unclosed streaming blocks
  const sanitized = sanitizeMarkdownFences(raw);

  // 2. Split on fenced code blocks (handling 3, 4, 5+ backticks/tildes) so raw drafts inside code fences stay untouched
  const segments = splitFencedCodeBlocks(sanitized);

  return segments
    .map((segment) => {
      // Code blocks remain completely untouched by prose transforms
      if (segment.isCode) return segment.text;

      // 1. Escape conversational currency amounts ($150k, $41.20, $50–$100) before math delimiter evaluation
      let processed = escapeProseCurrency(segment.text);

      // 2. Normalize LaTeX delimiter variants \(...\) -> $...$ and \[...\] -> $$...$$
      processed = processed
        .replace(/\\\(([\s\S]*?)\\\)/g, (_m, inner) => `$${inner}$`)
        .replace(/\\\[([\s\S]*?)\\\]/g, (_m, inner) => `\n$$\n${inner.trim()}\n$$\n`);

      // 3. Auto-escape unescaped underscores inside \text{...} in math so snake_case identifiers don't fail in KaTeX
      processed = processed.replace(/\\text\{([^}]+)\}/g, (_m, inner) => {
        return `\\text{${inner.replace(/(?<!\\)_/g, "\\_")}}`;
      });

      // 4. Split by display math ($$...$$) and inline math ($...$) so prose-specific link and arrow replacements
      //    only execute on plain conversational text and never mutate KaTeX math expressions
      const mathSegments = processed.split(/(\$\$[\s\S]*?\$\$|(?<!\\)\$(?!\s)[^$\n]+?(?<!\s)\$)/g);

      return mathSegments
        .map((subSegment, mathIndex) => {
          // Odd indices are math blocks ($$...$$ or $...$)
          if (mathIndex % 2 === 1) {
            return subSegment;
          }

          // A. Match backtick-wrapped wikilinks (`[[target|alias]]` or ``[[target]]``) OR bare wikilinks ([[target|alias]] or [[target]])
          let prose = subSegment.replace(
            /`{1,2}\s*\[\[([^\]|]+)(?:\|([^\]]+))?\]\]\s*`{1,2}|\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g,
            (_match, t1?: string, a1?: string, t2?: string, a2?: string) => {
              const target = (t1 || t2 || "").trim();
              const alias = (a1 || a2 || "").trim();
              const rawDisplay = alias || target.split("/").pop() || target;
              const display = formatNoteDisplay(rawDisplay);
              const encodedTarget = encodeURIComponent(target);
              return `[${display}](#wikilink:${encodedTarget})`;
            }
          );

          // B. Convert backtick-wrapped Markdown note titles (e.g. `1.1. Section Instructions.md`, `Plan.md`, `Tasks.md`, `Toilet/Kohler.md`)
          //    into #wikilink: links so all note titles and paths share the unified VaultNotePill representation instead of splitting
          //    between inline code boxes and Vault pills. Excludes CLI commands and wildcard/placeholder patterns (`Project - *.md`, `<Name>.md`).
          prose = prose.replace(
            /`([^`\n*?<>"{}$]+\.md)`/g,
            (match, noteFile: string) => {
              const trimmed = noteFile.trim();
              if (/^(python|uv|git|npm|node|npx|pip|pytest|ruff)\b/i.test(trimmed) || trimmed.startsWith("-")) {
                return match;
              }
              const cleanTarget = trimmed.replace(/^(\/?Vault\/|\.\/)/i, "");
              const display = formatNoteDisplay(cleanTarget.split("/").pop() || cleanTarget);
              const encodedTarget = encodeURIComponent(cleanTarget);
              return `[${display}](#wikilink:${encodedTarget})`;
            }
          );

          // C. Convert bare LaTeX arrow/operator commands in prose (e.g. `Step 1 \rightarrow Step 2`)
          prose = prose.replace(
            BARE_PROSE_LATEX_PATTERN,
            (match) => PROSE_LATEX_SYMBOLS[match] ?? match
          );

          return prose;
        })
        .join("");
    })
    .join("");
}

// REMARK_PLUGINS: Module-level static Remark plugin array passed to ReactMarkdown.
// Hoisting this outside the component prevents allocating a new array reference on every render,
// preserving ReactMarkdown's internal unified/remark processor cache across re-renders.
// Combines remarkGfm (tables, checklists, strikethrough) and remarkMath ($inline$, $$block$$ math).
const REMARK_PLUGINS: PluggableList = [remarkGfm, remarkMath];

// REHYPE_PLUGINS: Module-level static Rehype plugin array for KaTeX mathematical typesetting.
// Configured with `strict: false` and `throwOnError: false` so malformed or non-standard LaTeX
// degrades gracefully without crashing the UI thread.
const REHYPE_PLUGINS: PluggableList = [[rehypeKatex, { strict: false, throwOnError: false }]];

// MARKDOWN_COMPONENTS: Module-level static custom element renderer map for ReactMarkdown.
// Keeping this object reference stable avoids tearing down and remounting DOM subtrees when parent components re-render.
const MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => (
    <h1 className="text-xl md:text-2xl font-bold tracking-tight text-text-primary mt-6 mb-3 pb-2 border-b border-border-subtle first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-lg md:text-xl font-semibold tracking-tight text-accent-cyan mt-5 mb-2 pb-1.5 border-b border-border-subtle/60 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base font-semibold text-accent-violet mt-4 mb-1.5 first:mt-0">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mt-3 mb-1">
      {children}
    </h4>
  ),
  p: ({ children }) => <p className="leading-relaxed last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-5 space-y-1.5 my-2 marker:text-accent-cyan/70">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1.5 my-2 marker:text-accent-cyan/80 font-medium">{children}</ol>,
  li: ({ children, className }) => {
    // If remark-gfm parsed a task checkbox item, remove the bullet styling so checkboxes align neatly
    const isTask = Boolean(className?.includes("task-list-item"));
    return (
      <li className={`leading-relaxed text-text-primary/95 pl-0.5 ${isTask ? "list-none -ml-4 flex items-baseline gap-2" : ""}`}>
        {children}
      </li>
    );
  },
  strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
  em: ({ children }) => <em className="italic text-text-secondary">{children}</em>,
  hr: () => <hr className="my-4 border-border-subtle" />,
  blockquote: ({ children }) => <ObsidianCallout>{children}</ObsidianCallout>,
  a: ({ href, children }) => {
    // 1. Render Obsidian `[[Wiki-Links]]` preprocessed into `#wikilink:` as styled Vault note pills
    if (href?.startsWith("#wikilink:")) {
      const target = decodeURIComponent(href.replace("#wikilink:", ""));
      return <VaultNotePill target={target}>{children}</VaultNotePill>;
    }

    // 2. Intercept deep-links to `/vault?note=...` so they share unified VaultNotePill presentation and tab handling
    if (href?.startsWith("/vault?note=") || href?.startsWith("vault?note=")) {
      const match = href.match(/[?&]note=([^&#]+)/);
      if (match) {
        const target = decodeURIComponent(match[1]);
        return <VaultNotePill target={target}>{children}</VaultNotePill>;
      }
    }

    // 3. Intercept relative Markdown links to Vault notes (e.g. `[Log](Vault/6. Engineering/Log.md)` or `[Plan](Plan.md)`)
    //    that would otherwise resolve to broken `/chat/*.md` 404 paths in the browser
    if (
      href &&
      !href.startsWith("http://") &&
      !href.startsWith("https://") &&
      !href.startsWith("mailto:") &&
      !href.startsWith("#") &&
      /\.md(?:#[^#]*)?$/i.test(href)
    ) {
      // Strip leading "Vault/", "/Vault/", or "./" prefixes to extract the clean relative vault path
      const cleanPath = href.replace(/^(\/?Vault\/|\.\/)/i, "");
      return <VaultNotePill target={cleanPath}>{children}</VaultNotePill>;
    }

    // 4. Standard external links render with target="_blank" and rel="noopener noreferrer" for isolated tab security
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent-cyan underline decoration-accent-cyan/40 underline-offset-2 hover:decoration-accent-cyan transition-colors"
      >
        {children}
      </a>
    );
  },
  pre: ({ children }) => (
    <pre className="my-3.5 rounded-xl bg-[#05070e] border border-border-subtle p-4 overflow-x-auto text-xs font-mono leading-relaxed text-zinc-200 shadow-inner">
      {children}
    </pre>
  ),
  code: ({ className, children }) => {
    // Inline code vs fenced code block detection (className "language-*" denotes fenced blocks)
    const isBlock = Boolean(className?.includes("language-"));
    if (isBlock) {
      return <code className={`${className} font-mono text-xs`}>{children}</code>;
    }

    // Defense-in-depth: if any #wikilink: escaped pre-processing inside an inline code span,
    // unpack and render it as a styled VaultNotePill rather than leaking raw markdown syntax
    if (typeof children === "string" && children.includes("#wikilink:")) {
      const parts = children.split(/(\[[^\]]+\]\(#wikilink:[^)]+\))/g);
      if (parts.length > 1) {
        return (
          <>
            {parts.map((part, i) => {
              const match = part.match(/^\[(.*?)\]\(#wikilink:(.*?)\)$/);
              if (match) {
                const display = match[1];
                const target = decodeURIComponent(match[2]);
                return (
                  <VaultNotePill key={i} target={target}>
                    {display}
                  </VaultNotePill>
                );
              }
              if (!part) return null;
              return (
                <code key={i} className="inline-block px-1.5 py-0.5 mx-0.5 my-0.5 rounded-md bg-bg-secondary/95 border border-white/15 font-mono text-[0.78rem] text-accent-cyan align-baseline">
                  {part}
                </code>
              );
            })}
          </>
        );
      }
    }

    return (
      <code className="inline-block px-1.5 py-0.5 mx-0.5 my-0.5 rounded-md bg-bg-secondary/95 border border-white/15 font-mono text-[0.78rem] text-accent-cyan align-baseline">
        {children}
      </code>
    );
  },
  table: ({ children }) => (
    <div className="my-4 overflow-x-auto rounded-xl border border-border-subtle shadow-md">
      <table className="w-full text-left border-collapse text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-bg-secondary/90 text-text-secondary border-b border-border-subtle font-semibold">{children}</thead>,
  th: ({ children }) => <th className="px-3.5 py-2.5 font-semibold text-text-primary">{children}</th>,
  td: ({ children }) => <td className="px-3.5 py-2.5 border-t border-border-subtle/50">{children}</td>,
  input: ({ checked, type }) => {
    if (type === "checkbox") {
      return (
        <input
          type="checkbox"
          checked={checked}
          readOnly
          className="mr-2 rounded border-border-subtle bg-bg-secondary accent-cyan-400 align-middle cursor-default"
        />
      );
    }
    return <input type={type} readOnly />;
  },
};

// MarkdownMessageProps: Input parameters for the Markdown renderer
// - content: raw or preprocessed markdown document string
// - onWikiLinkClick: optional callback for in-place Vault note switching
// - className: optional container styling overrides
// - openInNewTab: optional boolean specifying whether note links open in a new browser tab (defaults to true when onWikiLinkClick is omitted)
export interface MarkdownMessageProps {
  content: string;                            // Raw or preprocessed markdown document string
  onWikiLinkClick?: (target: string) => void; // Optional callback for in-place Vault note switching
  className?: string;                         // Optional container styling overrides
  openInNewTab?: boolean;                     // Optional override: whether note links open in a new browser tab
}

// MarkdownMessage: Memoized component that preprocesses Obsidian syntax and renders GFM Markdown.
// Wrapped in `React.memo` so historical message bubbles skip AST parsing when sibling or parent state changes.
const MarkdownMessage = memo(function MarkdownMessage({
  content,
  onWikiLinkClick,
  className = "",
  openInNewTab = true,
}: MarkdownMessageProps) {
  // Memoize regex preprocessing so string splitting and replacements only run when `content` actually mutates
  const formatted = useMemo(() => preprocessObsidianMarkdown(content), [content]);

  // Memoize context configuration so child pills avoid re-rendering unless the navigation handler or tab policy changes
  const wikiLinkConfig = useMemo<WikiLinkConfig>(
    () => ({ onWikiLinkClick, openInNewTab }),
    [onWikiLinkClick, openInNewTab]
  );

  return (
    <WikiLinkContext.Provider value={wikiLinkConfig}>
      <div className={`space-y-3 text-sm leading-relaxed text-text-primary break-words ${className}`}>
        <ReactMarkdown
          remarkPlugins={REMARK_PLUGINS}
          rehypePlugins={REHYPE_PLUGINS}
          components={MARKDOWN_COMPONENTS}
        >
          {formatted}
        </ReactMarkdown>
      </div>
    </WikiLinkContext.Provider>
  );
});

export default MarkdownMessage;
