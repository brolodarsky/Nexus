---
description: Breaks down a dense external source (article, paper, PDF, URL) into atomic, interlinked notes. Prioritizes augmenting existing notes over creating duplicates to ensure knowledge synthesis. For lightweight saving, use /capture_content instead.
---

# Steps

1. Read & Absorb:
   - Read the provided source material (using `tools/read_webpage.py` for URLs to ensure clean text extraction, `view_file` for local docs, etc).

2. Extract Core Concepts:
   - Identify the most critical, distinct concepts, algorithms, or theories presented in the material.

3. Check for Existing Knowledge (Augmentation Check):
   - For each extracted concept, search the Vault using the `/ask_brain` workflow to determine if a note already exists that covers this topic.
   - Crucial: If a relevant note exists, prioritize augmenting the existing note with the new information instead of creating a new note. This ensures knowledge synthesis and prevents fragmentation.

4. Draft or Augment Notes:
   - For each concept identified in Step 2:
     - If no existing note was found: Draft a new atomic note following the `generate_obsidian_note` skill.
     - If an existing note was found: Draft the specific additions or refinements to be made to that existing note.

5. Map to Knowledge Base:
   - Analyze `Vault/Table of Contents.md` (specifically focusing on sections like `6.2. Library & Learning` or `3.1. Wealth & Asset Management`).
   - Determine exactly where each new atomic note belongs structurally.
   
6. Establish Connections (Intra-linking):
   - Ensure the new or updated notes link back to the source material (URL, PDF, Markdown, etc).
   - Ensure they link to each other if part of the same source.
   - Crucially, search the Vault for related existing concepts and add `[[wiki-links]]` tying the new knowledge into the existing web.

7. Review and Execute:
   - Present a concise summary to the user: "I will create `Concept A.md` in `6.2.1` and augment `Existing Concept B.md`. Is this correct?"
   - Await execution approval. Upon approval, apply the `generate_obsidian_note` skill to create/modify the physical files and update the `Table of Contents.md` if new notes were created.