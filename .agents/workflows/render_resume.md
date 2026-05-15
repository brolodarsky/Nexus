---
description: Renders markdown documents (resumes, cover letters) from the Portfolio into professionally-styled PDF and DOCX files.
---

# Workflow: Render Resume (`/render_resume`)

This workflow uses the Resume Engine to render any renderable markdown document from the Career Strategy section into a premium PDF and clean DOCX.

## Steps

1. Run Rendering Engine:
   - Run the Node.js rendering script. It scans `3.1. Career Strategy & Revenue` and `3.1.3. Professional Portfolio & Evidence` for Resume, Cover Letter, and Doc markdown files, presents an interactive menu, and renders the selected document(s) to PDF (via Playwright) and DOCX (via python-docx):
     ```bash
     node tools/resume_engine/render.js
     ```
   - To render a specific file directly (non-interactive):
     ```bash
     node tools/resume_engine/render.js "Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Resume - Master.md"
     ```

2. Confirm Output:
    - Verify that both the PDF and DOCX outputs have been created alongside the source markdown file.
   - A copy is also saved to `~/Downloads` for quick access.
   - Provide the user with links to the new files.

3. Optional: Tailoring
   - If a specific Job Description is provided, the agent should first create a tailored copy of the Master Resume in `3.1.3. Professional Portfolio & Evidence/`, then render that specific version.
