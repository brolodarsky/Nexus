# Brain 2

This is a personal "second brain"/knowledge management system that stores/uses markdown notes, images, pdfs and other files in a Vault as thoughts, memories, plans, learning materials, and much more.

It's read and tinkered with in Obsidian, tinkered with in agentic IDEs, version-controlled with Git, and synced to mobile via Syncthing.

Notes follow the Zettelkasten methodology. Vault folder structure is defined in `Table of Contents.md`. Several "brain engine" tools are available to help with automation.

---

## Repository Structure

```
Brain 2/
├── .agents/                    # AI agent instructions
│   ├── skills/                 # Mandatory behaviors
│   │   ├── analyze_health/           # Health diagnostics & context check
│   │   ├── analyze_psych/            # Psych support & cognitive architecture
│   │   ├── cleanup_orphans/          # Zettelkasten maintenance (links/folders)
│   │   ├── conventional_commits/     # Commit message format rules
│   │   ├── generate_obsidian_note/   # How to create new notes
│   │   ├── maintain_project_docs/    # Keep README & requirements.
│   │   ├── skill_creator/            # Create & improve agent skills
│   │   └── workflow_creator/         # Create & improve agent workflows
│   └── workflows/              # Structured procedures (slash commands)
│       ├── add_job_requirement.md    # Job criteria extraction
│       ├── audit_inbox.md            # Zettelkasten inbox sorting
│       ├── create_new_note.md        # Obsidian note creation
│       ├── create_project.md         # Project planning/tasks
│       ├── distill_learning.md       # Atomic note synthesis
│       ├── ingest_medical_record.md  # Parse raw medical data
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
│   │   │   ├── Health_Logs/                          # Doctor visit notes (PCP, ENT, Pulmonology, etc.)
│   │   │   └── Lab_Work/                             # Bloodwork results (BMP, CBC, Thyroid, etc.)
│   │   ├── 2.3. Psych/                               # Cognitive load and mindfulness rituals
│   │   ├── 2.4. Nutrition/                           # Recipe vault and nutrition science
│   │   └── 2.5. Mom's Health Tracking/               # Caregiving logs, symptoms, and medical records for Mom
│   ├── 3. Operations & Wealth/     # Financial and logistical systems
│   │   ├── 3.1. Wealth & Asset Management/           # Investment strategy and recurring payments
│   │   ├── 3.2. Infrastructure & Logistics/          # Home lab, family estate, and auto maintenance
│   │   │   ├── 3.2.1. Home Improvement & Maintenance/
│   │   │   ├── 3.2.2. Family & Care/
│   │   │   └── 3.2.3. Auto/
│   │   └── 3.3. Career Strategy & Revenue/           # Job hunt, professional profile, and portfolio
│   │       ├── 3.3.1. Market Research & Future of Work/
│   │       ├── 3.3.2. Interview Prep & Technical Depth/
│   │       ├── 3.3.3. Professional Portfolio & Evidence/
│   │       ├── 3.3.4. Networking & Professional CRM/
│   │       ├── 3.3.5. Income Streams & Side Revenue/
│   │       └── 3.3.6. Compensation & Negotiation/
│   ├── 4. Playground/              # Social, culture, and creativity
│   │   ├── 4.1. Social Life & Community/             # People data, social club, and adventures
│   │   ├── 4.2. Romance & Partnership/               # Relationship maintenance and date ideas
│   │   ├── 4.3. Culture & Inspiration/               # Media archive, reading list, and education
│   │   └── 4.4. Creativity/                          # Writing, jokes, and creative exploration
│   ├── 5. Capture & Archive/       # Inbox and memory bank
│   │   ├── 5.1. Brain Dump & Inbox/                  # Quick capture and significant milestones
│   │   ├── 5.2. The Content Log (General)/           # Web archive and YouTube history
│   │   └── 5.3. Digital Inventory/                   # Hardware/software audits and backups
│   ├── 6. Forge/                   # Technical projects and learning
│   │   ├── 6.1. Projects/                            # Active development "The Lab"
│   │   │   ├── 6.1.1. Flagship Applications/         # Primary high-importance projects
│   │   │   ├── 6.1.2. Agentic R&D/                   # Agentic skills (mirrored), workshops, and tinkering
│   │   │   ├── 6.1.3. Maintenance & Assets/          # Stable portfolios and meta-checklists
│   │   │   └── 6.1.4. Script Attic/                  # Inactive tools and experiments
│   │   └── 6.2. Library & Learning/                  # Technical archive and deep-dives
│   │       ├── 6.2.1. Math & Stats/
│   │       ├── 6.2.2. Programming & Software Engineering/
│   │       ├── 6.2.3. Algorithms & Data Structures/
│   │       ├── 6.2.4. System Design & Distributed Systems/
│   │       ├── 6.2.5. Data Processing, Engineering & MLOps/
│   │       ├── 6.2.6. Machine Learning/
│   │       ├── 6.2.7. Deep Learning/
│   │       ├── 6.2.8. NLP & Vector Search/
│   │       ├── 6.2.9. Computer Vision/
│   │       ├── 6.2.10. Reinforcement Learning/
│   │       ├── 6.2.11. Intelligent Agents & Autonomy/
│   │       ├── 6.2.12. Robotics (Hardware & Control Systems)/
│   │       └── 6.2.13. AI Ethics, Safety & Governance/
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

## The Engine (Skills, Workflows & Tools)

This repository distinguishes between three types of "cognitive" capabilities that define how the Brain automation works. It is critical to understand the distinction between the "Laws of Physics" (Skills) and the "Recipes" (Workflows):

1. **Skills (`.agents/skills/`)**: **Mandatory Behaviors (The Laws of Physics)**. These are the fundamental rules that an AI Agent *must* follow whenever a specific trigger occurs (e.g., how to format YAML for *any* note, or when to update the changelog). They run automatically in the background.
2. **Workflows (`.agents/workflows/`)**: **Active Procedures (The Recipes)**. These are explicit, multi-step slash commands (e.g., `/create_new_note` vs `/capture_content`) that the user calls to achieve complex outcomes. **Workflows rely on Skills.** (For example, both the `/create_new_note` and `/capture_content` workflows invoke the exact same underlying `generate_obsidian_note` skill when they need to save a file).
3. **Tools (`tools/`)**: **Deterministic Capabilities**. These are Python scripts for repetitive, heavy-lifting tasks (like MP3 generation or folder maintenance) that are triggered manually via terminal.

### Agent Skills (Mandatory Behaviors)

| Skill | Trigger |
|---|---|
| `analyze_health` | When asked about symptoms, medical conditions, or health advice |
| `analyze_psych` | When asked about emotional processing |
| `generate_obsidian_note` | When asked to create a new note or integrate new notes/thoughts into the vault |
| `maintain_project_docs` | Keep README.md, AGENTS.md, CHANGELOG.md and requirements.txt up to date |
| `conventional_commits` | On every `git commit` |
| `cleanup_orphans` | When asked to "clean the vault" or perform maintenance |
| `skill_creator` | When asked to create, edit, evaluate, or optimize a skill |
| `workflow_creator` | When asked to create, edit, or improve a workflow |

### Agentic Workflows (Slash Commands)

- `/capture_content`: Format, move, or clean up a raw capture note to serve as an inbox item for future knowledge synthesis.
- `/add_job_requirement`: Automates extracting skills from a job description (PDF, URL, Markdown, etc.).
- `/audit_inbox`: Sorts raw notes and bullet points from the Brain Dump & Inbox into the main Zettelkasten structure.
- `/create_project`: Consolidates rough notes or ideas into a structured project note, complete with extracted tasks and materials.
- `/distill_learning`: Synthesizes complex technical articles or PDFs into atomic, interlinked notes.
- `/ingest_medical_record`: Parse and ingest raw medical records (PDF, XML, Images) into the Vault.
- `/plan_activity`: Cross-references Activities List, Date Ideas, and People Data notes to generate a structured markdown itinerary.
- `/render_resume`: Renders the Master Markdown Resume into a premium, professionally-styled PDF.

### Deterministic Tools (Scripts)

| Tool | Purpose | Usage |
|---|---|---|
| `youtube_transcript.py` | Downloads YouTube transcripts to text files. | `python tools/youtube_transcript.py <url>` |
| `generate_podcast.py` | Converts Vault notes to MP3 via edge-tts. | `python tools/generate_podcast.py` |
| `create_folders.py` | Idempotently creates the folder structure from TOC. | `python tools/create_folders.py` |
| `check_folders.py` | Validates Vault structure against TOC (dry-run). | `python tools/check_folders.py` |
| `add_gitkeeps.py` | Adds `.gitkeep` to all empty folders for Git tracking. | `python tools/add_gitkeeps.py` |
| `backup_vault.py` | Creates a timestamped local backup of the `Vault/`. | `python tools/backup_vault.py` |
| `medical_xml_parser.py` | Parses HL7 CDA medical XML files to structured Markdown. | `python tools/medical_xml_parser.py <path> <output_dir>` |
| `resume_engine/` | PDF rendering system for the Master Resume. | (See `tools/resume_engine/`) |

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

---

## Vault Maintenance
Whenever the `Table of Contents.md` is modified, run `tools/create_folders.py` to ensure the folder structure matches the plan.

- Handle `.gitkeep` files: add to empty folders, remove from populated ones.
- Orphaned folders (no matching TOC entry) should be reported, never deleted automatically.

---

## Obsidian Setup

Point Obsidian at the **`Vault/`** subfolder, not the repo root.

> Settings → About → Vault path → `…/Brain 2/Vault`
