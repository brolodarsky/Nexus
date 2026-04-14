# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.8.3] - 2026-04-14

### Changed
- Upgraded `analyze_health` skill (Step 9: Update the Vault) to explicitly mandate active narrative restructuring and visual re-weighting of `Health Summary.md`. Added strict requirements for table hygiene: re-sorting by urgency (urgent at top) and symptom consolidation (merging managed items) to maintain high signal-to-noise ratio.

---

## [1.8.2] - 2026-04-13

### Changed
- Promoted **Career Strategy & Revenue** from `3.3` to `3.1` to align with priority and daily usage.
- Re-ordered Section 3 (Operations & Wealth) folders: Wealth & Asset Management shifted to `3.2`, Infrastructure & Logistics shifted to `3.3`.
- Updated `Table of Contents.md` and `README.md` to map to the new hierarchy.
- **Fixed:** Reconstructed broken `.venv` configuration caused by absolute path fragmentation (moved from `Knowledge Base`).
- **Added:** Integrated `openai`, `langgraph`, `httpx`, and `python-dotenv` into `requirements.txt` for agentic development.
- **Added:** Created `sandbox_langgraph.py` in `Vault/6. Forge/6.1. Projects/6.1.2. Agentic R&D/` for isolated state machine testing.

---

## [1.8.1] - 2026-04-12

### Added
- In `generate_obsidian_note` skill (Formatting and Structure section), mandated the use of synchronized horizontal navigation bars for "tight clusters" of notes (e.g., Auto, Health, Career) to allow lateral movement between related Map of Content (MOC) notes.

### Changed
- Refactored **Rules 4 & 5** in `AGENTS.md` into a single unified **Git & Changelog Policy** with a structured decision table to eliminate model ambiguity at rule execution time. Previously, two prose rules with overlapping scope caused false-positive commits for routine note/TOC-link additions.
- Implemented **Compiled Portability Architecture** across core skills:
  - Added strict Compiler Rules to `maintain_project_docs` to force verbatim YAML transcription into `AGENTS.md` to prevent context drift.
  - Refactored `skill_creator` and `workflow_creator` to delegate `AGENTS.md` updates to `maintain_project_docs`.
  - Wrapped `AGENTS.md` lists in strict `<!-- AUTO-COMPILED -->` warnings to preserve system portability.
  
---

## [1.8.0] - 2026-04-11

