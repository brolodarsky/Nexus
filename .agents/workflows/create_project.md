---
description: Scaffolds a structured canonical project note from raw ideas, inbox thoughts, or briefs, linking it to the Table of Contents and To Do List.
---

# Steps

1. Ingest & Classify Source Material:
   - Read the provided source text, scratchpad note (e.g. from `Vault/5. Capture & Archive/5.1. Brain Dump & Inbox/`), or natural language prompt.
   - Classify the project domain:
     - Software & Agentic Systems: Flagship applications, multi-agent swarms, backend services, or tool suites.
     - Physical & Operations: Home maintenance, auto repairs, hardware setups, or operational protocols.

2. Determine Folder Location & Naming:
   - Cross-reference `Vault/Table of Contents.md` and physical folder structure to choose the appropriate directory:
     - Software / AI: `Vault/6. Forge/6.1. Projects/6.1.1. Flagship Applications/` or `6.1.2. Agentic R&D/`
     - Operations / DIY: `Vault/3. Operations & Wealth/3.2. Home & Auto/` or similar.
   - Use `list_dir` on the target directory to verify existing naming patterns.
   - Format the filename using the standard taxonomic prefix: `Project - <Project Name>.md` (e.g., `Project - Nutrition Meal Planner.md`).

3. Scaffold the Canonical 7-Section Note:
   - Apply the `generate_obsidian_note` and `project_work` formatting standards.
   - Build the note using this canonical structure:

```markdown
---
aliases: [Alternative Name 1, Alternative Name 2]
tags: [projects, domain-tag, sub-tag]
type: project
---
**Back to:** [[Table of Contents#Section Header|Table of Contents]] | [[Parent Hub Note]]

## Goal
[High-level objective, core thesis, and measurable definition of done]

## Current State
| Dimension | Status | Notes |
|---|---|---|
| Architecture / Scope | 🟡 Inception | Initial scoping phase |
| Primary Codebase | ⚪ Not Started | ... |
| Infrastructure | ⚪ Not Started | ... |

## Architecture & System Blueprint
[Technical architecture, Mermaid diagrams, data models, or system specifications]
*(For physical/DIY projects, include ### Materials & Tools Needed or ### Budget here)*

## Standing Guidelines
[Non-negotiables, architectural constraints, security/privacy boundaries, or permanent rules that are NEVER checked off]

## Build Log
### YYYY-MM-DD — Project Scaffolding
- Initialized canonical project note and scoped roadmap tasks.

## Roadmap
- [ ] Phase 1: Core setup and dependency initialization
- [ ] Phase 2: Feature development
- [ ] Phase 3: Integration testing and verification

## Resources & Reference Links
- [[Internal Vault Link]]
- [External Documentation](https://...)
```

4. Extract Actionable Tasks into Roadmap:
   - Extract all milestones, prerequisites, and tasks from the source material into unchecked checkboxes (`- [ ]`) inside `## Roadmap`.
   - Organize tasks by logical phase or priority order.

5. Link in Table of Contents:
   - Add a `[[wiki-link]]` to the new project note in the corresponding section of `Vault/Table of Contents.md`.

6. Register in To Do List:
   - Add the project note link to the `Active Projects` section of `Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md`:
     `- [ ] [[Project - <Project Name>]] — Brief one-line objective`

7. Cleanup & Confirm:
   - If the source material was an inbox scratchpad in `Vault/5. Capture & Archive/5.1. Brain Dump & Inbox/`, delete or archive the scratchpad.
   - Output a summary of the created file path, TOC link, and To Do List entry to the user.
