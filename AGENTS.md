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

<!-- AUTO-COMPILED BY maintain_project_docs. DO NOT EDIT DESCRIPTIONS MANUALLY -->

### `generate_obsidian_note`
**Trigger:** When asked to create, move, format, or import a note into the Vault

### `maintain_project_docs`
**Trigger:** After `pip install`/`pip uninstall`, after adding/changing/removing tools, skills or rules.

### `conventional_commits`
**Trigger:** On every `git commit`

### `cleanup_orphans`
**Trigger:** When asked to "clean the vault", "find orphans", or perform Zettelkasten maintenance

### `analyze_health`
**Trigger:** When asked to diagnose a problem, act as a doctor, suggest treatments, or analyze a health issue.

### `analyze_psych`
**Trigger:** Whenever the user mentions depression,anxiety, decision fatigue, context switching, or any emotional processing. Provide science-based, non-sycophantic psychological support and cognitive architecture analysis.

### `skill_creator`
**Trigger:** When asked to create a new skill from scratch, edit or optimize an existing skill, run evals to test a skill, benchmark skill performance, or improve a skill's triggering description.

### `workflow_creator`
**Trigger:** When asked to create a new slash-command workflow, edit or improve an existing workflow's steps or description, or review a set of workflows for consistency.

## Tools & Workflows

This brain distinguishes between **Active Procedures** (Workflows) and **Deterministic Capabilities** (Tools).

- **Tools (`tools/`)**: Python scripts for deterministic automation (e.g., MP3 generation, folder sync).
- **Workflows (`.agents/workflows/`)**: Structured instructions/recipes for the AI agent to follow (e.g., `/create_new_note`).

### Tools

Deterministic scripts for vault and engine maintenance.

| Tool | Purpose |
|------|---------|
| `youtube_transcript.py` | Downloads transcripts from YouTube videos to text files. |
| `generate_podcast.py` | Converts markdown notes into MP3 files via edge-tts. |
| `check_folders.py` | Validates that the current Vault structure matches `Table of Contents.md`. |
| `create_folders.py` | Idempotently creates the directory structure defined in the TOC. |
| `add_gitkeeps.py` | Adds `.gitkeep` to all empty folders to ensure tracking (Rule 10). |
| `backup_vault.py` | Creates a timestamped local backup of the `Vault/` directory. |
| `medical_xml_parser.py` | Parses HL7 CDA medical XML files into structured Markdown. |
| `resume_engine/` | Node.js project for rendering the Markdown resume into a premium PDF. |

### Workflows

Agentic protocols for complex knowledge management tasks.

<!-- AUTO-COMPILED BY maintain_project_docs. DO NOT EDIT DESCRIPTIONS MANUALLY -->

### `capture_content`
Format, move, or clean up a raw capture note to serve as an inbox item for future knowledge synthesis.

### `add_job_requirement`
Agentic tool. Automates extracting skills from a job description (PDF/URL), appending it to `Employer Skill Requirements.md`, and regenerating the high-level AI Summary for Career Strategy.

### `audit_inbox`
Agentic tool for reading and sorting raw notes and bullet points from the Brain Dump & Inbox into the main Zettelkasten structure.

### `create_project`
Consolidates rough notes or ideas into a structured project note, complete with extracted tasks and materials appended to the bottom of the plan.

### `distill_learning`
Synthesizes complex technical articles or PDFs into atomic, interlinked notes within the `Library & Learning` section or global Zettelkasten.

### `ingest_medical_record`
Parse and ingest raw medical records (PDF, XML, Images) into the Vault following chronological conventions.

### `plan_activity`
Cross-references `Activities List`, `Date Ideas`, and `People Data` notes to generate a structured markdown itinerary.

### `render_resume`
Renders the Master Markdown Resume into a premium, professionally-styled PDF using the Resume Engine and Playwright.

## Rules

1. **Never delete user content** without explicit confirmation.
2. **Always use the `.venv`** — resolve Python tools from `.venv/Scripts/`, not system PATH. Never install dependencies globally. Always use `.venv\Scripts\pip.exe` for installations. If a new requirement is added, immediately trigger the `maintain_project_docs` skill.
3. **Commit messages must follow Conventional Commits** — see `conventional_commits` skill. 
4. **Git & Changelog Policy.** Use this table to determine whether a change requires a `git commit` and/or a `CHANGELOG.md` entry:

| What changed? | Commit? | Changelog? | Version bump |
|---|---|---|---|
| Tool, skill, or workflow code | ✅ | ✅ | Minor or patch |
| New H1/H2 *section* in TOC / global structural paradigm change | ✅ | ✅ | Minor or patch |
| Project docs (AGENTS.md, README.md) | ✅ | ✅ | Patch |
| `.gitkeep` additions for new empty folders | ✅ | ❌ | — |
| Note wiki-links added to existing TOC sections | ❌ | ❌ | — |
| Individual note creation, edits, or deletions in `Vault/` | ❌ | ❌ | — |

- **Key principles:** Git is solely for the **Engine** (tools, skills, workflows, project docs) and **Vault structure** (new sections — not individual notes). Individual notes/thoughts are encrypted and backed up locally — avoid micro-commits. If there's an existing changelog version on the same day, update the existing version unless the change is significant.
5. **The TOC is the single source of truth** for Vault folder structure and the high-level concept of this entire project. Do not clutter the TOC with individual granular notes (e.g. single medical visits, individual articles, daily logs). Those should be linked and organized inside specialized "Hub" or "Map of Content" (MOC) notes (e.g., `Health Summary`, `Auto Knowledge Base`).
6. **All notes must have YAML frontmatter** with `aliases`, `tags`, and `type` fields.
7. **Audio files are gitignored** — they sync via Syncthing, not Git.
8. **Keep AGENTS.md AND README.md updated.** If you make fundamental changes to the project/brain functionality, update these files to reflect the changes.
9. **Add `.gitkeep` to empty folders.** Whenever creating a new empty directory in the Vault, always create an empty `.gitkeep` file inside it so it can be tracked by Git.
10. **All `Project -` and `Protocol -` notes must be registered in `To Do List.md`.** Ensure new projects are added to the Active Projects section of `Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md`.