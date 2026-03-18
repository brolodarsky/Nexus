# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---
---

## [1.0.3] - 2026-03-18

### Added
- "Car Info" persistent reference note in Section 4.2.3
- "Project Ideas" persistent tracking note in Section 4.2.1
- "Currently Learning" note and tracking in Section 1.1
- "Project - MEM Billing" note and TOC mapping in Section 3.1

- "Maintenance Log" hybrid note linking to Google Sheets in Section 4.2.3
- "Maintenance Tracker Game Plan" project note outlining the build steps for the automated Google Sheet
- Note generation rules enforcing prefixed filenames (`Project -`, `Protocol -`, etc), banning redundant H1 headers, and moving the Table of Contents link to the top of the file
- Rule 10 in `AGENTS.md` enforcing `.gitkeep` files for empty directories.
- Folder maintenance scripts: `scripts/create_folders.py`, `scripts/check_folders.py`, and `scripts/add_gitkeeps.py`.

### Changed
- Moved all python scripts into the `scripts/` root directory.
- Updated all script references across `README.md`, `CHANGELOG.md`, and `AGENTS.md`.
- Readjusted relative paths in `scripts/generate_podcast.py`.

## [1.0.2] - 2026-03-17

### Added
- Blower Motor Noise Fix note for the 2005 Honda Pilot in section 4.2.3
- Monthly Hard Drive Backup Protocol note in section 1.2
- Protocol for FreeFileSync batch job backups
- Movie List note and TOC mapping in Section 5.3
- Education List note for general studies in Section 5.3
- Numbered sub-subsections to TOC Section 4.2 (4.2.1. Home Improvement, 4.2.2. Family Care, 4.2.3. Auto)
- "Exterior Repair Game Plan" note for the 2005 Honda Pilot in section 4.2.3
- Activities List note and corresponding subfolder structure in Section 5.1


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
