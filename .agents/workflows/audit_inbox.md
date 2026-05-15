---
description: Agentic tool for reading and sorting raw notes and bullet points from the Brain Inbox and Quick Capture into the main Zettelkasten structure. Identifies downstream workflows (e.g., /add_job_requirement, /ingest_medical_record, /distill_learning) and chains their execution. Use during weekly review or when processing captured thoughts.
---

# Workflow: Audit Inbox (`/audit_inbox` or `/weekly_review`)

This workflow automates the process of processing, structuring, and filing raw thoughts and documents from the Inbox into the main Vault.

## Steps

1. Analyze Inbox Content:
   - Read all files located in `Vault/0. Inbox/` and the `Vault/0. Quick Capture.md` file.
   - For each distinct thought, project idea, or piece of information, determine its core subject.

2. Categorize and Plan:
   - Cross-reference the identified subjects with `Vault/Table of Contents.md` to find the most appropriate destination (e.g., a fitness log belongs in `2.1. Fitness`, a new technical concept belongs in `6.2. Library & Learning`, a general idea might become an atomic note).
   - Prefer filing granular notes into the most relevant existing hub, MOC, project note, log, or folder instead of adding each item directly to `Vault/Table of Contents.md`.
   - CRITICAL: If an item is a task or to-do, recommend it goes to `1.1. Philosophy & Personal North Star/To Do List` or an appropriate project note.
   - Localized Synthesis Integration Check: When filing articles, research, or industry news into a target folder, scan that folder to verify if it contains a Localized Synthesis, Hub, or Map of Content (MOC) note. If present, plan to review that synthesis note and directly integrate relevant findings, statistics, or counter-narratives into its body while appending the source citation link.
   - Workflow Chaining: Identify if any specialized downstream workflows apply to the item (e.g., `/add_job_requirement` for job descriptions, `/ingest_medical_record` for medical/health files, `/distill_learning` for dense source material) and integrate their execution into the plan.

3. Format Notes (Dry Run):
   - Prepare to format the extracted content according to the `generate_obsidian_note` rules. Always inspect existing target directory patterns using `list_dir` to ensure perfect naming consistency. Plan note titles, frontmatter (`aliases`, `tags`, `type`), and any appends to parent hub logs.
   
4. Present Execution Plan (Interactive):
   - STOP and present a summary to the user detailing the planned actions in a clean, readable format, including any proposed chained workflows.
   - Example: "I found 3 distinct items. 1. Move 'Gym Idea' to `2.1. Fitness/Workout Log`. 2. Create new note `Concept - XYZ` in `6.2`. 3. Chain `/add_job_requirement` for Job Listing. Does this look correct?"
   - Do not execute any moves, deletions, or chained workflows without explicit user approval.

5. Execute and Cleanup:
   - Wait for user approval.
   - Once approved, create the new notes, append to existing notes, or update logs as planned.
   - Add `[[wiki-links]]` to `Vault/Table of Contents.md` only when creating a durable hub, MOC, `Project -`, `Protocol -`, or other structural note that belongs in the high-level map. Do not add routine granular notes, individual captures, job listings, articles, logs, or visit records directly to the TOC.
   - Remove the processed content from the original Inbox files. If an entire Inbox file was processed, delete it (unless it is the main `Quick Capture.md` file, which should just be emptied).