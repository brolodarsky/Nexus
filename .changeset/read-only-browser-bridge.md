---
type: minor
---
### Added
- **Read-Only Live Chrome Browser & Tab Group Bridge (`src/nexus/shared_tools/browser_bridge.py`, `src/nexus/shared_tools/browser_extension/`, `src/nexus/api/routers/browser.py`):**
  - Created an unpacked Manifest V3 Chrome Extension (`src/nexus/shared_tools/browser_extension/`) with offscreen service-worker keepalive that connects over loopback (`127.0.0.1`) to expose native Chrome Tab Groups (`chrome.tabGroups.query`), open tab metadata (`chrome.tabs.query`), and strictly read-only live DOM-to-Markdown + JSON-LD (`JobPosting` / `Product` / `Article`) extraction (`chrome.scripting.executeScript`).
  - Mounted `/api/browser` router in FastAPI (`ws://127.0.0.1:8000/api/browser/ws`, `GET /status`, `GET /tabs`, `POST /read`) and added automatic standalone ephemeral WebSocket fallback (`ws://127.0.0.1:8765/api/browser/ws`) in `browser_bridge.py` so CLI and IDE Resident agents work seamlessly even when `start.ps1` is offline.
  - Bound `list_browser_tabs` and `read_browser_tabs` `@tool` wrappers in `src/nexus/shared_tools/shared.py` and `CORE_TOOLS` in `src/nexus/agent/graph.py` with a Context Hygiene Directive for parallel `spawn_subagent` fan-out across multi-tab Chrome Tab Groups.
  - Added unit and integration test suite (`tests/test_browser_bridge.py`).