### Changed
- Executed **Vault Structural Refactor & Friction Reduction** (Roadmap Item #5):
  - Moved **`Inbox/`** and **`Quick Capture.md`** out of deep nesting into the Vault root (`0. Inbox/`, `0. Quick Capture.md`) to eliminate capture friction.
  - Re-allocated **`Memories`** and Journaling into **`1.1. Philosophy & Personal North Star / Personal Logs`**, rather than creating an unnecessary extra section format.
  - Split Personal Logs into `Daily Notes (Journal)` for stream-of-consciousness, and `Memories/` for curated milestones and Trophy Case.
  - Renamed `5. Capture & Archive` subsections to reflect the removal of the Brain Dump.
- Updated `audit_inbox` and `capture_content` workflows to use the new zero-friction paths.
- Updated `Table of Contents.md` and `README.md` to reflect the new architecture.

---

## [1.7.0] - 2026-04-11

### Added
- Created new educational sections in **6.2 Library & Learning**:
  - **6.2.3. Algorithms & Data Structures**: Core CS fundamentals for technical depth and interview preparation.
  - **6.2.4. System Design & Distributed Systems**: Architectural principles for scaling complex systems.
  - **6.2.11. Knowledge Graphs & GraphRAG**: Integrated graph theory and applied graph-based retrieval into the NLP and Math domains.
- Added boilerplate study frameworks for all new sections to facilitate future knowledge synthesis.
- Added `.gitkeep` to new empty folders to ensure structural tracking in Git.

### Changed
- Re-architected Section **6.2 Library & Learning** for optimal pedagogical flow:
  - Moved **Data Engineering (6.2.5)** before Machine Learning to treat it as a prerequisite.
  - Grouped all Deep Learning application domains (NLP, Computer Vision, Reinforcement Learning) into a continuous sequence (6.2.8 - 6.2.10).
  - Promoted **Intelligent Agents (6.2.11)** as the culmination of the Deep Learning sequence.
- Renamed the master index alias from "Table of Contents" to include "Map of Content" (MOC) to reflect the Zettelkasten organizational paradigm.
- Updated `README.md` directory tree to reflect the deep restructure of the Forge.

---

## [1.6.2] - 2026-04-07

### Added
- Created new Vault section **2.5. Mom's Health Tracking** in the TOC and filesystem.
- Implemented **Mom's Health Summary** dashboard for centralized symptom, medication, and visit tracking.
- Created `Mom_Health_Logs` and `Mom_Lab_Work` folder structure for clinical record organization.
- Added `2.5. Mom's Health Tracking/` to the `README.md` directory tree.
- Created `tools/medical_xml_parser.py` script to parse complex HL7 CDA medical XML files into structured Markdown.
- Added `/ingest_medical_record` workflow to automate standardizing and importing raw patient records.

### Changed
- Upgraded `analyze_health` skill to optionally integrate checking Section 2.2 Medical insurance coverage documents for realistic financial/logistical medical planning.
- Standardized `analyze_health` skill to support multi-profile diagnostics (handling multiple health summaries like Mom's vs. Primary) via patient-context switching.

## [1.6.1] - 2026-04-05

### Changed
- Upgraded `analyze_health` skill with mandatory `search_web` step before forming any diagnostic hypothesis or treatment recommendation:
  - Open-ended recency queries (no year pinning — uses "latest", "current guidelines" language)
  - Evidence quality hierarchy: meta-analyses > RCTs > guidelines > case reports
  - Explicit instruction to surface conflicting evidence rather than defaulting to most recent
- Upgraded `analyze_psych` skill with the same web research step:
  - Open-ended recency queries; vigilance flags for psychedelic-assisted therapy, sleep science, neuroinflammation, gut-brain axis
  - Same evidence quality hierarchy and conflict-surfacing rule
- Added mandatory **Source Citation** rule (step 7) to both `analyze_health` and `analyze_psych` skills:
  - Preferred source hierarchy defined per skill (PubMed/NCBI, Cochrane, domain-specific clinical guidelines, Mayo Clinic, Cleveland Clinic, JAMA/NEJM/Lancet, NIH)
  - Blocklist: wellness blogs, product sites, Reddit, non-peer-reviewed sources
  - Mandatory inline markdown link format beside each claim
  - Fallback: cite institution + document name if direct URL unavailable
  - Links must be written into Vault note updates for persistent reference

## [1.6.0] - 2026-04-05

### Added
- New meta-skill `skill_creator` — moved from `Vault/SKILL.md` into `.agents/skills/skill_creator/SKILL.md`. Covers full skill anatomy, progressive disclosure, writing patterns, and eval guidance.
- New meta-skill `workflow_creator` — `.agents/skills/workflow_creator/SKILL.md`. Covers workflow anatomy, format rules, overlap resolution, sharp descriptions, and registration checklist. Mirrors `skill_creator` for the workflow domain.
- Both new skills registered in `AGENTS.md`, `README.md`, and `List - Agentic Instructions.md`.

### Changed
- Standardized all 6 existing skills against the `skill_creator` spec:
  - Added missing `name:` frontmatter field to `cleanup_orphans`, `conventional_commits`, `generate_obsidian_note`, `maintain_project_docs`.
  - Upgraded all weak descriptions to "pushy" triggering language (explicit context cues and imperative phrasing).
  - Fixed typo in `maintain_project_docs` description ("warrent" → "warrant").
  - Removed redundant `## Trigger` body sections from `analyze_health` and `analyze_psych` — trigger logic consolidated into `description:` only.
- Standardized all 8 workflows:
  - Removed redundant `## Trigger` body sections from `add_job_requirement`, `audit_inbox`, `create_project`, `distill_learning`, `plan_activity`, `render_resume`.
  - Sharpened overlapping descriptions on `capture_content`, `distill_learning`, and `create_new_note` — each now explicitly cross-references the other two to prevent agent confusion.

## [1.5.1] - 2026-04-01

### Added
- Implemented `/capture_content` workflow and agentic scaffolding (Template, SKILL updates) for logging videos, articles, and raw snippets.
- Created `tools/youtube_transcript.py` script to extract YouTube video transcripts directly to text files.
- Added `youtube-transcript-api` to `requirements.txt`.

## [1.5.0] - 2026-03-31

### Added
- Added `analyze_psych` agentic skill to provide science-based, non-sycophantic psychological support and cognitive architecture analysis.
- Mandatory context check of Section 2.3 ("Psych") in the TOC before providing emotional or mental health support.
- Updated `AGENTS.md`, `README.md`, and `Workshop - Agentic Instructions.md` to register the new skill.
- New Vault subsections under `2.2. Medical/`: `Health Logs/` (doctor visit notes) and `Lab Work/` (bloodwork results).
- New Vault subsections under `3.3. Career Strategy & Revenue/`: `3.3.2` through `3.3.6` (Interview Prep, Portfolio, Networking CRM, Income Streams, Compensation).
- Updated `README.md` directory tree to reflect all new subsections.
- Updated `Table of Contents.md` with wiki-links for all new Health Logs and Lab Work notes.

### Fixed
- Fixed stale references in `audit_inbox.md`, `add_job_requirement.md`, and `create_project.md`.
- Updated `create_project.md` to include mandatory registration in the `To Do List`.
- Updated `distill_learning.md` to optionally update `Current Learning.md` with new study materials.
- Significant improvements to `AGENTS.md`: fixed Rule 4 typo, added deterministic Tools documentation (Python scripts and Resume Engine), and added Rule 11 for mandatory `To Do List` registration for projects/protocols.

## [1.4.0] - 2026-03-30

### Added
- Added `analyze_health` agentic skill to enforce reading Section 2 of the TOC and performing comprehensive context checks before analyzing user health issues.
- Updated `AGENTS.md` to register `analyze_health` as a mandatory behavior skill.

## [1.3.0] - 2026-03-21

### Added
- Implemented `resume-engine` tool for generating professional PDF resumes from Markdown sources.
- Added `tools/resume_engine/` directory with `render.js` script and `style.css`.
- Updated `AGENTS.md` to include `resume-engine` as a deterministic capability for generating resumes.
- Added `tools/resume_engine/package-lock.json` for dependency management.

### Changed
- Deepened `README.md` repository structure to show one more header level (H2 equivalent) for all primary Vault sections.
- Added concise descriptive comments to all Vault and Agent Workflow files in the `README.md` directory tree for improved clarity.

## [1.2.0] - 2026-03-20

### Added
- Implemented `git-crypt` for transparent, local-only encryption of all Vault contents (`Vault/**`) before syncing to GitHub.
- Added strict ignore rules to `.gitignore` to prevent committing the `git-crypt` master key and other sensitive credential files.
- Updated `AGENTS.md` and `conventional_commits` skill to explicitly enforce batching of commits and pushes (forbid micro-commits).
- Added Production Engineering - Meta job listing to `Employer Skill Requirements.md` and refreshed the AI summary.
- Transitioned to an "Engine-only" Git policy: AI agents will no longer commit individual notes or "thoughts" in the `Vault/` directory, focusing Git operations on tools, skills, workflows, and project structure.

## [1.1.0] - 2026-03-19

### Added
- Four new Agentic Workflows to simplify knowledge management and cognitive load:
  - `/audit_inbox` — Zettelkasten maintenance and raw note structuring.
  - `/create_project` — Task extraction and project planning from raw notes.
  - `/distill_learning` — Concept extraction and atomic note generation from complex papers/articles.
  - `/plan_activity` — Intelligent itinerary generation using relationship/activity data.
- Updated `Protocol - System Maintenance.md` to include running `/audit_inbox`.

## [1.0.4] - 2026-03-19

### Added
- `Vault/Sensitive/` folder for sensitive notes/files gitignored

### Changed
- Renamed `scripts/` to `tools/`.
- Updated `AGENTS.md` and `README.md` to reflect the new unified "Tools & Workflows" structure.
- Updated `conventional_commits` skill and `AGENTS.md` to require TOC section references for Vault changes in git commit messages.
- Updated `maintain_project_docs` skill and `AGENTS.md` to require README, CHANGELOG and AGENTS.md updates when needed & to maintain README's vault structure diagram.
- Put section 3.Forge at the end of the TOC b/c it's so big. Changed TOC & folder structure.
- Added "Brain Functions & Automation" conceptual framework to `README.md` and `AGENTS.md` to clarify the use of Active Procedures (Workflows) vs. Deterministic Capabilities (Tools).

### Removed
- Section 3.2.12 - "Career" - moved to section 4.3

## [1.0.3] - 2026-03-18

### Added
- Note generation rules enforcing prefixed filenames (`Project -`, `Protocol -`, etc), banning redundant H1 headers, and moving the Table of Contents link to the top of the file
- Rule 10 in `AGENTS.md` enforcing `.gitkeep` files for empty directories.
- Folder maintenance scripts: `scripts/create_folders.py`, `scripts/check_folders.py`, and `scripts/add_gitkeeps.py`.
- `/add_job_requirement` workflow for automated PDF/URL job criteria extraction.

### Changed
- Moved all python scripts into the `scripts/` root directory.
- Updated all script references across `README.md`, `CHANGELOG.md`, and `AGENTS.md`.
- Readjusted relative paths in `scripts/generate_podcast.py`.

## [1.0.2] - 2026-03-17

### Changed
- Updated documentation to use conventional "Affirm Vault Structure" language instead of deprecated sync_vault.py
- Updated `AGENTS.md` rules to require `CHANGELOG.md` updates and `git push` on every commit.

### Removed
- All active references to `sync_vault.py` from `AGENTS.md` and `README.md`


## [1.0.1] - 2026-03-16

### Added
- "Middle ground" TOC header structure in section 3.2 (3.2.x numbered, children unnumbered)
- Top-level files in `Vault/` created to match full TOC structure
- Added new category files and documentation
- New CSS snippet `headers.css` for custom header styling in Obsidian

### Changed
- Relocated Library & Learning resources from `Vault/` root to `Vault/3. Forge/`

### Removed
- `sync_vault.py` — script deleted in favor of direct agentic structure management

## [1.0.0] - 2026-03-14

### Added
- `scripts/generate_podcast.py` — converts all Vault notes to MP3 via edge-tts
- `sync_vault.py` — syncs Vault folder structure with Table of Contents H1 sections
- `AGENTS.md` — central AI agent constitution for the repository
- `README.md` — project documentation with setup, scripts, and structure
- `requirements.txt` — pinned Python dependencies
- `.agents/skills/generate_obsidian_note` — skill for creating Zettelkasten-formatted notes
- `.agents/skills/sync_vault_structure` — mandatory skill for folder/TOC sync
- `.agents/skills/maintain_project_docs` — mandatory skill for requirements.txt and README updates
- `.agents/skills/conventional_commits` — mandatory skill for commit message format
- `.agents/workflows/create_new_note` — end-to-end note creation workflow
- Vault folder structure created for all 12 TOC sections
- `.gitkeep` normalisation across all empty Vault folders

### Changed
- Reorganised repo: moved all Obsidian content into `Vault/` subfolder
- `scripts/generate_podcast.py` resolves edge-tts from `.venv` automatically
- `.gitignore` updated to exclude `.venv/`, `Vault/Audio/`, and `podcast_history.json`
