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

// ── Obsidian Wiki-Link Context ───────────────────────────────────────────────

// WikiLinkContext: Supplies an optional in-place selection callback to Vault note pills.
// If provided (e.g. inside /vault), clicking a pill switches the active note in-place.
// If omitted (e.g. in /chat or /hitl), clicking navigates to `/vault?note=${target}`.
export const WikiLinkContext = createContext<((target: string) => void) | undefined>(undefined);

// ── Obsidian Wiki-Link & LaTeX Preprocessor & Rich Markdown Renderer ─

// LATEX_SYMBOLS: Lookup map converting LaTeX math arrow/operator commands into clean Unicode characters
// so LLM-emitted syntax like `$\leftrightarrow$` or `\rightarrow` renders natively without MathJax/KaTeX overhead.
const LATEX_SYMBOLS: Record<string, string> = {
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
  "\\leq": "≤",
  "\\geq": "≥",
  "\\neq": "≠",
  "\\le": "≤",
  "\\ge": "≥",
  "\\ne": "≠",
  "\\approx": "≈",
  "\\equiv": "≡",
  "\\sim": "∼",
  "\\times": "×",
  "\\div": "÷",
  "\\pm": "±",
  "\\cdot": "·",
  "\\bullet": "•",
  "\\infty": "∞",
  "\\notin": "∉",
  "\\in": "∈",
  "\\subseteq": "⊆",
  "\\subset": "⊂",
  "\\cup": "∪",
  "\\cap": "∩",
  "\\forall": "∀",
  "\\exists": "∃",
  "\\emptyset": "∅",
  "\\varnothing": "∅",
  "\\Delta": "Δ",
  "\\nabla": "∇",
  "\\alpha": "α",
  "\\beta": "β",
  "\\gamma": "γ",
  "\\delta": "δ",
  "\\lambda": "λ",
  "\\mu": "μ",
  "\\pi": "π",
  "\\sigma": "σ",
  "\\tau": "τ",
  "\\omega": "ω",
  "\\Omega": "Ω",
};

// BARE_LATEX_PATTERN: Matches unambiguous multi-character LaTeX arrow/operator commands even when the LLM
// omits surrounding `$` delimiters (e.g., `\rightarrow`, `\leftarrow`, `\leftrightarrow`).
const BARE_LATEX_PATTERN =
  /\\(longleftrightarrow|Longleftrightarrow|leftrightarrow|Leftrightarrow|longrightarrow|Longrightarrow|longleftarrow|Longleftarrow|rightarrow|Rightarrow|leftarrow|Leftarrow|updownarrow|uparrow|downarrow|mapsto|implies|iff|leq|geq|neq|approx|equiv|times|infty)\b/g;

// MATH_INNER_LATEX_PATTERN: Matches all known LaTeX commands (sorted longest-first) inside `$...$` or `\(...\)` spans
const MATH_INNER_LATEX_PATTERN = new RegExp(
  Object.keys(LATEX_SYMBOLS)
    .sort((a, b) => b.length - a.length)
    .map((k) => k.replace(/\\/g, "\\\\") + "\\b")
    .join("|"),
  "g"
);

// Replaces LaTeX command tokens inside a math expression string with their Unicode equivalents
function replaceLatexInMath(expr: string): string {
  return expr
    .replace(MATH_INNER_LATEX_PATTERN, (match) => LATEX_SYMBOLS[match] ?? match)
    .trim();
}

// Strips trailing `.md` from note display labels so `[[Plan.md]]`, `` `Plan.md` ``, and `[[Plan]]` render identically
function formatNoteDisplay(rawDisplay: string): string {
  return rawDisplay.trim().replace(/\.md$/i, "");
}

