---
description: Render markdown resumes/letters to PDF/DOCX and output page fill metrics.
---

# Steps

1. Run Rendering Engine:
   - Run the Node.js rendering script. It scans `3.1.3. Professional Portfolio & Evidence/Resumes/` and `Cover Letters/` for renderable markdown documents, presents an interactive menu, and renders the selected document(s) to PDF (via Playwright) and DOCX (via python-docx):
     ```bash
     node src/nexus/shared_tools/resume_engine/render.js
     ```
   - To render a specific file directly (non-interactive):
     ```bash
     node src/nexus/shared_tools/resume_engine/render.js "Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/3.1.3. Professional Portfolio & Evidence/Resumes/Resume - Master.md"
     ```

2. Read Page Metrics:
   - After rendering, the engine outputs a `📐 PAGE METRICS` summary with per-document stats:
     - **Pages**: Total page count
     - **Last page fill %**: How full the last page is
     - **Verdict**: `UNDERFILL` (<60%) | `ROOM` (60-80%) | `GOOD FIT` (80-95%) | `TIGHT FIT` (95-100%) | `OVERFLOW` (>100%)
     - **Room remaining**: Approximate bullet points that could be added or need to be trimmed
   - A machine-readable `[METRICS_JSON]` line is also emitted for programmatic consumption.
   - **Agent decision rules:**
     - `UNDERFILL` → Add content (more bullets, expand descriptions, add sections)
     - `ROOM` → Optional expansion if valuable content is available
     - `GOOD FIT` → Leave as-is (target state for 1-page resumes)
     - `TIGHT FIT` → Be careful — one more bullet could push to a new page
     - `OVERFLOW` → Trim content (shorten bullets, remove least impactful items)

3. Confirm Output:
   - Verify that both the PDF and DOCX outputs have been created alongside the source markdown file.
   - A copy is also saved to `~/Downloads` for quick access.
   - Provide the user with links to the new files.

4. Resume Versions:
   - **`Resume - Master.md`**: The tight 1-page version. Must target `GOOD FIT` or `TIGHT FIT` (85-100% fill). Every word must earn its pixel.
   - **`Resume - Master (Extended).md`**: The "wishful thinking" version with full technical depth (7 Nexus bullets, content ingestion, architectural evolution narrative). No page constraint.
   - When tailoring for a specific job, copy from the Master version, not Extended.

5. Optional: Tailoring
   - If a specific Job Description is provided, the agent should first create a tailored copy of the Master Resume in `3.1.3. Professional Portfolio & Evidence/Resumes/`, then render that specific version.
   - After rendering, check page metrics and adjust content to hit `GOOD FIT` or `TIGHT FIT` before delivering.
