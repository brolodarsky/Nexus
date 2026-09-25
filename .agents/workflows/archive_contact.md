---
description: Prunes closed, rejected, or stale contacts from Professional CRM.md and archives them to Professional CRM - Archive.md to preserve agentic context windows.
---

# Archiving Protocol for Professional CRM

Use this workflow to archive specific contacts or run a comprehensive pruning sweep on `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/3.1.4. Networking & Professional CRM/Professional CRM.md`.

## Steps

1. Read Active Pipeline & Target Inputs:
   - Read the `### Active Pipeline & Outreach` table in `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/3.1.4. Networking & Professional CRM/Professional CRM.md`.
   - If the user specified a target (e.g., `/archive_contact Kapitus` or `/archive_contact Christi`), locate that specific row.
   - If running a general sweep (e.g., monthly review or Sunday maintenance), evaluate all rows against the archival triggers defined in `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/Protocol - Career Maintenance.md#CRM Archiving Protocol (Context Preservation)`:
     - **Terminal Outcome:** Explicit rejection received, candidate declined, or role confirmed filled/closed.
     - **Prolonged Silence:** No response after $\ge 14$ days following a 5-day follow-up nudge.
     - **Disqualified Lead:** Unviable offshore blast, blind RTR demands, or sensitive PII traps.

2. Draft Archive Row:
   - Match the target table schema in `Vault/3. Operations & Wealth/3.1. Career Strategy & Revenue/3.1.4. Networking & Professional CRM/Archive/Professional CRM - Archive.md`:
     `| Name | Role / Title | Company | Source | Last Contact | Status / Next Action | Historical Notes |`
   - Set **Status / Next Action** to `Closed / Archive`, `Closed / Rejected`, `Closed / Expired`, etc.
   - Ensure **Historical Notes** record the final resolution date, reason, and retain any wiki-links to conversation logs (`[[Archive/Conversations/...]]`) or job requisitions (`[[Saved Job Listings/...]]`).

3. Propose Two-Phase Commit Diff (HITL):
   - Present the candidate row(s) to the user with the justification for archiving.
   - Show the exact proposed diffs:
     - Row deletion from `Professional CRM.md`.
     - Row insertion into `Professional CRM - Archive.md` under `## Inactive & Closed Pipelines`.

4. Execute Migration:
   - Once approved, append the formatted row(s) to `Professional CRM - Archive.md`.
   - Delete the row(s) from `Professional CRM.md`.

5. Parity & Link Verification:
   - Verify that all internal wiki-links in the archived row resolve correctly.
   - Confirm the active pipeline contains only actionable opportunities and active institutional contacts.
