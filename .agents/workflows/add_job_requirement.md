---
description: Extracts skills from a job description (URL, PDF, or raw text) and appends them to Employer Skill Requirements.md, regenerates the AI summary, and optionally adds the company to the correct industry vertical in Job Hunt War Room.md Section 4.
---

# Workflow: Add Job Requirement (`/add_job_requirement`)

This workflow automates the process of extracting job requirements from a source (URL, PDF, or raw text, etc) and adding them to the centralized tracking note. The main goal is to find the most relevant job qualifications across the industry and keep track of important postings.

## Steps

1. **Extract Information:**
   - Read the provided source.
   - Extract the following fields: Role Name, Company, Core Requirements, Preferred Background, and any compensation/bonus information.

2. **Format the Entry:**
   - Format the extracted information into a markdown section:
     ```markdown
     ## [[Role Name] - [Company]] <- ADD INTERNAL WIKILINK TO JOB POSTING FILE AS HEADER
     - **Source:** [Link or File Reference]
     - **Date Added:** [Current Date]
     - **Desired Background and Skills:**
         - [Skill 1]
         - [Skill 2]
         ...
     ```

3. **Update the Note (`Vault/3. Operations & Wealth/3.3. Career Strategy & Revenue/Employer Skill Requirements.md`):**
   - Append or insert the newly formatted entry into the `# 📋 Roles & Requirements` section.

4. **Regenerate the AI Summary:**
   - Read the entirety of the `# 📋 Roles & Requirements` section.
   - Synthesize the common themes, required degrees, prominent languages/frameworks, and domain knowledge. Sort by importance, ALWAYS NOTE MOST IMPORTANT SKILLS!!!
   - Replace the contents of the `# 🤖 AI Summary` section with the newly generated synthesis.

5. **Optionally Update Job Hunt War Room — Section 4 (Industry Targets):**
   - Read `Vault/3. Operations & Wealth/3.3. Career Strategy & Revenue/Job Hunt War Room.md`.
   - Determine which industry vertical in `## 4. Industry Targets (NYC/NJ Area)` best fits the company (e.g. "Legal Tech", "FinTech", "AI Infrastructure & Agentic Labs", etc.).
   - Check if the company is **already listed** under that vertical. If it is, skip this step.
   - If it is **not listed**, ask the user: *"[Company] isn't in the [Vertical] list in the War Room. Should I add it?"*
   - If the user confirms, append the company as a new bullet point (with a hyperlink to the company's careers page if available) under the correct vertical. Do not create a new vertical unless the company clearly doesn't fit any existing one.