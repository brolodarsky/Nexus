---
name: project_work
description: Keep active project documents inside the Vault up to date whenever changes are planned, implemented, completed, or conceptually modified. Make sure to use this skill whenever you complete a task related to a project, plan modifications, create a new project, or add/remove tasks conceptually from any Project - *.md file, even if the user does not explicitly request it.
---

# Mandatory Behavior

Apply this protocol whenever any project-related change occurs during execution. This includes completing tasks, modifying plans, adding or removing features, or altering the conceptual direction of any project.

## 1. Locate the Project Note

Identify the relevant project note inside the Vault. Project notes always have the prefix Project - and end with .md.
- Search for the project note using vault search or file list tools.
- If no matching project note exists, check if this is a sub-task of an existing active project, or create a new project note if appropriate.

## 2. Update Tasks and Checklist Items

Project notes (`Project - *.md`) follow a canonical section ordering: Overview, Current State, Architecture, Standing Guidelines, Build Log, Roadmap, Resources. 

When tasks are completed, started, or modified:
- Locate the relevant task within the `Roadmap` section of the project note.
- Update uncompleted tasks (e.g., `- [ ]`) to in-progress (e.g., `- [/]`) when working on them.
- **CRITICAL**: When a task in the `Roadmap` is completed, do NOT just mark it as `- [x]`. Instead, **MOVE** the item to the `Build Log` section as a bullet point under a date heading (e.g., `### YYYY-MM-DD — Brief Description`). The Roadmap should only contain uncompleted items.
- **CRITICAL**: Items in the `Standing Guidelines` section are permanent architectural rules. They are ongoing obligations and are NEVER checked off.

## 3. Update Project Planning and Scope

When conceptual items are added, removed, or changed:
- Update the relevant sections of the project note (such as Overview, Architecture, Roadmap, or Resources).
- **CRITICAL**: You MUST update the `Current State` section whenever you modify a project's codebase, capabilities, or file tree. It should be a living snapshot.
- Document any shifts in implementation strategy, target dates, or architectural decisions.
- Add new tasks to the `Roadmap` as they are discovered or planned. Remove or mark obsolete tasks if they are no longer relevant.

## 4. Keep Global Tracking Documents in Sync

Ensure other files that reference this project are also kept up to date:
- If a new project note is created, register it under the Active Projects section of Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md.
- If a project is completed, archived, or no longer needed, run the archive_project protocol to update To Do List.md, Table of Contents.md, and move the project file to its section-specific archive directory.
- Update any MOCs (Map of Content) or higher-level project notes that link to or track the current project.
