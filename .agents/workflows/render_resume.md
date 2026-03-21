---
description: Renders the Master Markdown Resume into a premium, professionally-styled PDF.
---

# Workflow: Render Resume (`/render_resume`)

This workflow takes the content from the `Resume - Master.md` file and uses the Resume Engine to generate a high-end PDF.

## Trigger
When asked to "generate my resume", "update the pdf", or explicitly invoking `/render_resume`.

## Steps

1. **Verify Master Resume:**
   - Ensure `Vault/3. Operations & Wealth/3.3. Career Strategy & Revenue/Resume - Master.md` exists and is up-to-date.

2. **Run Rendering Engine:**
   - Navigate to `tools/resume_engine/`.
   - Run the rendering script:
     ```bash
     node render.js
     ```
   - (Note: The engine uses Playwright to ensure premium CSS rendering).

3. **Confirm Output:**
   - Verify that `Vault/3. Operations & Wealth/3.3. Career Strategy & Revenue/Resume - William Volodarsky.pdf` has been updated.
   - Provide the user with a link to the new PDF.

4. **Optional: Tailoring**
   - If a specific Job Description is provided, the agent should first create a tailored copy of the Master Resume, then render that specific version.
