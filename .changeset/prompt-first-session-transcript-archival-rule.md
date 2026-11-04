---
type: patch
---
### Added
- **Prompt-First Session Transcript Archival Directive (`AGENTS.md` & `.agents/rules/session_transcript_archival.md`):** Codified standing rule requiring AI builder and resident agents to proactively offer to export and archive high-signal co-engineering session transcripts into `<Project>/Transcripts/` via `export_conversation.py` linked to `[[Build Log - <Project>]]` at the conclusion of non-trivial milestones. Explicitly prohibits silent or automated transcript exports without user confirmation.
- **Master Instructions Flush Integration (`Vault/Master Instructions.md`):** Integrated prompt-first transcript archival as step 3 of the Cognitive Boundary Flush protocol.
