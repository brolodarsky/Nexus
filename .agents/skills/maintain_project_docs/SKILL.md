---
name: maintain_project_docs
description: Keep README.md, AGENTS.md, CHANGELOG.md, and requirements.txt in sync whenever the project changes. Always use this skill after adding, removing, or modifying any tool, skill, or workflow; after any pip install/uninstall; or after any structural change to the Engine (e.g., new TOC sections, AGENTS.md updates). Individual note additions/moves/links do NOT warrant this skill.
---

# Maintain Project Docs

## Trigger 1: After adding, removing, or significantly changing project

**ALWAYS check whether `README.md`, `CHANGELOG.md`, `AGENTS.md` and any agentic skills, workflows or rules need updating** when, but not limited to, the following occurs:
- A `.py` script is added, removed, or significantly changed.
- An agentic skill or workflow is added, removed, or significantly changed.
- `/Vault` folder structure is changed.
- 'Table of Contents.md' high-level structure (H1/H2) is significantly changed. (Routine note links do NOT count).

**CRITICAL RULES FOR AGENTS.md (THE COMPILER PATTERN):**
`AGENTS.md` is a highly portable file that serves as your system constitution. To ensure external portability without context fragmentation, you must keep the `.agents` directories and `AGENTS.md` perfectly in sync.
1. **Verbatim Syncing**: When modifying the Skills or Workflows sections in `AGENTS.md`, you MUST scrape the `name` and `description` from the YAML frontmatter inside `.agents/skills/*/SKILL.md` or `.agents/workflows/*.md` and copy them **verbatim**.
2. **Auto-Compile**: Whenever you add, remove, or modify a workflow or skill, you MUST parse its updated frontmatter and strictly overwrite its corresponding entry in `AGENTS.md` so the docs remain a perfectly compiled artifact of the codebase.
3. **Tools**: Ensure any python scripts in `tools/` are accurately reflected in the `AGENTS.md` Tools table.

**CRITICAL RULES FOR CHANGELOG:**
1. **Read `CHANGELOG.md` first**.
2. **Same-Day Entries:** If an entry for the current date already exists (e.g., `## [1.0.3] - 2026-03-18`), you MUST append your new changes under that existing date's `### Added` or `### Fixed` headers. Do NOT create duplicate `## [Version] - Date` headers for the same day.
3. **Version Bumping:** Increment the version number only if it is a new day, OR if you believe the changes constitute a significant overhaul, major feature addition, or breaking change. In those significant cases, bumping the version on the same day is acceptable.

Example of appending to an existing day:
```markdown
### Added
- New Vector Embeddings note in section 5
- (Your new appended feature goes here)
```

For scripts, update the relevant section in `README.md` under `## Scripts`. Each script entry should include:
- **What it does** (one sentence)
- **Usage** — exact command to run
- **Any flags or config options** the user might need to know

Do not rewrite sections unrelated to the changed script.

## Trigger 2: After any `pip install` or `pip uninstall`

**ALWAYS regenerate `requirements.txt` immediately after installing or removing a Python package.**

Run this from the repo root:
```powershell
.venv\Scripts\pip.exe freeze > requirements.txt
```
Then commit `requirements.txt` along with whatever other changes prompted the install.
