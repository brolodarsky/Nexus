"use client";

// ReactMarkdown: Renders raw Markdown strings into React DOM elements safely without `dangerouslySetInnerHTML`
import ReactMarkdown from "react-markdown";
// remarkGfm: Remark plugin enabling GitHub-Flavored Markdown (tables, task checkboxes `- [ ]`, strikethrough, autolinks)
import remarkGfm from "remark-gfm";

// Shared renderer used by the /chat stream and the /hitl Pre-Commit Preview tab.

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

// VaultNotePill: Renders an Obsidian [[Wiki-Link]] or Markdown note title as an unbroken glowing cyan badge
function VaultNotePill({ target, children }: { target: string; children: React.ReactNode }) {
  return (
    <span
      title={`Vault Note: ${target}`}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 my-0.5 rounded-md text-xs font-medium bg-accent-cyan/10 border border-accent-cyan/25 text-accent-cyan hover:bg-accent-cyan/20 transition-colors cursor-default align-baseline"
    >
      <span className="opacity-70 text-[0.65rem] shrink-0">📄</span>
      <span>{children}</span>
    </span>
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

export default function MarkdownMessage({ content }: { content: string }) {
  const formatted = preprocessObsidianMarkdown(content);

  return (
    <div className="space-y-2.5 text-sm leading-relaxed text-text-primary break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-lg font-bold tracking-tight text-text-primary mt-4 mb-2 pb-1.5 border-b border-border-subtle first:mt-0">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-semibold tracking-tight text-accent-cyan mt-4 mb-1.5 pb-1 border-b border-border-subtle/60 first:mt-0">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold text-accent-violet mt-3 mb-1 first:mt-0">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-xs font-semibold uppercase tracking-wider text-text-secondary mt-2.5 mb-1">
              {children}
            </h4>
          ),
          p: ({ children }) => <p className="leading-relaxed last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 my-1.5 marker:text-accent-cyan/70">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 my-1.5 marker:text-accent-cyan/80 font-medium">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed text-text-primary/95 pl-0.5">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
          em: ({ children }) => <em className="italic text-text-secondary">{children}</em>,
          hr: () => <hr className="my-3.5 border-border-subtle" />,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-accent-cyan/70 bg-accent-cyan/5 px-3.5 py-2 my-2.5 rounded-r-xl text-text-secondary space-y-1">
              {children}
            </blockquote>
          ),
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
            <pre className="my-2.5 rounded-xl bg-[#05070e] border border-border-subtle p-3.5 overflow-x-auto text-xs font-mono leading-relaxed text-zinc-200 shadow-inner">
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
            <div className="my-3 overflow-x-auto rounded-xl border border-border-subtle">
              <table className="w-full text-left border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-bg-secondary/80 text-text-secondary border-b border-border-subtle">{children}</thead>,
          th: ({ children }) => <th className="px-3 py-2 font-semibold">{children}</th>,
          td: ({ children }) => <td className="px-3 py-2 border-t border-border-subtle/50">{children}</td>,
          input: ({ checked, type }) => {
            if (type === "checkbox") {
              return (
                <input
                  type="checkbox"
                  checked={checked}
                  readOnly
                  className="mr-2 rounded border-border-subtle bg-bg-secondary accent-cyan-400 align-middle"
                />
              );
            }
            return <input type={type} readOnly />;
          },
        }}
      >
        {formatted}
      </ReactMarkdown>
    </div>
  );
}
