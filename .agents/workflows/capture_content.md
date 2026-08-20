---
description: Saves raw external content (YouTube videos, articles, Reddit posts, podcast summaries, Twitter threads, web pages) as a lightly-structured inbox note in the Content Log. Use this when you want to capture something for later — not process it now. For deep synthesis into atomic notes, use /distill_learning. For original internal notes, use /create_new_note.
---

# Steps

1. Gather Source Information:
   - Identify source title, author/platform, URL, and raw text (summary, transcript, or bullet points).
   - If a URL is provided, use `.venv/Scripts/python.exe src/nexus/shared_tools/read_webpage.py "<url>"` to extract clean text.
   - If referencing an existing note, read it with `view_file` to collect contents.

2. Standardize Location and Filename:
   - Target directory: `Vault/0. Inbox/`.
   - Filename format: `Capture - [Source Title].md`.

3. Format Note Structure:
   - Apply the `generate_obsidian_note` skill to format the markdown document.
   - YAML frontmatter:
     ```yaml
     ---
     aliases: []
     tags: [inbox, capture]
     type: capture
     ---
     ```
   - Return link directly below frontmatter: `Back to: [[Table of Contents]]`
   - Body sections:
     - `## [Source Title]`
     - `### Metadata` (Source URL, Author, Date captured)
     - `### Summary / Transcript`
   - Append call-to-action footer:
     `*Run [/distill_learning] on this note when ready to synthesize into the Zettelkasten.*`

4. Confirm and Verify:
   - Confirm with user that the captured note is created and ready for future distillation.
