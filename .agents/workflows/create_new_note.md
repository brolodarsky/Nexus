---
description: End-to-end workflow for creating, moving, formatting, or importing an original note or internal thought into the Knowledge Base. Use this for notes you are writing yourself — not for saving external articles or URLs (use /capture_content) and not for breaking down a source into atomic notes (use /distill_learning).
---

# Steps

1. Identify Subject and Destination:
   - Identify the topic and corresponding section in `Vault/Table of Contents.md`.
   - If a new section is needed, propose it to the user before creating.

2. Determine Note Naming:
   - Apply prefixes only for specific instances of categories (`Project - `, `Protocol - `, `Log - `, `Workshop - `, `Plan - `).
   - Broad concepts and atomic thoughts keep their natural conceptual names without prefixes.

3. Verify Target Directory:
   - Run `list_dir` on target folder to confirm existence and inspect existing naming patterns. Create folder if missing.

4. Generate and Format Note:
   - Apply the `generate_obsidian_note` skill to create the note with valid YAML frontmatter, return link, and internal wiki-links.
   - Include external search links for complex external terminology if beneficial (e.g., `[Search - [Topic]](https://www.google.com/search?q=[topic])`).

5. Update Table of Contents:
   - Add a `[[wiki-link]]` to the new note from the appropriate section of `Vault/Table of Contents.md` if it represents a durable hub, project, protocol, or structural note.

6. Confirm with User:
   - Provide the user with the link to the created note and verify placement.
