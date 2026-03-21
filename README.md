# Brain 2

This is a personal "second brain"/knowledge management system that stores/uses markdown notes, images, pdfs and other files in a Vault as thoughts & memories.

It's read and tinkered with in Obsidian and tinkered with in agentic IDEs, version-controlled with Git, and synced to mobile via Syncthing. 

Notes follow the Zettelkasten methodology. Vault folder structure is defined in `Table of Contents.md`. Audio files are frequently generated for on the go listening to "thoughts". Several tools are available to help with "brain automation".

---

## Repository Structure

```
Brain 2/
├── .agents/                    # AI agent instructions
│   ├── skills/                 # Mandatory behaviors
│   │   ├── cleanup_orphans/          # Zettelkasten maintenance (links/folders)
│   │   ├── conventional_commits/     # Commit message format rules
│   │   ├── generate_obsidian_note/   # How to create new notes
│   │   ├── maintain_project_docs/    # Keep README & requirements.
│   └── workflows/              # Structured procedures (slash commands)
│       ├── add_job_requirement.md    # Job criteria extraction
│       ├── audit_inbox.md            # Zettelkasten inbox sorting
│       ├── create_new_note.md        # Obsidian note creation
│       ├── create_project.md         # Project planning/tasks
│       ├── distill_learning.md       # Atomic note synthesis
│       ├── plan_activity.md          # Itinerary generation
│       └── render_resume.md          # PDF resume rendering
├── .venv/                      # Python virtual environment (not committed)
├── Vault/                      # All Brain content lives here
│   ├── .obsidian/              # Obsidian settings
│   ├── .stfolder/              # Syncthing folder
│   ├── 1. The Core/                # Identity, governance, and foundations
│   │   ├── 1.1. Philosophy & Personal North Star/    # Values, principles, and long-term vision
│   │   ├── 1.2. Personal Knowledge Management (PKM)/ # Brain 2.0 meta and maintenance protocols
│   │   ├── 1.3. Security & Digital Sovereignty/      # Encryption, password strategy, and inheritance
│   │   └── 1.4. Emergency & Survival/                # Crisis protocols and emergency contacts
│   ├── 2. Health/                  # Physical and mental well-being
│   │   ├── 2.1. Fitness/                             # Training logs and performance tracking
│   │   ├── 2.2. Medical/                             # Health history, lab work, and sleep hygiene
│   │   ├── 2.3. Psych/                               # Cognitive load and mindfulness rituals
│   │   └── 2.4. Nutrition/                           # Recipe vault and nutrition science
│   ├── 3. Operations & Wealth/     # Financial and logistical systems
│   │   ├── 3.1. Wealth & Asset Management/           # Investment strategy and recurring payments
│   │   ├── 3.2. Infrastructure & Logistics/          # Home lab, family estate, and auto maintenance
│   │   └── 3.3. Career Strategy & Revenue/           # Job hunt, professional profile, and portfolio
│   ├── 4. Playground/              # Social, culture, and creativity
│   │   ├── 4.1. Social Life & Community/             # People data, social club, and adventures
│   │   ├── 4.2. Romance & Partnership/               # Relationship maintenance and date ideas
│   │   ├── 4.3. Culture & Inspiration/               # Media archive, reading list, and education
│   │   └── 4.4. Creativity/                          # Writing, jokes, and creative exploration
│   ├── 5. Capture & Archive/       # Inbox and memory bank
│   │   ├── 5.1. Brain Dump & Inbox/                  # Quick capture and significant milestones
│   │   ├── 5.2. The Content Log (General)/           # Web archive and YouTube history
│   │   └── 5.3. Digital Inventory/                    # Hardware/software audits and backups
│   ├── 6. Forge/                   # Technical projects and learning
│   │   ├── 6.1. Projects/                            # Active development "The Lab"
│   │   │   ├── 6.1.1. Flagship Applications/         # Primary high-importance projects (Feeder, etc.)
│   │   │   ├── 6.1.2. Agentic R&D/                   # Agentic skills, workshops, and tinkering
│   │   │   ├── 6.1.3. Maintenance & Assets/          # Stable portfolios and meta-checklists
│   │   │   └── 6.1.4. Script Attic/                  # Inactive tools and experiments
│   │   └── 6.2. Library & Learning/                  # Technical archive and deep-dives
│   ├── Audio/                  # Gitignored
│   └── Table of Contents.md   # Master index — source of truth for structure
├── AGENTS.md                   # AI agent constitution
├── CHANGELOG.md                # Running log of notable changes
├── tools/                      # Automation tools
│   └── resume_engine/          # Premium PDF rendering system
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
- `/render_resume`: Renders the Master Markdown Resume into a premium, professionally-styled PDF.

### Vault Maintenance Tools
- `tools/create_folders.py`: Parses the TOC for numbered headers and creates missing folders.
- `tools/check_folders.py`: Dry-run version of folder creation to print missing paths.
- `tools/add_gitkeeps.py`: Scans the Vault for empty directories and adds `.gitkeep` files.
- `tools/backup_vault.py`: Creates a timestamped local backup of the Vault and tools to an external destination.
- `tools/resume_engine/`: Premium PDF rendering system using Playwright and CSS.

---

## Security & Encryption

This repository uses **`git-crypt`** to transparently encrypt all personal content before it is pushed to GitHub. 

- **What is encrypted:** Everything inside the `Vault/` directory (except structural `.gitkeep` files).
- **What is visible:** Folder names and file names remain visible on GitHub, but the actual file contents are scrambled.
- **Master Key:** The symmetric key (`brain-key.key`) is required to unlock the repository on a new machine. It is strictly ignored by `.gitignore` and must be backed up securely off-site (e.g., in a password manager).

To unlock the repository on a new machine after cloning:
```bash
git-crypt unlock /path/to/your/brain-key.key
```

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
| `cleanup_orphans` | When asked to "clean the vault" or perform maintenance |
