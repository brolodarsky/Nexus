---
type: minor
---
### Added
- **Chrome Tab Group Orchestration (`open_browser_tabs`):** Added `open_tabs` (`browser_bridge.py`), `POST /api/browser/open` (`routers/browser.py`), `handleOpenTabs` (`browser_extension/background.js`), CLI `--open`/`--color`/`--activate` flags, and `@tool open_browser_tabs` (`shared.py`, bound in `CORE_TOOLS`) to open 1–10 `http(s)` URLs directly into new Chrome tabs or Chrome Tab Groups.
- **Interactive Form Refs & Assisted-Draft Filling (`fill_browser_form`):** Added `include_refs=True` transient `data-nexus-ref` stamping to `read_browser_tabs`, plus `fill_form` (`browser_bridge.py`), `POST /api/browser/fill` (`routers/browser.py`), self-contained `fillFormFieldsInFrame` (`background.js` `v1.2.0`), CLI `--refs`/`--fill`/`--fields-json`, and `@tool fill_browser_form` (`shared.py`, bound in `CORE_TOOLS`) with blue review highlights and hard-blocks on passwords, files, disabled/readonly inputs, payment/SSN fields, and form submission.
### Security
- **Loopback-Only Browser Bridge Guard:** Added strict TCP peer-IP validation (`require_loopback_client` and WebSocket `1008` close on non-loopback peers) across `/api/browser/*` so LAN/Tailscale peers cannot drive local Chrome while `start.ps1` binds `0.0.0.0:8000`.