// VaultNotePill: Renders an Obsidian [[Wiki-Link]] or Markdown note title as an unbroken glowing cyan badge.
// Interacts with WikiLinkContext to either perform an in-place note switch or open via Next.js <Link>.
function VaultNotePill({ target, children }: { target: string; children: React.ReactNode }) {
  const onWikiLinkClick = useContext(WikiLinkContext);

  const badge = (
    <span
      title={`Vault Note: ${target}`}
      className="inline-flex items-center gap-1.5 px-2 py-0.5 mx-0.5 my-0.5 rounded-lg text-xs font-medium bg-accent-cyan/10 border border-accent-cyan/25 text-accent-cyan hover:bg-accent-cyan/20 hover:border-accent-cyan/40 hover:shadow-[0_0_12px_rgba(56,189,248,0.18)] transition-all cursor-pointer align-baseline select-none group"
    >
      <span className="opacity-70 group-hover:opacity-100 text-[0.7rem] shrink-0 transition-opacity">📄</span>
      <span className="group-hover:underline underline-offset-2">{children}</span>
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
      href={`/vault?note=${encodeURIComponent(target)}`}
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

// Converts Obsidian `[[Target|Alias]]` / `[[Target]]` syntax, backticked `.md` note titles (`Plan.md`),
// and inline LaTeX arrow/operator syntax (`$\leftrightarrow$`) outside of fenced code blocks into
// clean Markdown links and Unicode characters.
export function preprocessObsidianMarkdown(raw: string): string {
  if (!raw) return "";
  // Split on fenced code blocks (```...```) so raw Markdown drafts inside code fences stay untouched
  const segments = raw.split(/(```[\s\S]*?```)/g);
  return segments
    .map((segment, index) => {
      // Odd indices are fenced code blocks captured by the regex group
      if (index % 2 === 1) return segment;

      // 1. Match backtick-wrapped wikilinks (`[[target|alias]]` or ``[[target]]``) OR bare wikilinks ([[target|alias]] or [[target]])
      let processed = segment.replace(
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

      // 2. Convert backtick-wrapped Markdown note titles (e.g. `1.1. Section Instructions.md`, `Plan.md`, `Tasks.md`)
      //    into #wikilink: links so all note titles share the unified VaultNotePill representation instead of splitting
      //    between inline code boxes and Vault pills. Excludes paths with slashes (`Vault/Tasks.md`), CLI commands,
      //    and wildcard/placeholder patterns (`Project - *.md`, `<Name>.md`).
      processed = processed.replace(
        /`([^`\n*?<>"{}$/\\]+\.md)`/g,
        (match, noteFile: string) => {
          const trimmed = noteFile.trim();
          if (/^(python|uv|git|npm|node|npx|pip|pytest|ruff)\b/i.test(trimmed) || trimmed.startsWith("-")) {
            return match;
          }
          const display = formatNoteDisplay(trimmed);
          const encodedTarget = encodeURIComponent(trimmed);
          return `[${display}](#wikilink:${encodedTarget})`;
        }
      );

      // 3. Unwrap inline LaTeX math spans (`$...$` or `\(...\)`) containing backslash commands into clean Unicode.
      //    Closing `$` is guarded by `(?![a-zA-Z0-9\\])` so currency ranges like `$150k–$200k` never pair across prose.
      processed = processed.replace(
        /(?:^|(?<![a-zA-Z0-9]))\$(?!\s)(?=[^$\n]*\\[a-zA-Z])([^$\n]+?)(?<!\s)\$(?![a-zA-Z0-9\\])/g,
        (_match, inner: string) => replaceLatexInMath(inner)
      );
      processed = processed.replace(
        /\\\(([\s\S]*?)\\\)/g,
        (_match, inner: string) => replaceLatexInMath(inner)
      );

      // 4. Convert any remaining bare unambiguous LaTeX arrow/operator commands (e.g. `\rightarrow`, `\leftrightarrow`)
      processed = processed.replace(
        BARE_LATEX_PATTERN,
        (match) => LATEX_SYMBOLS[match] ?? match
      );

      return processed;
    })
    .join("");
}

// REMARK_PLUGINS: Module-level static plugin array passed to ReactMarkdown.
// Hoisting this outside the component prevents allocating a new array reference (`[remarkGfm]`) on every render,
// preserving ReactMarkdown's internal unified/remark processor cache across re-renders.
const REMARK_PLUGINS = [remarkGfm];

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
    // Render Obsidian `[[Wiki-Links]]` as styled Vault note pills
    if (href?.startsWith("#wikilink:")) {
      const target = decodeURIComponent(href.replace("#wikilink:", ""));
      return <VaultNotePill target={target}>{children}</VaultNotePill>;
    }
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
export interface MarkdownMessageProps {
  content: string;                            // Raw or preprocessed markdown document string
  onWikiLinkClick?: (target: string) => void; // Optional callback for in-place Vault note switching
  className?: string;                         // Optional container styling overrides
}

// MarkdownMessage: Memoized component that preprocesses Obsidian syntax and renders GFM Markdown.
// Wrapped in `React.memo` so historical message bubbles skip AST parsing when sibling or parent state changes.
const MarkdownMessage = memo(function MarkdownMessage({
  content,
  onWikiLinkClick,
  className = "",
}: MarkdownMessageProps) {
  // Memoize regex preprocessing so string splitting and replacements only run when `content` actually mutates
  const formatted = useMemo(() => preprocessObsidianMarkdown(content), [content]);

  return (
    <WikiLinkContext.Provider value={onWikiLinkClick}>
      <div className={`space-y-3 text-sm leading-relaxed text-text-primary break-words ${className}`}>
        <ReactMarkdown
          remarkPlugins={REMARK_PLUGINS}
          components={MARKDOWN_COMPONENTS}
        >
          {formatted}
        </ReactMarkdown>
      </div>
    </WikiLinkContext.Provider>
  );
});

export default MarkdownMessage;
