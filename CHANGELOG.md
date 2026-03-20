# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

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
