---
name: archive_project
description: Use this skill whenever the user asks to archive a project, mark a project as done, complete a project, or move a finished project out of an active folder.
---

# Mandatory Behavior

When instructed to archive or complete a `Project - [Name].md` file, perform the following steps in order:

## 1. Move Project File
- Move the active `Project - [Name].md` file into a year-based subfolder inside the `Archive/` folder of its current Vault section.
- Match the subfolder to the current year (e.g., `Archive/2026/`).
- Create `Archive/` or `Archive/[Year]/` directories if they do not already exist.
- Example: Move `Vault/1. The Core/1.2. PKM/Project - Example.md` to `Vault/1. The Core/1.2. PKM/Archive/2026/Project - Example.md`.

## 2. Update Frontmatter
- Update the project note's YAML frontmatter with completed status:
  ```yaml
  status: completed
  archived: true
  ```

## 3. Update Master To Do List
- Remove the project from the Active Projects section of `Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md`.
- Append the project to the Completed section with today's date:
  `- **[YYYY-MM-DD] [[Project - Example Name]]:** Brief summary of completion.`

## 4. Update Table of Contents
- Remove the active project wiki-link from its section in `Vault/Table of Contents.md`.
- Ensure an Archive folder entry exists for that section:
  `- **📁 [Archive](obsidian://search?vault=Vault&query=path%3A"[Section Folder Name]/Archive")**`
- Do not add duplicate Archive links if one already exists for that section.
