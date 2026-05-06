# Brain 2: Agentic Knowledge OS & Personal Second Brain

This is my personal "second brain" and knowledge management system. It acts as an agentic operating system that manages my notes, thoughts, projects, career strategy, health records, and learning materials.

## The Human Context Statement (Why This Is Public)

This repository is **not** a generic, blank-slate template. It is a live, production system that runs my actual life. I have chosen a strategy of **Radical Transparency** and made this repository public to demonstrate real-world agentic orchestration on a complex, live system. 

You will see that the Agent Skills (`.agents/skills/`) and instructions (`AGENTS.md`) explicitly reference my personal context—like my health tracking, career goals, or specific personal protocols. This is intentional. The personal specificity is the proof that this system manages real human complexity.

**What's included in this public repo:**
- **The Engine Layer:** All the tools, agent skills, and workflows I use to automate my life.
- **The Vault Structure:** The folder skeleton and the `Table of Contents.md`.
- **(Private) The Vault Content:** The actual markdown notes, images, and PDFs in my vault are **local-only**. They are gitignored or encrypted, meaning you can't read my private thoughts, but you can see the architecture of the system.

## The Table of Contents (The Cognitive Map)

The `Vault/Table of Contents.md` is intentionally tracked and public. It demonstrates the *scope* of what a personal cognitive OS can manage—ranging from health and fitness to system design learning, caregiving, and professional networking—without exposing the content itself. It serves as both a structural map if you want to fork this, and a proof-of-concept for recruiters reviewing my work.

## How It Operates & Roadmap

This system currently follows a "best tool for the job" architecture:
- **The Content UI (Obsidian):** The daily interaction with notes, thoughts, and the knowledge graph happens entirely within Obsidian. It is the best tool for visualizing links, reading, and writing markdown.
- **The Engine UI (CLI & Agentic IDEs):** Deterministic tools and RAG queries can be executed directly via terminal. Complex agentic workflows (slash commands) are currently orchestrated using Agentic IDEs (like Cursor, Windsurf, or specialized agents) to follow the `.agents/` instructions.

**Future Evolution:**
While the current setup relies on Obsidian for viewing and an IDE for orchestrating agentic workflows, the roadmap points toward a fully unified, standalone application. Future iterations will include:
1. A **Standalone Autonomous Orchestrator** to run the agentic engine without relying on a third-party IDE.
2. A **Custom Content UI** to replace Obsidian, allowing tight, native integration between the knowledge graph and the agentic tools.

---

## Repository Structure

