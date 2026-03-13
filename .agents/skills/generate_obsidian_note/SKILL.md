---
description: How to generate and format new Obsidian notes
---

# Generating New Obsidian Notes

When asked to generate a new note in the user's Obsidian vault, you must adhere to the following rules to ensure consistency with their existing knowledge base structure.

## 1. File Location & Verifying Folder Structure
*   **CRITICAL RULE:** Do NOT assume folder names. Folder names must exactly match the H1 or H2 sections as defined in `Table of Contents.md`.
*   If the required folder does not currently match the `Table of Contents.md` structure, you MUST read the index to find the exact current name of the section header to use as the folder name.
*   New notes should be placed in the appropriate subdirectory matching that exact header name.
*   If a link exists in an index file (e.g., `[[Supervised Learning]]`), create the new file in the folder that corresponds to that header.

## 2. File Naming
*   Use the exact name specified in the wiki-link.
*   For example, if the link is `[[Overview - Linear Algebra]]`, the file must be named `Overview - Linear Algebra.md`.

## 3. Formatting and Structure (Zettelkasten Protocol)
*   **H1 Header:** Every note must start with an H1 header matching the title of the note.
*   **Atomic Notes:** Keep the note focused on a single logical concept. Use H2 (`##`) and H3 (`###`) headers to logically break down the topic.
*   **Lists:** Use extensive bullet points for readability. The user prefers a highly structured, outline-like format over wall-of-text paragraphs.
*   **Intra-linking:** Proactively interlink concepts within the body text using Obsidian's `[[Wiki-link]]` syntax.
*   **Mandatory Footer:** EVERY note you generate must end with the following exact markdown on the last line to ensure it is always tied back to the master index:
    ---
    **Back to:** [[Table of Contents]]
## 4. Frontmatter (YAML)
*   Every single note MUST begin with a YAML frontmatter block at the very top of the file.
*   **`aliases:`** Provide 1-3 synonyms or alternative names (e.g., for `Calculus.md`, an alias might be `Derivatives`). This makes linking much easier.
*   **`tags:`** Provide 2-4 highly relevant, broad category tags (e.g., `#machine-learning`, `#nlp`, `#math`, `#python`).
*   **`type:`** Categorize the note as one of the following: `concept`, `algorithm`, `tool`, or `overview`.
*   Example:
    ```yaml
    ---
    aliases: [Linear Models, OLS]
    tags: [machine-learning, statistics]
    type: algorithm
    ---
    ```

## 5. Content Style
*   Be concise and factual.
*   Focus on definitions, core concepts, algorithms, and applications.
*   Include relevant external resources or links to specific learning materials (like Khan Academy, Coursera, books) if applicable to the topic.

## 6. Workflow
1.  **Analyze Request:** Understand the topic the user wants a note for.
2.  **Determine Location:** Find the best folder for this topic.
3.  **Create File:** Create the `.md` file with the exact title.
4.  **Draft Content:** Write the content following the formatting rules.
5.  **Review Links:** Ensure the new note is properly linked FROM the relevant index file (e.g., `Table of Contents.md`). If the link doesn't exist there, add it.
