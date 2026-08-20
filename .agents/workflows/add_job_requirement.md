---
description: Extracts skills from a job description (URL, PDF, or raw text) and appends them to Employer Skill Requirements.md, regenerates the AI summary, and optionally adds the company to the correct industry vertical in Job Hunt War Room.md Section 4.
---

# Steps

1. Extract Information:
   - Read the provided source. If the source is a URL, use `src/nexus/shared_tools/read_webpage.py` to extract the clean job description.
   - Extract the following fields: Role Name, Company, Core Requirements, Preferred Background, and any compensation/bonus information.

2. Format the Entry:
   - Format the extracted information into a markdown section:
     ```markdown
     ## [[YYYY-MM-DD - Company - Role Name]] <- ADD INTERNAL WIKILINK TO JOB POSTING FILE AS HEADER
     - **Source:** [Link or File Reference]
     - **Date Added:** [Current Date]
     - **Desired Background and Skills:**
         - [Skill 1]
         - [Skill 2]
         ...
     ```

3. Update the Note (`Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Employer Skill Requirements.md`):
   - Append or insert the newly formatted entry into the `# 📋 Roles & Requirements` section.

4. Regenerate the AI Summary:
   - Read the entirety of the `# Roles & Requirements` section.
   - Synthesize common themes, required qualifications, prominent languages/frameworks, and domain knowledge sorted by importance.
   - Replace the contents of the `# AI Summary` section with the newly generated synthesis.

5. Optionally Update Job Hunt War Room — Section 4 (Industry Targets):
   - Read `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Job Hunt War Room.md`.
   - Determine which industry vertical in `## 4. Industry Targets` best fits the company (e.g., "Legal Tech", "FinTech", "AI Infrastructure & Agentic Labs").
   - Check if the company is already listed under that vertical; if so, skip this step.
   - If not listed, ask the user: "[Company] isn't in the [Vertical] list in the War Room. Should I add it?"
   - If confirmed, append the company (with hyperlink to careers page if available) under the correct vertical. Do not create a new vertical unless the company clearly doesn't fit any existing one.
