---
description: Renders the Master Markdown Resume into a premium, professionally-styled PDF.
---

# Workflow: Render Resume (`/render_resume`)

This workflow takes the content from the `Resume - Master.md` file and uses the Resume Engine to generate a high-end PDF.

## Steps

1. **Verify Master Resume:**
    - Ensure `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Resume - Master.md` exists and is up-to-date.

2. **Run Rendering Engine:**
   - Navigate to `tools/resume_engine/`.
   - Run the rendering script:
     ```bash
     node render.js
     ```
   - (Note: The engine uses Playwright to ensure premium CSS rendering).

3. **Confirm Output:**
    - Verify that the PDF output has been updated in `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/`.
   - Provide the user with a link to the new PDF.

4. **Optional: Tailoring**
   - If a specific Job Description is provided, the agent should first create a tailored copy of the Master Resume, then render that specific version.
