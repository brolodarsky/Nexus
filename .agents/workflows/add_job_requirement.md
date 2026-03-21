---
description: Agentic tool for working in `Employer Skill Requirements.md` note. Automates the extraction of skills from job descriptions, adds them to the Employer Skill Requirements note, and updates the AI summary.
---

# Workflow: Add Job Requirement (`/add_job_requirement`)

This workflow automates the process of extracting job requirements from a source (URL, PDF, or raw text, etc) and adding them to the centralized tracking note. The main goal is to find the most relevant job qualifications across the industry and keep track of important postings.

## Trigger
When asked to "review this job", "add this job requirement", when explicitly invoking `/add_job_requirement [source]`, or some similar language.

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

3. **Update the Note (`Vault/Operations & Wealth/Career Strategy & Revenue/Employer Skill Requirements.md`):**
   - Append or insert the newly formatted entry into the `# 📋 Roles & Requirements` section.

4. **Regenerate the AI Summary:**
   - Read the entirety of the `# 📋 Roles & Requirements` section.
   - Synthesize the common themes, required degrees, prominent languages/frameworks, and domain knowledge. Sort by importance, ALWAYS NOTE MOST IMPORTANT SKILLS!!!
   - Replace the contents of the `# 🤖 AI Summary` section with the newly generated synthesis.