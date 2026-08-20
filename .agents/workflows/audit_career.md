---
description: Run cross-document drift audit across all career strategy and portfolio documents.
---

# Steps

1. Run Deterministic Tier-1 Drift Audit:
   - Execute the zero-cost heuristic script to verify timestamp hierarchy, character limits, core keyword coverage, canonical links, and telemetry:
     ```bash
     .venv/Scripts/python.exe scripts/audit_career_drift.py
     ```
   - Inspect the terminal output for:
     - `[FAIL]` items (critical issues like missing files or character overflows in `Platform Profiles.md`).
     - `[WARN]` items (waterfall staleness, missing keywords across secondary documents, telemetry drift).

2. Perform Tier-2 Semantic LLM Drift Audit:
   - Read the core cluster files:
     - `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/My Skills.md`
     - `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/3.1.3. Professional Portfolio & Evidence/Resumes/Resume - Master.md`
     - `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/3.1.3. Professional Portfolio & Evidence/Resumes/Resume - Master (Extended).md`
     - `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/3.1.3. Professional Portfolio & Evidence/Platform Profiles.md`
     - `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/3.1.3. Professional Portfolio & Evidence/Portfolio Hub.md`
     - `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Job Hunt War Room.md`
   - Evaluate cross-document alignment across 4 dimensions:
     1. **Grounded Claims:** Is every skill claimed in `Resume - Master` backed by an evidence brief in `Portfolio Hub` and listed in `My Skills`?
     2. **Profile Parity:** Do the headlines, bios, and summaries in `Platform Profiles.md` accurately mirror the narrative in `Resume - Master.md`?
     3. **Operational Alignment:** Do the active quests and target roles in `Job Hunt War Room.md` reflect the current state of completed engineering?
     4. **Market Alignment:** Are high-frequency skills from `Employer Skill Requirements.md` captured in `My Skills.md` or assigned to `Current Learning.md`?

3. Propose Revisions via Two-Phase Commit (HITL):
   - If drift is detected, draft targeted multi-document patch diffs.
   - Present the changes clearly to the user before committing edits to the Vault.
