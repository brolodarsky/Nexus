# AGENTS.md

> This file tells any AI agent how to work in this repository.

---

## Project Overview

This is a personal "second brain"/knowledge management system that's read/tinkered with in Obsidian and tinkered with in agentic IDEs, version-controlled with Git, and synced to mobile via Syncthing. Notes follow the Zettelkasten methodology. Audio files are frequently generated for on the go listening to "thoughts".

**Vault path:** `Vault/` (not the repo root)

---

## Repository Layout

| Path | Purpose |
|---|---|
| `Vault/` | All Obsidian content — notes, images, audio |
| `Vault/Table of Contents.md` | Master index; source of truth for folder structure |
| `Vault/Audio/` | Generated MP3s (gitignored, synced via Syncthing) |
| `scripts/generate_podcast.py` | Converts notes → MP3 via edge-tts |
| `requirements.txt` | Python dependencies |
| `.venv/` | Virtual environment (gitignored) |
| `.agents/skills/` | AI agent skill definitions |
| `.agents/workflows/` | AI agent workflows |

---

## Skills (Mandatory Behaviours)

These are located in `.agents/skills/` and define rules you **must** follow.

### `generate_obsidian_note`
**Trigger:** When asked to create, move, format, or import a note into the Vault
- Verify folder exists (Affirm Vault Structure first)
- Follow Zettelkasten formatting: YAML frontmatter, atomic structure, wikilinks, mandatory footer
- Add the note's `[[wikilink]]` to `Table of Contents.md`

### `maintain_project_docs`
**Trigger:** After `pip install`/`pip uninstall`, or after adding/changing/removing a script
- Regenerate `requirements.txt` via `.venv\Scripts\pip.exe freeze > requirements.txt`
- Update relevant `## Scripts` section in `README.md`

### `conventional_commits`
**Trigger:** On every `git commit`
- Use conventional commit format: `type(scope): description`
- Valid types: `feat`, `fix`, `docs`, `chore`, `refactor`, `style`, `test`
- Update `CHANGELOG.md` for `feat` and `fix` commits

### `cleanup_orphans`
**Trigger:** When asked to "clean the vault", "find orphans", or perform Zettelkasten maintenance
- Scan the vault for broken wiki-links and empty folders
- Report findings to the user; do not delete or modify files automatically

---

## Workflows

Located in `.agents/workflows/`.

### `create_new_note`
End-to-end workflow for adding a note: affirm structure → create note → update TOC link → confirm with user.

---

## Rules

1. **Never delete user content** without explicit confirmation.
2. **Always use the `.venv`** — resolve Python tools from `.venv/Scripts/`, not system PATH. Never install dependencies globally. Always use `.venv\Scripts\pip.exe` for installations. If a new requirement is added, immediately trigger the `maintain_project_docs` skill.
3. **Commit messages must follow Conventional Commits** — see `conventional_commits` skill.
4. **Update `CHANGELOG.md` for all `feat` and `fix` commits.**
5. **The TOC is the single source of truth** for Vault folder structure.
6. **All notes must have YAML frontmatter** with `aliases`, `tags`, and `type` fields.
7. **Audio files are gitignored** — they sync via Syncthing, not Git.
8. **Batch your commits.** Group related changes into single logical commits. Do not `git push` after every minor file edit or documentation fix. Only `git push` at the very end of a task or session to reduce user interruptions.
9. **Keep AGENTS.md updated.** If you create, modify, or delete a skill or workflow, you must update the `## Skills` or `## Workflows` section in this file to reflect the change.
10. **Add `.gitkeep` to empty folders.** Whenever creating a new empty directory in the Vault, always create an empty `.gitkeep` file inside it so it can be tracked by Git.
