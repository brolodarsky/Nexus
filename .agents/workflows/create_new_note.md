---
description: End-to-end workflow for creating, moving, formatting, or importing an Obsidian note in the Knowledge Base
---

# Create, Move, or Import Note

Use this workflow whenever you need to add, move, format, or import a note into the Knowledge Base.

## Steps

1. Identify the topic and which H1 section in `Vault/Table of Contents.md` it belongs to.
If a new H1 section is needed, recommend to user and wait for approval.

2. Confirm the target folder exists. Create it if missing.

3. Apply the `generate_obsidian_note` skill to create the note file with correct YAML frontmatter, structure, and intra-links.

4. Add a `[[Wiki-link]]` to the new note from the appropriate section of `Vault/Table of Contents.md`.

5. Confirm with the user that the note content and placement look correct.