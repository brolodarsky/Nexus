---
type: patch
---

### Fixed
- **KaTeX Mathematical Typesetting Across GUI (`gui/src/components/MarkdownMessage.tsx`, `gui/src/app/layout.tsx`, `gui/src/app/globals.css`):** Fixed a Markdown rendering flaw where complex LaTeX equations (e.g. `$$\text{Spread} = 0.4 \times \text{edge\_weight} \times (0.5^{\text{hop\_distance}})$$`) rendered as raw broken text with stray `$` delimiters due to an ad-hoc regex symbol preprocessor that lacked math AST parsing. Installed `remark-math`, `rehype-katex`, and `katex`, added `remarkMath` and `rehypeKatex` (configured with `strict: false, throwOnError: false`) to `MarkdownMessage.tsx`, imported `katex/dist/katex.min.css` in `layout.tsx`, and added horizontal scroll overflow styling for `.katex-display` blocks in `globals.css`.
- **Prose Currency Delimiter Protection (`gui/src/components/MarkdownMessage.tsx`):** Added deterministic regex escaping for conversational currency figures (`$41.20`, `$150k`, `$50–$100`) so `remark-math` does not mistakenly pair prose dollar amounts into broken inline math spans, while preserving single-number math literals (e.g. `$0.4$`).
- **LaTeX snake_case Variable Protection (`gui/src/components/MarkdownMessage.tsx`):** Added automatic underscore escaping inside `\text{...}` math tags (e.g. `\text{edge_weight}`) so programmatic variable names parse without triggering KaTeX `Expected 'EOF', got '_'` syntax errors.
- **Zero-Vestige Refactoring (`gui/src/components/MarkdownMessage.tsx`):** Excised legacy symbol substitution code (`MATH_INNER_LATEX_PATTERN`, `replaceLatexInMath`) that previously attempted to unwrap math into flat Unicode characters, preserving `BARE_PROSE_LATEX_PATTERN` exclusively for un-delimited prose arrow shortcuts (`\rightarrow` $\to$ `→`).
