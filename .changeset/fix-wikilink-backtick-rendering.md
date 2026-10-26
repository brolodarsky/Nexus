---
type: patch
---
### Fixed
- **Obsidian `[[Wiki-Link]]` Backtick Rendering (`MarkdownMessage.tsx`):** Fixed an issue where backtick-wrapped wikilinks emitted by LLMs (e.g. `\`[[Plan]]\``) retained their surrounding backticks during preprocessing, causing `ReactMarkdown` to treat them as inline verbatim code and display raw link syntax (`[Plan](#wikilink:Plan)`) instead of styled cyan Vault note pills. Added backtick unwrapping to `preprocessObsidianMarkdown()` and defense-in-depth unpacking in the inline `code` component.
