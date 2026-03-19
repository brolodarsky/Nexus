# Brain 2

This is a personal "second brain"/knowledge management system that stores/uses markdown notes, images, pdfs and other files in a Vault as thoughts & memories.

It's read and tinkered with in Obsidian and tinkered with in agentic IDEs, version-controlled with Git, and synced to mobile via Syncthing. 

Notes follow the Zettelkasten methodology. Vault folder structure is defined in `Table of Contents.md`. Audio files are frequently generated for on the go listening to "thoughts". Several scripts are available to help with "brain automation".

---

## Repository Structure

```
Knowledge Base/
├── .agents/                    # AI agent skills & workflows
│   ├── skills/
│   │   ├── conventional_commits/     # Commit message format rules
│   │   ├── generate_obsidian_note/   # How to create new notes
│   │   ├── maintain_project_docs/    # Keep README & requirements.txt in sync
│   └── workflows/
│       ├── add_job_requirement.md    # Job requirement extraction workflow
│       └── create_new_note.md        # End-to-end note creation flow
├── .venv/                      # Python virtual environment (not committed)
├── Vault/                      # All Obsidian content lives here
│   ├── .obsidian/
│   ├── .stfolder/
│   ├── 1. The Core/
│   ├── 2. Health/
│   ├── 3. Forge/
│   ├── 4. Operations & Wealth/
│   ├── 5. Playground/
│   ├── 6. Capture & Archive/
│   ├── Audio/
│   ├── BatchRun_CDrive_to_MainBackup.ffs_batch
│   └── Table of Contents.md   # Master index — source of truth for structure
├── AGENTS.md                   # AI agent constitution for the repo
├── CHANGELOG.md                # Running log of notable changes
├── scripts/                    # Python automation scripts
│   └── generate_podcast.py     # Converts notes to MP3 audiobooks
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

## Scripts

### Vault Maintenance Scripts
- `scripts/create_folders.py`: Parses the TOC for numbered headers and creates missing folders.
- `scripts/check_folders.py`: Dry-run version of folder creation to print missing paths.
- `scripts/add_gitkeeps.py`: Scans the Vault for empty directories and adds `.gitkeep` files.

### `scripts/generate_podcast.py`
Converts every Markdown note in the Vault into an MP3 using Microsoft's neural TTS voices via [`edge-tts`](https://github.com/rany2/edge-tts).

- Only regenerates notes that are **new or modified** since the last run.
- Output goes to `Vault/Audio/` — excluded from Git, synced via Syncthing.
- Voice can be changed by editing `VOICE` at the top of the script.

**Usage** (from repo root, with `.venv` active or not):
```bash
python scripts/generate_podcast.py
```

**Setup** (first time only):
```bash
.venv\Scripts\Activate.ps1      # Windows PowerShell
pip install edge-tts
```

---

### Vault Maintenance
Any time `Vault/Table of Contents.md` is modified, the directory structure must be affirmed to match.

- Ensure every top-level H1 section has a matching folder in `Vault/`.
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
| `maintain_project_docs` | After `pip install`/`uninstall`, or after adding/changing scripts |
| `conventional_commits` | On every `git commit` |
