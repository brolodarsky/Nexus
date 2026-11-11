---
type: patch
---
### Fixed
- Fixed uncatchable native C++ access violation (SEH `0xc0000005` segfault) in PyMuPDF (`mupdfcpp64.dll`) triggered during `page.find_tables()` table extraction. The default layout analyzer (`use_layout=True` -> `page.get_layout()`) dereferenced null pointers on vector-drawn PDFs (such as financial and student loan payment receipts), abruptly killing the Uvicorn worker process and leaving port 8000 orphaned in `CloseWait`.
- Configured `find_tables(use_layout=False)` in `src/nexus/shared_tools/vault_reader.py` (`_read_pdf_content`), restricting detection to memory-safe, deterministic line- and edge-based vector algorithms.
- Updated `tests/test_pdf_support.py` with `test_read_pdf_layout_segfault_resilience` validating receipt PDFs with vector drawings ingest cleanly without process termination.
- Resolved ambiguous path resolution in `tests/test_pdf_support.py` across duplicate vault files.
