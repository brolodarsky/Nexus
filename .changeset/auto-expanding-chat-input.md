---
type: patch
---
### Fixed
- **Auto-Expanding Chat Input Field (`gui/src/app/ask/page.tsx`):** Replaced the single-line fixed `<input>` with an auto-expanding `<textarea>` that starts at a comfortable 56px base height and dynamically grows up to 240px as the user types. Added multiline support (`Shift + Enter` for newlines, `Enter` to submit) and refactored the input card to give the textarea full horizontal width with model selection pills and the send button arranged along a dedicated bottom toolbar.
