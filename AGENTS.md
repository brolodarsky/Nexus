# AGENTS.md

> This file tells any AI agent how to work in this repository. The Agentic Constitution.

## Project Overview

This is a personal "second brain"/knowledge management system that stores/uses markdown notes, images, pdfs and other files in a Vault as thoughts & memories.

It's read and tinkered with in Obsidian and tinkered with in agentic IDEs, version-controlled with Git, and synced to mobile via Syncthing. 

Notes follow the Zettelkasten methodology. Vault folder structure is defined in `Table of Contents.md`. Audio files are frequently generated for on the go listening to "thoughts". Several scripts are available to help with "brain automation".

**Vault path:** `Vault/` (not the repo root)

## Repository Layout

| Path | Purpose |
|---|---|
| `Vault/` | All Obsidian content/second brain "thoughts" — notes, images, audio, pdfs, external links, etc. |
| `Vault/Table of Contents.md` | Master index; source of truth for folder structure/brain structure |
| `Vault/Audio/` | Generated MP3s (gitignored, synced via Syncthing) |
| `scripts/` | Python scripts for brain automation |
| `requirements.txt` | Python dependencies |
| `.venv/` | Virtual environment (gitignored) |
| `.agents/skills/` | AI agent skill definitions |
| `.agents/workflows/` | AI agent workflows |

## Skills (Mandatory Behaviours)

These are located in `.agents/skills/` and define rules you **must** follow.

### `generate_obsidian_note`
**Trigger:** When asked to create, move, format, or import a note into the Vault

### `maintain_project_docs`
**Trigger:** After `pip install`/`pip uninstall`, after adding/changing/removing scripts, agentic workflows, skills or rules.

### `conventional_commits`
**Trigger:** On every `git commit`

### `cleanup_orphans`
**Trigger:** When asked to "clean the vault", "find orphans", or perform Zettelkasten maintenance

## Workflows

Located in `.agents/workflows/`.

### `create_new_note`
End-to-end workflow for adding a note: affirm structure → create note → update TOC link → confirm with user.

### `add_job_requirement`
Automates extracting skills from a job description (PDF/URL), appending it to `Employer Skill Requirements.md`, and regenerating the high-level AI Summary.

## Rules

1. **Never delete user content** without explicit confirmation.
2. **Always use the `.venv`** — resolve Python tools from `.venv/Scripts/`, not system PATH. Never install dependencies globally. Always use `.venv\Scripts\pip.exe` for installations. If a new requirement is added, immediately trigger the `maintain_project_docs` skill.
3. **Commit messages must follow Conventional Commits** — see `conventional_commits` skill. For Vault changes, always include a TOC section reference.
4. **Update `CHANGELOG.md` for all `feat` and `fix` commits, or when you think appropriate. If there is a significant change, update the version number. If there is a minor change, update the patch number. If there is a documentation change, update the patch number. If there's an existing version on the same day, only create a new version if the change is significant, otherwise update the existing version.**
5. **The TOC is the single source of truth** for Vault folder structure and the concept of this entire project.
6. **All notes must have YAML frontmatter** with `aliases`, `tags`, and `type` fields.
7. **Audio files are gitignored** — they sync via Syncthing, not Git.
8. **Batch your commits.** Group related changes into single logical commits. Do not `git push` after every minor file edit or documentation fix. Only `git push` at the very end of a task/session or if it's a significant change, to reduce user interruptions.
9. **Keep AGENTS.md updated.** If you create, modify, or delete a skill or workflow, you must update the `## Skills` or `## Workflows` section in this file to reflect the change.
10. **Add `.gitkeep` to empty folders.** Whenever creating a new empty directory in the Vault, always create an empty `.gitkeep` file inside it so it can be tracked by Git.