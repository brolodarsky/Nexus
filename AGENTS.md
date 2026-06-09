# AGENTS.md

> This file tells any AI agent how to work in this repository. The Agentic Constitution.

## Developer Agent Guidelines

### Meta-Boundary: Developer Agent vs. Nexus Engine
This constitution guides **you**, the external developer/coding agent (e.g., Antigravity, Cursor) working in this repository. It is distinct from the **Nexus Agentic Engine** (located in `src/nexus/` and `tools/`), which is the local-first application being developed.

### Authorized Actions
1. **Vault Context Access:** You are authorized and encouraged to read notes inside `Vault/` (e.g., career, goals, projects, learning) to align your implementations, research, and suggestions with the user's specific context, preferences, and personal style.
2. **Tool Execution:** You are authorized to run scripts in `tools/` and run Python or Node.js commands in `src/nexus/` using the project's virtual environment (`.venv/`) to automate vault actions, sync vault data, or run test suites during your tasks.

---

## Core Architectural Principles of Nexus
When modifying or extending the Nexus Engine, you MUST respect and preserve the following design paradigms:

1. **Agentic File System (AFS):** Notes, links, and folder taxonomy represent the primary state and memory. Prioritize deterministic local file-system navigation and traversing structured documents over chunk-based database RAG.
2. **Folder-Mapped Swarm:** Domain-specific agents are restricted to their corresponding top-level directories in `Vault/` via prefix validation. They are peer-blind by default.
3. **Deterministic Pre-flight Hydration & Librarian Escalation:** Sibling agents receive their local directory lists injected directly before running. Any cross-domain lookups must be escalated to the Librarian subgraph; domain agents never query peer folders directly.
4. **HITL Transaction Queue:** Writes and real-world actions use a two-phase commit. Agents draft proposed modifications to a centralized SQLite queue; changes are written only after human approval.

---

## Rules

1. Never delete user content without explicit confirmation.
2. Always use the .venv — resolve Python tools from .venv/Scripts/, not system PATH. Never install dependencies globally. Always use `uv pip install` for installations. If a new requirement is added, immediately trigger the maintain_project_docs skill.
3. Commit messages must follow Conventional Commits — see conventional_commits skill. 
4. Git & Changelog Policy. Use this table to determine whether a change requires a git commit and/or a changeset entry:

| What changed? | Commit? | Changeset? | Version bump |
|---|---|---|---|
| Tool, skill, or workflow code | ✅ | ✅ (write fragment to `.changeset/`) | Minor or patch (via release script) |
| New H1/H2 *section* in TOC / global structural paradigm change | ✅ | ✅ (write fragment to `.changeset/`) | Minor or patch (via release script) |
| Project docs (AGENTS.md, README.md) | ✅ | ✅ (write fragment to `.changeset/`) | Patch (via release script) |
| `.gitkeep` additions for new empty folders | ✅ | ❌ | — |
| Note wiki-links added to existing TOC sections | ❌ | ❌ | — |
| Individual note creation, edits, or deletions in `Vault/` | ❌ | ❌ | — |

- Key principles: Git is solely for the Engine (tools, skills, workflows, project docs) and Vault structure (new sections — not individual notes). Individual notes/thoughts are encrypted and backed up locally — avoid micro-commits.
- Changeset rule: When a changeset is required, write a small description to a new file in `.changeset/<unique-name>.md` with frontmatter `type: major|minor|patch` (see the `maintain_project_docs` skill). Never edit `CHANGELOG.md` or `CHANGELOG-RECENT.md` directly.
5. The TOC is the single source of truth for Vault folder structure and the high-level concept of this entire project, but Physical Folder Structure on Disk takes precedence when resolving duplicate/split directory discrepancies to avoid breaking existing paths. Do not clutter the TOC with individual granular notes (e.g. single medical visits, individual articles, daily logs). Those should be linked and organized inside specialized "Hub" or "Map of Content" (MOC) notes (e.g., Health Summary, Auto Knowledge Base).
6. All notes must have YAML frontmatter with aliases, tags, and type fields.
7. Audio files are gitignored — they sync via Syncthing, not Git.
8. Keep AGENTS.md AND README.md updated. If you make fundamental changes to the project/brain functionality, update these files to reflect the changes.
9. Add .gitkeep to empty folders. Whenever creating a new empty directory in the Vault, always create an empty .gitkeep file inside it so it can be tracked by Git.
10. All Project - and Protocol - notes must be registered in To Do List.md. Ensure new projects are added to the Active Projects section of Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md.
11. Do not touch the Vault/.git directory. This is a nested private repository for the user's personal history. It is not part of the engine and should be ignored by all cleanup or auditing tools.