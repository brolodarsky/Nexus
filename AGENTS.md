# 1. Agentic Roles
Nexus is an agentic program. You can be a project Resident OR project Builder, depending on user needs. Either way all agents must understand the basics. Run `.venv\Scripts\python.exe -m nexus.core.engine_constitution`.

## Role A: Operating IN Nexus as a Resident Agent
Work exists ONLY inside the `Vault/` directory.

## Role B: Operating ON Nexus as a Builder Agent
For work writing engine code, modifying Vault structure, adding/modifying tools, or any other work that modifies the Nexus engine itself, follow the Builder rules below. Work exists anywhere from the project root.

# Living Project Context & Engineering Standards
- **Primary Project Doc:** Read `Project - Nexus Agentic Engine.md` for the entire living Nexus gameplan. Make sure to keep it updated with the `maintain_project_docs` skill after any change.
- **Educational Commenting:** NEVER strip or compress existing educational comments during refactors or edits. Follow `.agents/rules/code_commenting_standards.md`.
- **Daily Plan & Work Attribution:** Whenever doing Nexus work (engine, tools, workflows, Vault structure), update `Vault/1. Core/1.1. Philosophy & Personal North Star/Plan.md` under `# Today` (`## Career & Technical`). Clearly articulate what the human did/directed and what the agent executed/built—never make it appear as though the human did all the work alone or obscure the collaboration. Follow `.agents/rules/builder_work_tracking.md`.

# Standing Safety & Execution Directives
- **Zero Sycophancy:** No flattery or invented superlatives. Ground claims in verified code and disk facts; flag doc-vs-disk drift bluntly.
- **Environment & Tooling:** Always use `.venv`. Resolve Python tools from `.venv/Scripts/`, never system PATH, and never install globally. Install with `uv add <package>`.

# Git & Changelog Policy

| What changed? | Commit? | Changeset? | Version bump |
|---|---|---|---|
| Tool, skill, or workflow code | ✅ | ✅ (write fragment to `.changeset/`) | Minor or patch (via release script) |
| New H1/H2 *section* in TOC / global structural paradigm change | ✅ | ✅ (write fragment to `.changeset/`) | Minor or patch (via release script) |
| Project docs (AGENTS.md, README.md) | ✅ | ✅ (write fragment to `.changeset/`) | Patch (via release script) |
| `.gitkeep` additions for new empty folders | ✅ | ❌ | — |
| Note wiki-links added to existing TOC sections | ❌ | ❌ | — |
| Individual note creation, edits, or deletions in `Vault/` | ❌ | ❌ | — |

- Git covers the Engine (tools, skills, workflows, project docs) and Vault *structure*, not individual notes. Notes are encrypted and backed up locally. Avoid micro-commits.
- Commit messages follow Conventional Commits (`conventional_commits` skill).
- Changesets: new file `.changeset/<unique-name>.md` with frontmatter `type: major|minor|patch`. Never edit `CHANGELOG.md` / `CHANGELOG-RECENT.md` directly.
