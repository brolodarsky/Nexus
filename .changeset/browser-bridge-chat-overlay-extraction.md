---
type: minor
---

### Added
- **Active Floating Chat Overlay & Active Modal Extraction (`src/nexus/shared_tools/browser_extension/background.js`):**
  - Added dedicated, non-blocking active overlay extraction pass to the read-only browser bridge content extractor (`extractTabMarkdownReadOnly`), running after primary document extraction.
  - Detects expanded chat bubbles and floating dialogs (e.g. LinkedIn InMail/messaging chats via `aside.msg-overlay-container .msg-overlay-conversation-bubble--is-expanded`, `[role="dialog"]`, and active chat widgets) that were previously skipped as boilerplate outside the `<main>` container.
  - Extracts conversation participant names (automatically stripping ephemeral status indicators such as "Active now" or connection degree badges).
  - Extracts chronological message threads, resolving senders (with viewer/`--me` attribution), timestamps (relative/absolute), InMail subject lines, and message body text with inline links preserved.
  - Formats dialogue cleanly as blockquotes appended to the bottom of the page's standard Markdown body under `## Active Chat & Floating Overlays`.
  - Enforces non-blocking progressive enhancement: safely ignores minimized/collapsed bubbles and cookie consent banners (`/cookie|consent|gdpr|onetrust/i`), returning standard page markdown without error or extra headers when no overlays are active.
- **Automated Regression Test Suite (`tests/test_browser_bridge.py`, `tests/test_browser_extension_dom.js`):**
  - Added unit test coverage in `tests/test_browser_bridge.py` verifying formatted Markdown rendering of tabs with active chat overlays.
  - Built a Node.js DOM simulation test (`tests/test_browser_extension_dom.js`) evaluating `extractTabMarkdownReadOnly` against simulated DOM structures for expanded chat bubbles, minimized bubbles, cookie modals, and clean pages.

### Changed
- **Main Walk Boilerplate Isolation (`src/nexus/shared_tools/browser_extension/background.js`):**
  - Updated `isElementHidden(el, skipBoilerplate)` to skip floating chat containers (`.msg-overlay-container`, `.chat-window`, `.chat-overlay`) and active dialogs (`[role="dialog"]`, `[role="alertdialog"]`, `<dialog>`) during the primary document body walk when `skipBoilerplate=true`, preventing unformatted drawer buttons and modal noise from polluting the primary document prose.