```
Brain 2/
├── .agents/                    # AI agent instructions
│   ├── skills/                 # Mandatory behaviors
│   │   ├── analyze_health/           # Health diagnostics & context check
│   │   ├── analyze_psych/            # Psych support & cognitive architecture
│   │   ├── career_counselor/         # Career architecture & strategic advice
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
│       ├── ask_brain.md              # Semantic vault search
│       └── render_resume.md          # PDF resume rendering
├── .venv/                      # Python virtual environment (not committed)
├── Vault/                      # All Brain content lives here
│   ├── .obsidian/              # Obsidian settings
│   ├── .stfolder/              # Syncthing folder
│   ├── 0. Inbox/               # Temp file storage for items bound for integration
│   ├── 0. Quick Capture.md     # Temp scratchpad note
│   ├── 1. The Core/                # Identity, governance, and foundations
│   │   ├── 1.1. Philosophy & Personal North Star/    # Values, principles, and long-term vision
│   │   │   └── Personal Logs/                        # Journal, Memories, and The Trophy Case
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
│   │   ├── 3.1. Career Strategy & Revenue/           # Job hunt, professional profile, and portfolio
│   │   │   ├── 3.1.1. Market Research & Future of Work/
│   │   │   ├── 3.1.2. Interview Prep & Technical Depth/
│   │   │   ├── 3.1.3. Professional Portfolio & Evidence/
│   │   │   ├── 3.1.4. Networking & Professional CRM/
│   │   │   ├── 3.1.5. Income Streams & Side Revenue/
│   │   │   └── 3.1.6. Compensation & Negotiation/
│   │   ├── 3.2. Wealth & Asset Management/           # Investment strategy and recurring payments
│   │   └── 3.3. Infrastructure & Logistics/          # Home lab, family estate, and auto maintenance
│   │       ├── 3.3.1. Home Improvement & Maintenance/
│   │       ├── 3.3.2. Family & Care/
│   │       └── 3.3.3. Auto/
│   ├── 4. Playground/              # Social, culture, and creativity
│   │   ├── 4.1. Social Life & Community/             # People data, social club, and adventures
│   │   ├── 4.2. Romance & Partnership/               # Relationship maintenance and date ideas
│   │   ├── 4.3. Culture & Inspiration/               # Media archive, reading list, and education
│   │   └── 4.4. Creativity/                          # Writing, jokes, and creative exploration
│   ├── 5. Capture & Archive/       # The Content Log & Reference
│   │   ├── 5.1. The Content Log (General)/           # Web archive and YouTube history
│   │   └── 5.2. Digital Inventory/                   # Hardware/software audits and backups
│   ├── 6. Forge/                   # Technical projects and learning
│   │   ├── 6.1. Projects/                            # Active development "The Lab"
│   │   │   ├── 6.1.1. Flagship Applications/         # Primary high-importance projects
│   │   │   ├── 6.1.2. Agentic R&D/                   # Agentic skills (mirrored), workshops, and tinkering
│   │   │   ├── 6.1.3. Maintenance & Assets/          # Stable portfolios and meta-checklists
│   │   │   └── 6.1.4. Script Attic/                  # Inactive tools and experiments
│   │   └── 6.2. Library & Learning/                  # Technical archive and deep-dives
│   │       ├── 6.2.1. Math/
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
│   │       ├── 6.2.12. AI for Science & Healthcare/
│   │       ├── 6.2.13. Robotics (Hardware & Control Systems)/
│   │       └── 6.2.14. AI Ethics, Safety & Governance/
│   ├── Audio/                  # Gitignored
│   └── Table of Contents.md   # Master index — source of truth for structure
├── AGENTS.md                   # AI agent constitution
├── CHANGELOG.md                # Running log of notable changes
├── engine/                      # RAG engine (semantic search)
│   ├── ask_brain.py             # Query agent
│   └── ingest_vault.py          # Vector store indexer
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
| `career_counselor` | When asked for career advice, job hunt strategy, or professional optimization |
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
- `/ask_brain`: Semantic vault search. Queries the ChromaDB index and returns grounded answers with source citations.
- `/render_resume`: Renders the Master Markdown Resume into a premium, professionally-styled PDF and DOCX.

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
| `engine/ingest_vault.py` | Indexes Vault files into ChromaDB for semantic search. | `python engine/ingest_vault.py` |
| `engine/ask_brain.py` | RAG query agent for answering questions from context. | `python engine/ask_brain.py "<question>"` |
| `engine/eval_rag.py` | LLM-as-a-judge evaluation framework for testing RAG retrieval quality. | `python engine/eval_rag.py` |
| `engine/brain_voice.py` | Voice-first RAG query agent using microphone and Whisper transcription. | `python engine/brain_voice.py` |
| `engine/brain_telegram.py` | Telegram Bot listener for smartphone and AFK access to the RAG agent. | `python engine/brain_telegram.py` |
| `resume_engine/` | PDF (Playwright) and DOCX (`python-docx`) rendering for the Master Resume. | `node tools/resume_engine/render.js` + `.venv\Scripts\python.exe tools/resume_engine/render_docx.py` |

### PowerShell Integration

For a more seamless experience on Windows, the following "global" commands are available once added to your PowerShell profile:

| Command | Purpose |
|---|---|
| `ask-brain "<question>"` | Runs the semantic search engine from anywhere. |
| `brain-voice` | Starts voice recording for hands-free semantic search querying. |
| `ingest-vault` | Triggers a vault re-index from anywhere. |
| `render-resume` | Renders the professional PDF resume. |
| `venv` | Searches for and activates a `.venv` in the current directory. |

---

## Architectural Methods

Brain 2 relies on several specific architectural patterns to maintain a clean boundary between the "Engine" (public) and the "Vault" (private).

### 1. Engine + Vault Separation
The repository is split into two layers:
- The **Engine** (`tools/`, `engine/`, `.agents/`, root docs) is the public portfolio—tracked, readable, and version-controlled.
- The **Vault** (`Vault/`) is the private content layer—mostly gitignored, synced locally via Syncthing.

### 2. Git-Crypt Defense-in-Depth
While all vault content is intentionally gitignored so it never enters the repository, I use **`git-crypt`** as a transparent layer of defense-in-depth for anything that *is* tracked inside the Vault (like folder structures).
- If a file inside the Vault accidentally gets tracked, its contents appear as binary gibberish on GitHub without the master key.
- The `.gitattributes` file defines this encryption scope; the TOC and `.gitkeep` files are explicitly excluded so they remain readable.

### 3. Syncthing + Git Dual Sync
- **Git** handles the Engine (code, skills, workflows).
- **Syncthing** handles the Vault content (notes, audio, large binaries) across my personal devices.
- For example, large MP3 files generated by the podcast tools are gitignored and sync via Syncthing only, avoiding repo bloat while maintaining mobile access.

### 4. Agentic Config Mirror
I maintain a mirror of the root `tools/` directory inside `Vault/6. Forge/6.1. Projects/6.1.2. Agentic R&D/Agentic Config/`. This is an Obsidian-native development workflow that lets me tinker with scripts directly inside my Obsidian vault, using its linking and preview features, without breaking the production code at the repository root. Changes are manually promoted once tested.

---

## How to Fork This Brain

If you want to use this as a starting point for your own system:
1. **Clone the repo** (you will only get the engine and the vault skeleton).
2. **Replace the vault content** by populating the folders with your own notes.
3. **Adapt the Skills & Workflows** (`.agents/skills/` and `.agents/workflows/`) to match your own domain context and personal rules.
4. **Keep the Engine** and continue building out new deterministic tools or agentic workflows.

---

## Vault Maintenance
Whenever the `Table of Contents.md` STRUCTURE is modified, run `tools/create_folders.py` to ensure the folder structure matches the plan.

- Handle `.gitkeep` files: add to empty folders, remove from populated ones.
- Orphaned folders (no matching TOC entry) should be reported, never deleted automatically.

---

## Obsidian Setup

Point Obsidian at the **`Vault/`** subfolder, not the repo root.

> Settings → About → Vault path → `…/Brain 2/Vault`
