---
type: minor
---

### Added
- **Tools Suite Page (`gui/src/app/tools/page.tsx`):** Added a dedicated `/tools` page to the Nexus Control Panel featuring an extensible tool tab switcher and hosting the premier Resume & Document Compiler Engine.
- **Sidebar Destination (`gui/src/components/Sidebar.tsx`):** Added a primary navigation link for `🛠️ Tools` to the global sidebar menu.
- **Resume Engine Interactive Studio:** Replaced the terminal CLI workflow with a rich browser workspace including:
  - Portfolio document explorer with category tabs (`Resumes`, `Cover Letters`, `All`), multi-select checkboxes, and search filtering.
  - Page Budget & Metrics scorecard displaying total page count, last page fill %, geometry verdicts (`GOOD FIT`, `TIGHT FIT`, `ROOM`, `UNDERFILL`, `OVERFLOW`), and bullet points headroom / trim estimators.
  - Live in-browser markdown editor with direct saving to Vault.
  - Live inline PDF viewer iframe streamed directly from the engine backend.
  - Execution console log drawer and one-click PDF/DOCX downloads.
- **FastAPI Tools Router (`src/nexus/api/routers/tools.py`):** Added `/api/tools/resume/*` endpoints for portfolio scanning, document metadata inspection, markdown updating, headless Chromium & Word DOCX rendering, and binary asset streaming.
- **Resume Engine Backend Service (`src/nexus/shared_tools/resume_engine/service.py`):** Authoritative backend controller managing file discovery, directory traversal security checks, disk caching (`metrics_cache.json`), and compilation execution.
- **TypeScript API Client (`gui/src/lib/api/tools.ts`):** Client-side bindings and TypeScript data interfaces for all resume engine actions.
- **Automated Test Suite (`tests/test_resume_engine_api.py`):** 8 unit and integration tests covering document discovery, path traversal sandbox enforcement (HTTP 403 / ValueError), document reading, and binary PDF streaming.

### Changed
- **Headless Compiler Streamlining (`src/nexus/shared_tools/resume_engine/render.js`):** Refactored `render.js` into a dedicated headless Chromium PDF and page metrics compiler accepting CLI paths or batch flags (`--all`).
- **Native Python Execution (`src/nexus/shared_tools/resume_engine/service.py`):** Replaced the indirect Node-to-Python subprocess hop for Word DOCX generation with direct Python invocation via `render_docx.render_docx()`.
- **Updated `README.md`:** Added documentation for `src/nexus/api/routers/tools.py` and the Control Panel `/tools` page.

### Removed
- **Vestigial Terminal CLI Code (`src/nexus/shared_tools/resume_engine/render.js`):** Removed legacy interactive terminal prompt (`readline`, `promptFileSelection()`, `createInterface()`) now superseded by the `/tools` web studio.
- **Obsolete Debug Scripts & Unused Packages:** Deleted unused `inspect_docx.js` and removed unneeded `html-to-docx` and `adm-zip` dependencies from `src/nexus/shared_tools/resume_engine/package.json`.
