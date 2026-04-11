---
description: Saves raw external content (YouTube videos, articles, Reddit posts, podcast summaries, Twitter threads, web pages) as a lightly-structured inbox note in the Content Log. Use this when you want to capture something for later — not process it now. For deep synthesis into atomic notes, use /distill_learning. For original internal notes, use /create_new_note.
---

# Capture Content

Use this workflow whenever the user wants to save raw content (YouTube transcripts, podcast summaries, long articles, Reddit posts, Twitter threads, etc) OR point you to a previously manually-created raw note that needs to be "solidified" into the vault's capture structure.

## Context
A "Capture" is a raw, lightly-structured note stored in the Content Log. It acts as an inbox for external knowledge before it gets processed and distilled into the Library & Learning section.

## Steps

1. **Information Gathering**: Ensure you have a title, URL (if applicable), and the raw content (summary, transcript, or bullet points). If the user pointed you to an *existing* note, read that note first to gather its contents.
2. **Standardize Name & Location**:
   - The final note must reside in `Vault/5. Capture & Archive/5.2. The Content Log (General)`. If an existing note is elsewhere, move it here.
   - The file name should be renamed/created with the prefix `Capture - `, e.g., `Capture - [Source Title].md`.
3. **Format Frontmatter & Content**:
   - Ensure the YAML frontmatter includes exactly:
     ```yaml
     ---
     aliases: []
     tags: [inbox, capture]
     type: capture
     ---
     ```
     *(Add additional tags like `youtube`, `article`, etc., if contextually relevant).*
   - Add the standard return link below the YAML: `**Back to:** [[Table of Contents]]`
   - Structure the body neatly. Emphasize a clear `## [Source Title]` and a `### Summary / Transcript` section.
   - Append the following footer text at the bottom of the note:
     `*Run [/distill_learning] on this note when ready to synthesize into the Zettelkasten.*`
4. **Final Check**: Ensure the file follows all instructions inherited from `generate_obsidian_note` and confirm with the user that the capture is safely stored in the Content Log.