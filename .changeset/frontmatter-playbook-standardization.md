---
type: minor
---
### Added
- Created `Vault/3. Operations/3.1. Career Strategy & Revenue/Playbook.md` as the canonical Section 3.1 operational guide, folding in the Career Strategy & Principal Advisor persona, resume rendering (`render.js` page-fill targets), job requirement ingestion (`Employer Skill Requirements.md`), compensation/interview calibration, and section asset routing.

### Changed
- Standardized Self-Managing Document contracts (`# Document Playbook` headers) into YAML frontmatter `playbook:` properties across `Vault/Playbook.md`, `AGENTS.md`, and active living Vault documents, strictly separating document maintenance/archival rules from substantive domain content.
- Consolidated all Resident Vault skills and workflows into `Vault/Playbook.md`, `Vault/1. Core/1.1. Philosophy & Personal North Star/Playbook.md`, `Vault/2. Health/Playbook.md`, `Vault/3. Operations/3.1. Career Strategy & Revenue/Playbook.md`, and `Protocol - Career Maintenance.md`, reserving `.agents/skills/` (`conventional_commits`, `maintain_project_docs`, `skill_creator`, `workflow_creator`) and `.agents/workflows/` (`/release`) strictly for Builder (repo/engine) operations.

### Removed
- Retired all 6 IDE-locked Resident skills (`generate_obsidian_note`, `cleanup_orphans`, `project_work`, `archive_project`, `cognitive_boundary_flush`, `career_counselor`) from `.agents/skills/` and all 14 Resident workflows (`add_job_requirement`, `archive_contact`, `ask_brain`, `audit_career`, `audit_inbox`, `capture_content`, `create_new_note`, `create_project`, `distill_learning`, `flush`, `ingest_medical_record`, `plan_activity`, `render_resume`, `weekly_review`) from `.agents/workflows/`.
