---
type: minor
---
### Added
- Created `src/nexus/shared_tools/` as the new home for all deterministic Python integration scripts (e.g. `read_email.py`, `generate_podcast.py`, `ingest_phone.py`).

### Changed
- Moved all engine runtime tools from the root `tools/` directory into `src/nexus/shared_tools/`.
- Deleted the root `tools/` directory to enforce a strict boundary between repository maintenance scripts (`scripts/`) and engine components (`src/nexus/`).
- Updated `AGENTS.md` and `README.md` to reflect the new architecture.
- Updated slash command workflows (`/add_job_requirement`, `/capture_content`, `/distill_learning`, `/ingest_medical_record`, `/render_resume`) to point to the new `src/nexus/shared_tools/` paths.
