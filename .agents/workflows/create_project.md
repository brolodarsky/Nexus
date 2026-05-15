---
description: Consolidates project ideas into a structured project note, complete with extracted tasks and materials.
---

# Workflow: Create Project (`/create_project`)

This workflow takes rough notes or project ideas, structures them into an actionable project plan, and extracts a clear task list for execution.

## Steps

1. Ingest Source Material:
   - Read the provided source note or the natural language request describing the project idea (e.g., repairing a car part, building a new app feature).

2. Structure the Project Note:
   - Create a new note in the appropriate `.1. Projects` folder (e.g., `6.1. Projects` or `3.2.1. Home Improvement & Maintenance`). Name it with the `Project - ` prefix (e.g., `Project - Blower Motor Noise Fix`).
   - Add standard YAML frontmatter for a project (`aliases`, `tags`, `type: project`).
   - Draft a structural outline based on the context. If it's a software project, reference the `Project Maturity Checklist`. Otherwise, use standard project headers (Goal, Background, Execution Plan).

3. Extract Actionable Items:
   - Analyze the raw input to identify all implied tasks, prerequisites, and needed materials.
   - Separate these into distinct, actionable bullet points or checkboxes.

4. Compile the Final Note:
   - Append a clear `## Tasks` checklist block directly to the bottom of the new project note.
   - Append a `## Materials Needed` block (if applicable) directly above or below the Tasks section.
   - Include any other useful sections (e.g., `## Reference Links` or `## Budget`) derived from the source text.

5. Link and Finalize:
   - Insert a `[[wiki-link]]` to the new project note in the appropriate section of `Vault/Table of Contents.md` (e.g., under `6.1. Projects`).

6. Register in To Do List:
   - Add the new project to the "Active Projects" section of `Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md`.
   - Request user confirmation that the note looks correct.
   - Delete the original source note if it was a temporary scratchpad item from `5.1. Brain Dump & Inbox`.