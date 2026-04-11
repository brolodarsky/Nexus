---
description: Agentic tool for reading and sorting raw notes and bullet points from the Brain Inbox into the main Zettelkasten structure.
---

# Workflow: Audit Inbox (`/audit_inbox` or `/weekly_review`)

This workflow automates the process of processing, structuring, and filing raw thoughts and clipped documents from the Inbox into the main Vault.

## Steps

1. **Analyze Inbox Content:**
   - Read all files located in `Vault/0. Inbox/` and the `Vault/0. Quick Capture.md` file.
   - For each distinct thought, project idea, or piece of information, determine its core subject.

2. **Categorize and Plan:**
   - Cross-reference the identified subjects with `Vault/Table of Contents.md` to find the most appropriate destination (e.g., a fitness log belongs in `2.1. Fitness`, a new technical concept belongs in `6.2. Library & Learning`, a general idea might become an atomic note).
   - *CRITICAL:* If an item is a task or to-do, recommend it goes to `1.1. Philosophy & Personal North Star/To Do List` or an appropriate project note.

3. **Format Notes (Dry Run):**
   - Prepare to format the extracted content according to the `generate_obsidian_note` rules. This means planning the note titles (using prefixes if applicable), adding required YAML frontmatter (`aliases`, `tags`, `type`), and structuring the content.
   
4. **Present Execution Plan (Interactive):**
   - STOP and present a summary to the user detailing the planned actions in a clean, readable format.
   - Example: "I found 3 distinct items. 1. Move 'Gym Idea' to `2.1. Fitness/Workout Log`. 2. Create new note `Concept - XYZ` in `6.2`. 3. Add to-do to `To Do List`. Does this look correct?"
   - **Do not execute any moves or deletions without explicit user approval.**

5. **Execute and Cleanup:**
   - Wait for user approval.
   - Once approved, create the new notes, append to existing notes, or update logs as planned.
   - Add the necessary `[[wiki-links]]` to the `Table of Contents.md`.
   - Remove the processed content from the original Inbox files. If an entire Inbox file was processed, delete it (unless it is the main `Quick Capture.md` file, which should just be emptied).