---
description: Renders the Master Markdown Resume into a premium, professionally-styled PDF and DOCX.
---

# Workflow: Render Resume (`/render_resume`)

This workflow takes the content from the `Resume - Master.md` file and uses the Resume Engine to generate a high-end PDF and a clean DOCX.

## Steps

1. **Verify Master Resume:**
    - Ensure `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Resume - Master.md` exists and is up-to-date.

2. **Run Rendering Engine:**
   - Run the Node.js rendering script. This script uses Playwright for the PDF and automatically triggers the Python DOCX renderer:
     ```bash
     node tools/resume_engine/render.js
     ```

3. **Confirm Output:**
    - Verify that both the PDF and DOCX outputs have been updated in `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/`.
   - Provide the user with links to the new files.

4. **Optional: Tailoring**
   - If a specific Job Description is provided, the agent should first create a tailored copy of the Master Resume, then render that specific version.
