---
aliases: [Maintenance Checklist, Vault Cleanup, System Admin]
tags: [maintenance, system, admin]
type: overview
---

# System Maintenance

Use this note to track recurring administrative and maintenance tasks for Brain 2.0.

> [!important] Recommendation
> Run through this checklist at least once a month to keep the system, the project files, and the repository in sync.

## Monthly Maintenance Checklist

- [ ] **Run `cleanup_orphans` Agent Skill**
  - Ask an agent to "run the cleanup orphans skill".
  - Review the agent's report.
  - Fix any broken `[[wiki-links]]`.
  - Delete or populate any empty folders (ignoring `.gitkeep`).
- [ ] **Review `README.md` and `AGENTS.md`**
  - Ensure any new scripts or workflows created this month are documented.
- [ ] **Verify Python Environment**
  - Ensure `.venv` is healthy and `requirements.txt` is strictly in sync with actual usage.
- [ ] **[[Monthly Hard Drive Backup Protocol]]**
  - Execute the FreeFileSync batch jobs to back up the system locally.

---
**Back to:** [[Table of Contents]]
