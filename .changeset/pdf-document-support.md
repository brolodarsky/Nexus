---
type: minor
---
### Added
- Integrated PyMuPDF (`pymupdf`) into the Nexus Engine for layout-aware text extraction, tabular recognition, and high-fidelity page rasterization.
- Implemented `_read_pdf_content()` in `src/nexus/shared_tools/vault_reader.py` with native table detection (`page.find_tables().to_markdown()`), geometric reading block sorting (`sort=True`), scanned document detection, and page/line slicing.
- Extended the `@tool read_file` wrapper in `src/nexus/shared_tools/shared.py` with `start_page` and `end_page` slicing arguments for PDF documents.
- Enabled binary file handling across `move_file`, `delete_file` (`src/nexus/shared_tools/shared.py`), and the Two-Phase Commit HITL queue (`src/nexus/core/hitl_queue.py`), preventing `UnicodeDecodeError` and enabling atomic relocation and rollback of binary assets (PDFs, images).
- Authored 12 automated unit and integration tests in `tests/test_pdf_support.py` validating single-page/multi-page reading, page slicing, line slicing, vault table extraction, synthetic tables, scanned document flagging, tool execution, multi-page upload rasterization, thumbnail capping on >10 page documents, and binary move/delete/rollback lifecycles.

### Changed
- Upgraded `POST /api/agents/upload` in `src/nexus/api/routers/agents.py` to persist the full raw PDF file to `logs/uploads/` and cap visual thumbnail rendering to the first 10 pages, eliminating artificial upload rejections on multi-page manuals and reference documents.
- Updated Next.js chat composer (`gui/src/components/chat/ChatInputBar.tsx`) and API client (`gui/src/lib/api/agents.ts`) to accept PDF document uploads, drag-and-drop, and staging of all rendered page thumbnails into the multimodal vision stream.
- Updated `README.md`, `Build Log - Nexus Agentic Engine.md`, and engineering ADRs in `Vault/6. Engineering/Log.md`.
