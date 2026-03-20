# AGENTS.md

> This file tells any AI agent how to work in this repository. The Agentic Constitution.

## Project Overview

This is a personal "second brain"/knowledge management system that stores/uses markdown notes, images, pdfs and other files in a Vault as thoughts & memories.

It's read and tinkered with in Obsidian and tinkered with in agentic IDEs, version-controlled with Git, and synced to mobile via Syncthing. 

Notes follow the Zettelkasten methodology. Vault folder structure is defined in `Table of Contents.md`. Audio files are frequently generated for on the go listening to "thoughts". Several tools are available to help with "brain automation".

**Vault path:** `Vault/` (not the repo root)

## Repository Layout

| Path | Purpose |
|---|---|
| `Vault/` | All Obsidian content/second brain "thoughts" — notes, images, audio, pdfs, external links, etc. |
| `Vault/Table of Contents.md` | Master index; source of truth for folder structure/brain structure |
| `Vault/Audio/` | Generated MP3s (gitignored, synced via Syncthing) |
| `tools/` | Python scripts for brain automation |
| `requirements.txt` | Python dependencies |
| `.venv/` | Virtual environment (gitignored) |
| `.agents/skills/` | AI agent skill definitions |
| `.agents/workflows/` | AI agent workflows/tools to invoke |

## Skills (Mandatory Behaviours)

These are located in `.agents/skills/` and define rules you **must** follow.

### `generate_obsidian_note`
**Trigger:** When asked to create, move, format, or import a note into the Vault

### `maintain_project_docs`
**Trigger:** After `pip install`/`pip uninstall`, after adding/changing/removing tools, skills or rules.

### `conventional_commits`
**Trigger:** On every `git commit`

### `cleanup_orphans`
**Trigger:** When asked to "clean the vault", "find orphans", or perform Zettelkasten maintenance

## Tools & Workflows

This brain distinguishes between **Active Procedures** (Workflows) and **Deterministic Capabilities** (Tools).

- **Tools (`tools/`)**: Python scripts for deterministic automation (e.g., MP3 generation, folder sync).
- **Workflows (`.agents/workflows/`)**: Structured instructions/recipes for the AI agent to follow (e.g., `/create_new_note`).

### `create_new_note`
Agentic tool. End-to-end workflow for adding a note: affirm structure → create note → update TOC link → confirm with user.

### `add_job_requirement`
Agentic tool. Automates extracting skills from a job description (PDF/URL), appending it to `Employer Skill Requirements.md`, and regenerating the high-level AI Summary for Career Strategy.

### `audit_inbox`
Agentic tool for reading and sorting raw notes and bullet points from the Brain Dump & Inbox into the main Zettelkasten structure.

### `create_project`
Consolidates rough notes or ideas into a structured project note, complete with extracted tasks and materials appended to the bottom of the plan.

### `distill_learning`
Synthesizes complex technical articles or PDFs into atomic, interlinked notes within the `Library & Learning` section or global Zettelkasten.

### `plan_activity`
Cross-references `Activities List`, `Date Ideas`, and `People Data` notes to generate a structured markdown itinerary.

## Rules

1. **Never delete user content** without explicit confirmation.
2. **Always use the `.venv`** — resolve Python tools from `.venv/Scripts/`, not system PATH. Never install dependencies globally. Always use `.venv\Scripts\pip.exe` for installations. If a new requirement is added, immediately trigger the `maintain_project_docs` skill.
3. **Commit messages must follow Conventional Commits** — see `conventional_commits` skill. **Git is for the Engine-only**: only commit changes to tools, skills, workflows, project docs, and Vault structure (e.g., `Table of Contents.md`, `.gitkeep`). Do **not** commit individual notes, images, or "thoughts" within the `Vault/` directory.
4. **Update `CHANGELOG.md` for all `feat` and `fix` commits, or when you think appropriate. If there is a significant change, update the version number. If there is a minor change, update the patch number. If there is a documentation change, update the patch number. If there's an existing version on the same day, only create a new version if the change is significant, otherwise update the existing version.**
5. **The TOC is the single source of truth** for Vault folder structure and the concept of this entire project.
6. **All notes must have YAML frontmatter** with `aliases`, `tags`, and `type` fields.
7. **Audio files are gitignored** — they sync via Syncthing, not Git.
8. **Batch your commits and pushes.** Group related changes into single logical blocks. Only commit "Engine" changes (tools, skills, structure). Do **not** `git commit` or `git push` after every minor file edit. No micro-commits.
9. **Keep AGENTS.md updated.** If you create, modify, or delete a skill or workflow, you must update the `## Skills` or `## Workflows` section in this file to reflect the change.
10. **Add `.gitkeep` to empty folders.** Whenever creating a new empty directory in the Vault, always create an empty `.gitkeep` file inside it so it can be tracked by Git.