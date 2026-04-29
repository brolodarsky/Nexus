---
name: archive_project
description: Use this skill whenever the user asks to archive a project, mark a project as done, complete a project, or move a finished project out of an active folder.
---

# Archive Project Protocol

Use this skill to systematically archive completed projects within the Zettelkasten. 

## The Protocol

When instructed to archive or complete a `Project - ...md` file, perform the following steps in order:

### 1. File Move
Move the active `Project - [Name].md` file into the `Archive/` folder of its current Vault section. 
- If the `Archive/` folder doesn't exist yet, create it.
- **Example:** If the project is in `Vault/1. The Core/1.2. Personal Knowledge Management (PKM)/Project - Example.md`, move it to `Vault/1. The Core/1.2. Personal Knowledge Management (PKM)/Archive/Project - Example.md`.

### 2. YAML Update
Update the project note's YAML frontmatter to include the following status tags (or update existing ones):
```yaml
status: completed
archived: true
```

### 3. To Do List Update
Remove the project from the "Active Projects" section of `Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md` and append it to the "Completed" section.
- Prepend the project link with today's date in brackets.
- **Example format:** `- **[YYYY-MM-DD] [[Project - Example Name]]:** Brief description.`

### 4. TOC Update (Project Link)
If the project was explicitly linked in its active section of `Vault/Table of Contents.md`, remove that link.

### 5. TOC Update (Archive Link)
Ensure there is a bullet point linking to the new `Archive/` folder in that specific TOC section. This maintains the cognitive map without cluttering it.
- **Format:** `- [[Vault/[Path to Section]/Archive/|Archive]]`
- Only add this if an Archive link does not already exist for that section.
