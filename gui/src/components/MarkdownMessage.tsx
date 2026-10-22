"use client";

// ReactMarkdown: Renders raw Markdown strings into React DOM elements safely without `dangerouslySetInnerHTML`
import ReactMarkdown from "react-markdown";
// remarkGfm: Remark plugin enabling GitHub-Flavored Markdown (tables, task checkboxes `- [ ]`, strikethrough, autolinks)
import remarkGfm from "remark-gfm";

// Shared renderer used by the /ask chat stream and the /hitl Pre-Commit Preview tab.

// ── Obsidian Wiki-Link Preprocessor & Rich Markdown Renderer ─

// Converts Obsidian `[[Target|Alias]]` or `[[Target]]` syntax outside of fenced code blocks into standard
// Markdown links with a `#wikilink:` href so custom `<a>` components can style them as glowing Vault pills.
export function preprocessObsidianMarkdown(raw: string): string {
  if (!raw) return "";
  // Split on fenced code blocks (```...```) so wiki-links inside raw Markdown drafts stay untouched as literal code
  const segments = raw.split(/(```[\s\S]*?```)/g);
  return segments
    .map((segment, index) => {
      // Odd indices are fenced code blocks captured by the regex group
      if (index % 2 === 1) return segment;
      return segment.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_match, target: string, alias?: string) => {
        const display = (alias || target.split("/").pop() || target).trim();
        const encodedTarget = encodeURIComponent(target.trim());
        return `[${display}](#wikilink:${encodedTarget})`;
      });
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
              return (
                <span
                  title={`Vault Note: ${target}`}
                  className="inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded-md text-xs font-medium bg-accent-cyan/10 border border-accent-cyan/25 text-accent-cyan hover:bg-accent-cyan/20 transition-colors cursor-default"
                >
                  <span className="opacity-70 text-[0.65rem]">📄</span>
                  {children}
                </span>
              );
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
            // Inline code vs fenced code block detection
            const isBlock = Boolean(className?.includes("language-"));
            if (isBlock) {
              return <code className={`${className} font-mono text-xs`}>{children}</code>;
            }
            return (
              <code className="px-1.5 py-0.5 mx-0.5 rounded-md bg-bg-secondary/90 border border-border-subtle font-mono text-[0.78rem] text-accent-cyan">
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
