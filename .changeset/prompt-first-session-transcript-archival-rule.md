---
type: patch
---
### Added
- **Mandatory Engineering Section Instructions Directive (`AGENTS.md`):** Mandated that all Builder agents read and adhere to `Vault/6. Engineering/Section Instructions.md` ALWAYS when operating on the Nexus Engine, tools, or architecture.
- **Prompt-First Session Transcript Archival Directive (`Vault/6. Engineering/Section Instructions.md`):** Codified Section 2.D requiring AI agents to proactively offer to export and archive high-signal co-engineering session transcripts into `<Project>/Transcripts/` via `export_conversation.py` linked to `[[Build Log - <Project>]]` at the conclusion of non-trivial milestones. Explicitly prohibits silent or automated transcript exports without user confirmation.
- **Master Instructions Flush Integration (`Vault/Master Instructions.md`):** Integrated prompt-first transcript archival as step 3 of the Cognitive Boundary Flush protocol.
