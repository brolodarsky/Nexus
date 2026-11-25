---
type: patch
---

Fix KaTeX inline-math `\$` truncation (e.g. `$\ge\$160\text{k}$`) by rewriting inner escaped dollars to `{\char36}` and skipping inline-code spans during math/prose preprocessing, and fix GFM task-list items (`li.task-list-item`) splitting inline text, code badges, and wiki-links into side-by-side flex columns by using `relative` list items with `absolute` gutter checkboxes in `gui/src/components/MarkdownMessage.tsx` (plus `min-w-0` on `PinnedNotesReader.tsx`).
