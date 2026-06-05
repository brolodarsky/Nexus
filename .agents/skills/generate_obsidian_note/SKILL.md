---
name: generate_obsidian_note
description: How to generate, move, format, or import Obsidian notes into the Vault. Always use this skill whenever saving any content to Vault/ — whether creating a new note, reformatting an existing one, moving a file to a new location, or importing external content. You MUST use this skill before writing or moving any .md file into the Vault. Make sure to list_dir on the target folder first to mimic existing naming patterns and respect physical folder structures.
---

# Generating, Moving, or Importing Obsidian Notes

When asked to generate, move, format, or import a note/thought into the user's Obsidian vault (`Vault/`), you must adhere to the following rules to ensure consistency with their existing knowledge base structure.

> Before placing any note, verify the target folder exists. If it does not, create it based on the index.

## 1. File Location & Verifying Folder Structure
*   **CRITICAL RULE:** Do NOT assume folder names. Folder names must exactly match the H1 or H2 sections as defined in `Table of Contents.md`.
*   **Physical Folder Priority:** If there is a discrepancy between the logical nesting in `Table of Contents.md` (e.g., listed as a bullet point under a section) and the actual physical folder structure on disk, you MUST prioritize the existing physical folder path on disk to avoid creating duplicate/split directories. Flag the discrepancy to the user.
*   If the required folder does not currently match the `Table of Contents.md` structure, you MUST read the index to find the exact current name of the section header to use as the folder name.
*   New notes should be placed in the appropriate subdirectory matching that exact header name.
*   If a link exists in an index file (e.g., `[[Supervised Learning]]`), create the new file in the folder that corresponds to that header.

## 2. File Naming & Taxonomy
*   **"Look Before You Leap" Mandatory Naming Check:** Before proposing or creating a new filename, you MUST use `list_dir` on the target directory to examine the existing files. You MUST mimic the exact naming convention/taxonomy already established in that specific folder (e.g., if files follow `[Job Title] - [Company].md`, do NOT invent a `Listing -` prefix).
*   **Selective Prefixes:** Use taxonomic prefixes *only* when a note is a specific instance of a broader category (e.g., `Project - Blower Motor Noise Fix`, `Protocol - Monthly Backup`, `Log - Maintenance`, `Workshop - Tailoring Resumes`, `Capture - YouTube Interview`, `Article - Andrew Ng on Machine Learning`, etc) AND it aligns with the target folder's existing pattern.
*   **Natural Names:** Broad concepts, standalone entities, or general reference lists should keep their natural names without prefixes (e.g., `Linear Algebra`, `Python`, `Car Info`, `Project Ideas`).
*   *Note:* You are explicitly permitted to invent and use a new prefix if needed, but err on the side of natural names for general concepts and NEVER violate an established folder pattern.
*   The final filename must be what is specified in the index wiki-link.

## 3. Formatting and Structure (Modified Zettelkasten Protocol)
*   **No Redundant H1 Header:** Do NOT use an `#` H1 header that perfectly matches the filename. Obsidian natively displays the filename as the document title, making matching H1s redundant and a waste of vertical space. 
*   **Mandatory Header Link:** directly below the YAML frontmatter block, before any body content, you MUST place a Table of Contents return link that, if applicable, also links to the section of the TOC that the note belongs to. 
*   **Contextual Navigation:** If the note is part of a tight cluster (e.g., specific vehicle notes, health dashboards, or a project hub and its sub-notes), you MUST implement a horizontal navigation bar in the top row, directly after the TOC link.
```markdown
    **Back to:** [[Table of Contents#6.2.8. NLP & Vector Search]|Table of Contents] | [[Hub Note]] | [[Related Note A]] | [[Related Note B]]
```
*   **Atomic Notes:** Keep the note focused on a single logical concept. Use H1 (`#`) and H2 (`##`) and so on headers to logically break down the topic.
*   **Lists:** Use extensive bullet points for readability. The user prefers a highly structured, outline-like format over wall-of-text paragraphs.
*   **Intra-linking:** Proactively interlink concepts within the body text using Obsidian's `[[Wiki-link]]` syntax.
## 4. Frontmatter (YAML)
*   Every single note MUST begin with a YAML frontmatter block at the very top of the file.
*   **`aliases:`** Provide 1-3 synonyms or alternative names (e.g., for `Calculus.md`, an alias might be `Derivatives`). This makes linking much easier.
*   **`tags:`** Provide 2-4 highly relevant, broad category tags (e.g., `#machine-learning`, `#pkm`, `#math`, `#python`, `#health`, `#work`, `#projects`, `#ideas`, `#archive`).
*   **`type:`** Categorize the note as one of the following (or a new idea you have): `concept`, `algorithm`, `tool`, `overview`, or `capture`.
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

## 6. Workflow & Verification
1.  **Analyze Request:** Understand the topic the user wants a note for.
2.  **Determine Location:** Find the best folder for this topic by cross-referencing `Table of Contents.md` and the actual physical disk structure. Prioritize physical disk structure if discrepancies exist.
3.  **Verify Folder Structure:** Confirm the target folder exists. If missing, create it.
4.  **Examine Target Pattern:** Run `list_dir` on the target directory to verify existing naming conventions.
5.  **Create File:** Create the `.md` file with the exact title matching the folder's pattern.
6.  **Draft Content:** Write the content following the formatting rules. Include appending to any "Recent" or "Log" sections inside the parent Hub/MOC note if applicable.
7.  **Update Related Notes & Local Synthesis:** If this note was spawned from an existing "Project", "Protocol", or "Map of Content" note, open that parent note and insert a link to your newly created file. **Localized Synthesis Check:** Whenever saving or importing external content (articles, clippings, news) into a subdirectory, you MUST scan that subdirectory for a **Localized Synthesis, Hub, or Map of Content (MOC)** note. If found, evaluate if the new content provides relevant data/signals to synthesize into it. If beneficial, integrate the insights directly into the synthesis note and append the article reference link.
8.  **Table of Contents Integration:** You MUST link the new note FROM `Table of Contents.md`. Find the exact matching header in the index and add a bullet point for your new file.
9.  **To Do List Registration:** If the new note uses the `Protocol -` or `Project -` prefix, follow the rules in **Section 7** below.
10. **Agent Affirmation:** When summarizing your work to the user at the end of your turn, you MUST explicitly list the file paths of all index/parent notes you modified to establish these inbound links. If you did not establish inbound links, you have failed this task.

## 7. To Do List Registration

When creating a note with the `Protocol -` or `Project -` prefix, you MUST also register it in `Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md`.

### Protocol Registration
1.  **Read** `To Do List.md` and locate the `## Recurring Protocols` section.
2.  **Determine cadence:** Ask the user what cadence the protocol should run on (Weekly, Monthly, or Quarterly), or infer it from the protocol's content if the cadence is obvious.
3.  **Add a checkbox entry** under the correct `### Weekly`, `### Monthly`, or `### Quarterly` heading:
    ```markdown
    - [ ] [[Protocol - Example Name]] — Brief one-line description of what this protocol does.
    ```

### Project Registration
1.  **Read** `To Do List.md` and locate the `## Active Projects` section.
2.  **Add a list entry** with a wiki-link and brief description:
    ```markdown
    - **[[Project - Example Name]]:** Brief one-line description of what this project does.
    ```

### Final Step
*  **Update the date** at the bottom of `To Do List.md` to reflect the current date.

## 8. Canonical Project Note Template

When creating a new `Project - *.md` note, you MUST follow the canonical format. See the `project_work` skill for details. The required sections are: Overview, Current State, Architecture, Standing Guidelines, Build Log, Roadmap, Resources.
