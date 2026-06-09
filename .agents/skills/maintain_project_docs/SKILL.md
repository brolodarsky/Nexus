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

**CRITICAL RULES FOR DOCUMENTATION INTEGRITY:**
1. **AGENTS.md Maintenance:** `AGENTS.md` serves as your developer agent constitution. Do NOT compile skills, workflows, or tools into it. Keep it strictly focused on the core developer guidelines, rules, and core engine architectural principles.
2. **README.md Manual Updates:** Whenever you add, remove, or significantly change a script in `tools/` or a workflow/skill in `.agents/`, you MUST ensure that `README.md` is updated manually to accurately reflect the changes (e.g. updating the script/tool/workflow lists).

**CRITICAL RULES FOR CHANGELOG (CHANGESETS):**
1. **Never edit `CHANGELOG.md` or `CHANGELOG-RECENT.md` directly** during tasks.
2. **Create a Changeset Fragment:** Whenever you make a change that requires a changelog entry (according to the Git & Changelog Policy in `AGENTS.md`), you MUST write a new markdown file in the `.changeset/` directory: `.changeset/<unique-slug>.md` (e.g., `.changeset/add-email-tool-12345.md`).
3. **Changeset Format:**
   - YAML frontmatter specifying `type: patch | minor | major`.
   - Markdown body containing standard Keep a Changelog headings (e.g. `### Added`, `### Changed`, `### Fixed`, `### Removed`, `### Deprecated`, `### Security`) detailing the changes.

Example of a changeset file (`.changeset/add-email-tool-12345.md`):
```markdown
---
type: patch
---
### Added
- Integrated IMAP email client library under `tools/read_email.py`.
### Changed
- Refactored `tools/.secrets/` ignore rules in `.gitignore`.
```

For scripts, update the relevant section in `README.md` under `## Scripts`. Each script entry should include:
- **What it does** (one sentence)
- **Usage** — exact command to run
- **Any flags or config options** the user might need to know

Do not rewrite sections unrelated to the changed script.

## Trigger 2: After any `uv pip install` or `uv pip uninstall`

**ALWAYS regenerate `requirements.txt` immediately after installing or removing a Python package.**

Run this from the repo root:
```powershell
uv pip freeze > requirements.txt
```
Then commit `requirements.txt` along with whatever other changes prompted the install.
