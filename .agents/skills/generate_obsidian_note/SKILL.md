---
description: How to generate, move, format, or import Obsidian notes
---

# Generating, Moving, or Importing Obsidian Notes

When asked to generate, move, format, or import a note/thought into the user's Obsidian vault (`Vault/`), you must adhere to the following rules to ensure consistency with their existing knowledge base structure.

> Before placing any note, verify the target folder exists. If it does not, create it based on the index.

## 1. File Location & Verifying Folder Structure
*   **CRITICAL RULE:** Do NOT assume folder names. Folder names must exactly match the H1 or H2 sections as defined in `Table of Contents.md`.
*   If the required folder does not currently match the `Table of Contents.md` structure, you MUST read the index to find the exact current name of the section header to use as the folder name.
*   New notes should be placed in the appropriate subdirectory matching that exact header name.
*   If a link exists in an index file (e.g., `[[Supervised Learning]]`), create the new file in the folder that corresponds to that header.

## 2. File Naming & Taxonomy
*   **Selective Prefixes:** Use taxonomic prefixes *only* when a note is a specific instance of a broader category (e.g., `Project - Blower Motor Noise Fix`, `Protocol - Monthly Backup`, `Log - Maintenance`, `Workshop - Tailoring Resumes`).
*   **Natural Names:** Broad concepts, standalone entities, or general reference lists should keep their natural names without prefixes (e.g., `Linear Algebra`, `Python`, `Car Info`, `Project Ideas`).
*   *Note:* You are explicitly permitted to invent and use a new prefix if needed, but err on the side of natural names for general concepts.
*   The final filename must be what is specified in the index wiki-link.

## 3. Formatting and Structure (Modified Zettelkasten Protocol)
*   **No Redundant H1 Header:** Do NOT use an `#` H1 header that perfectly matches the filename. Obsidian natively displays the filename as the document title, making matching H1s redundant and a waste of vertical space. 
*   **Mandatory Header Link:** directly below the YAML frontmatter block, you MUST place the Table of Contents return link, followed by a blank line and a horizontal rule, before any body content:
```markdown
    **Back to:** [[Table of Contents]]

    ---
```
*   **Atomic Notes:** Keep the note focused on a single logical concept. Use H1 (`#`) and H2 (`##`) and so on headers to logically break down the topic.
*   **Lists:** Use extensive bullet points for readability. The user prefers a highly structured, outline-like format over wall-of-text paragraphs.
*   **Intra-linking:** Proactively interlink concepts within the body text using Obsidian's `[[Wiki-link]]` syntax.
## 4. Frontmatter (YAML)
*   Every single note MUST begin with a YAML frontmatter block at the very top of the file.
*   **`aliases:`** Provide 1-3 synonyms or alternative names (e.g., for `Calculus.md`, an alias might be `Derivatives`). This makes linking much easier.
*   **`tags:`** Provide 2-4 highly relevant, broad category tags (e.g., `#machine-learning`, `#pkm`, `#math`, `#python`, `#health`, `#work`, `#projects`, `#ideas`, `#archive`).
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
*   Be concise and factual. Use web search when needed to gather information.
*   Focus on definitions, core concepts, algorithms, and applications.
*   Include relevant external resources or links to specific learning materials (like Khan Academy, Coursera, books) if applicable to the topic.

## 6. Workflow
1.  **Analyze Request:** Understand the topic the user wants a note for.
2.  **Verify Folder Structure:** Confirm the target folder exists. If missing, create it.
3.  **Determine Location:** Find the best folder for this topic.
4.  **Create File:** Create the `.md` file with the exact title.
5.  **Draft Content:** Write the content following the formatting rules.
6.  **Review Links:** Ensure the new note is properly linked FROM the relevant index file (e.g., `Table of Contents.md`). If the link doesn't exist there, add it.
