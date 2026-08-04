---
description: End-to-end workflow for creating, moving, formatting, or importing an original note or internal thought into the Knowledge Base. Use this for notes you are writing yourself — not for saving external articles or URLs (use /capture_content) and not for breaking down a source into atomic notes (use /distill_learning).
---
# Steps

1. Identify the topic and which H1 section in `Vault/Table of Contents.md` it belongs to.
If a new H1 section is needed, recommend to user and wait for approval.

2. Determine if the note requires a filename prefix. Use prefixes *only* for specific instances of categories (e.g., `Project - `, `Protocol - `, `Log - `, `Workshop - `, `Plan - `). Broad concepts should keep their natural names. Apply this taxonomy to the proposed filename if applicable.

3. Confirm the target folder exists. Create it if missing.

4. Apply the `generate_obsidian_note` skill to create the note file with correct YAML frontmatter, structure, and intra-links. 
    - **Intertwined Research:** Proactively include external search links directly in the body text for complex terms or topics that benefit from further reading (e.g., `[Search - [Topic]](https://www.google.com/search?q=[topic])`).

5. Add a `[[Wiki-link]]` to the new note from the appropriate section of `Vault/Table of Contents.md`.

6. Confirm with the user that the note content and placement look correct.
