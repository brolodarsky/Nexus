---
type: patch
---

### Fixed
- **LLM Markdown Code Fence Sanitization & Inversion Prevention (`gui/src/components/MarkdownMessage.tsx`):** Added `sanitizeMarkdownFences` and `splitFencedCodeBlocks` to deterministically heal malformed LLM markdown outputs. When LLMs generate prompts, templates, or documentation containing nested code snippets using standard triple backticks (` ``` `), CommonMark (§4.5) prematurely terminates the outer block on the inner closing fence, spilling subsequent prompt steps into regular prose and inverting subsequent fences into unintended code blocks. `sanitizeMarkdownFences` tracks fence depth, auto-promotes enclosing outer fences to 4+ backticks (` ```` `) so inner fences are safely treated as literal text, and auto-closes unclosed streaming blocks. `splitFencedCodeBlocks` cleanly preserves arbitrary length fences (3, 4, 5+ backticks/tildes) so Obsidian wiki-links, note pills, and LaTeX math formatting apply only to prose segments without mutating or slicing code blocks.
