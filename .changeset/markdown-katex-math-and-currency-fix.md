---
type: patch
---
### Fixed
- **KaTeX CSS/DOM Version Alignment, Digit-Prefixed Math Guard & Fenced Code Box Wrapping (`gui/package.json`, `gui/src/components/MarkdownMessage.tsx`, `gui/src/components/chat/ChatMessageItem.tsx`):**
  - Aligned `katex` in `gui/package.json` to `^0.16.47` (matching `rehype-katex@7.0.1`'s `^0.16.0` dependency and eliminating the nested `0.16.47` vs. top-level `0.19.1` mismatch) so `katex/dist/katex.min.css` applies `.rlap > .inner` positioning cleanly and renders `\neq` as `≠` instead of `/=`.
  - Replaced `escapeProseCurrency`'s naive `$<number>` check in `MarkdownMessage.tsx` with `isClosedInlineMathOnSameLine()` and inline-code/display-math span protection (`PROSE_CURRENCY_PROTECTED_SPAN`), preventing digit-prefixed LaTeX expressions like `$2^{\Omega(n)}$`, `$2n + 1$`, and `$100 \text{ ms}$` from being escaped into `\$...` and corrupting downstream math spans while still escaping conversational currency (`$41.20`, `$150k`, `$50–$100`, `$1,200.50`).
  - Enabled `whitespace-pre-wrap break-words` and `max-w-full` on fenced `<pre>` / `<code>` blocks in `MarkdownMessage.tsx` (matching `audit/page.tsx`, `vault/page.tsx`, and `AgentTraceVisualizer.tsx`), fixed untagged fenced blocks (` ``` `) so they no longer inherit inline-code badge styling, added `max-w-full break-words` on inline `<code>` spans, and added `min-w-0 max-w-full` on `MarkdownMessage` and `ChatMessageItem` flex containers so long draft/code blocks wrap inside the card instead of clipping or overflowing off-screen.
