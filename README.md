# Brain 2

This is a personal "second brain"/knowledge management system that stores/uses markdown notes, images, pdfs and other files in a Vault as thoughts & memories.

It's read and tinkered with in Obsidian and tinkered with in agentic IDEs, version-controlled with Git, and synced to mobile via Syncthing. 

Notes follow the Zettelkasten methodology. Vault folder structure is defined in `Table of Contents.md`. Audio files are frequently generated for on the go listening to "thoughts". Several tools are available to help with "brain automation".

---

## Repository Structure

```
Knowledge Base/
├── .agents/                    # AI agent instructions
│   ├── skills/                 # Mandatory behaviors
│   │   ├── conventional_commits/     # Commit message format rules
│   │   ├── generate_obsidian_note/   # How to create new notes
│   │   ├── maintain_project_docs/    # Keep README & requirements.
│   └── workflows/              # Structured procedures (slash commands)
│       ├── add_job_requirement.md
│       ├── audit_inbox.md
│       ├── create_new_note.md
│       ├── create_project.md
│       ├── distill_learning.md
│       └── plan_activity.md
├── .venv/                      # Python virtual environment (not committed)
├── Vault/                      # All Brain content lives here
│   ├── .obsidian/              # Obsidian settings
│   ├── .stfolder/              # Syncthing folder
│   ├── 1. The Core/
│   ├── 2. Health/
│   ├── 3. Operations & Wealth/
│   ├── 4. Playground/
│   ├── 5. Capture & Archive/
│   ├── 6. Forge/
│   ├── Audio/                  # Gitignored
│   ├── Sensitive/              # Gitignored
│   └── Table of Contents.md   # Master index — source of truth for structure
├── AGENTS.md                   # AI agent constitution
├── CHANGELOG.md                # Running log of notable changes
├── tools/                      # Python automation tools
├── requirements.txt            # Pinned Python dependencies
└── .gitignore
```

---

## Setup

First time on a new machine:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> The `.venv/` folder is excluded from Git. `requirements.txt` is the source of truth for dependencies.

---

## Brain Functions & Automation

This repository distinguishes between two types of "cognitive" capabilities:

1. **Agentic Tools (`.agents/workflows/`)**: These are **Active Procedures** (Recipes) for the AI agent to follow. They define complex, multi-step logic (like creating notes or parsing job descriptions) and are triggered via slash commands.
2. **Automation Tools (`tools/`)**: These are **Deterministic Capabilities** (Scripts) written in Python. They perform specific, repetitive tasks (like generating MP3s or maintenance) and are triggered manually via the terminal.

---

## Tools & Workflows

### Agentic Tools
- `/add_job_requirement`: Automates extracting skills from a job description (PDF/URL).
- `/audit_inbox`: Sorts raw notes and bullet points from the Brain Dump & Inbox into the main Zettelkasten structure.
- `/create_project`: Consolidates rough notes or ideas into a structured project note, complete with extracted tasks and materials.
- `/distill_learning`: Synthesizes complex technical articles or PDFs into atomic, interlinked notes.
- `/plan_activity`: Cross-references Activities List, Date Ideas, and People Data notes to generate a structured markdown itinerary.

### Vault Maintenance Tools
- `tools/create_folders.py`: Parses the TOC for numbered headers and creates missing folders.
- `tools/check_folders.py`: Dry-run version of folder creation to print missing paths.
- `tools/add_gitkeeps.py`: Scans the Vault for empty directories and adds `.gitkeep` files.

### `tools/generate_podcast.py`
Converts every Markdown note in the Vault into an MP3 using Microsoft's neural TTS voices via [`edge-tts`](https://github.com/rany2/edge-tts).

- Only regenerates notes that are **new or modified** since the last run.
- Output goes to `Vault/Audio/` — excluded from Git, synced via Syncthing.
- Voice can be changed by editing `VOICE` at the top of the script.

**Usage** (from repo root, with `.venv` active or not):
```bash
python tools/generate_podcast.py
```

**Setup** (first time only):
```bash
.venv\Scripts\Activate.ps1      # Windows PowerShell
pip install edge-tts
```

---

### Vault Maintenance
Any time `Vault/Table of Contents.md` is modified, the directory structure must be affirmed to match.

- Ensure every numbered section has a matching folder in `Vault/`.
- Handle `.gitkeep` files: add to empty folders, remove from populated ones.
- Orphaned folders (no matching H1) should be reported, never deleted automatically.

---

## Obsidian Setup

Point Obsidian at the **`Vault/`** subfolder, not the repo root.

> Settings → About → Vault path → `…/Brain 2/Vault`

---

## Agent Skills, Workflows & Rules

AI agent tools & instructions live in `.agents/`. Each skill is a `SKILL.md` file that instructs the agent how to behave for a specific task:

| Skill | Trigger |
|---|---|
| `generate_obsidian_note` | When asked to create a new note |
| `maintain_project_docs` | After `pip install`/`uninstall`, or after adding/changing tools |
| `conventional_commits` | On every `git commit` |
