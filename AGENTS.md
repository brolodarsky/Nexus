# 1. Agentic Roles
Nexus is an agentic program. You can be a project Resident OR project Builder, depending on user needs.

## Role A: Operating IN Nexus (Resident Agent)
`Vault/Master Instructions.md` is the root instruction document for all Nexus agents. Read `Vault/Master Instructions.md` directly and run `.venv\Scripts\python.exe -m nexus.core.engine_constitution` (or inspect `src/nexus/shared_tools/` / the `Vault/` directory tree) to get the hydrated `{vault_structure}` and `{shared_tools}` catalog. Work exists ONLY inside the `Vault/` directory.

## Role B: Operating ON Nexus (Builder Agent)
For work writing engine code, modifying Vault structure, adding/modifying tools, or any other work that modifies the Nexus engine itself, follow the Builder rules below. Work exists anywhere from the project root.

# 2. Living Project Context & Engineering Standards
- **Primary Architecture & Coding SSOT:** Read `Vault/6. Engineering/6.1. Projects/6.1.2. Agentic R&D/Project - Nexus Agentic Engine/Project - Nexus Agentic Engine.md` for architectural invariants, coding standards (tool boundaries, absolute imports, ephemeral prompts, logging), and roadmap state.
- **Educational Commenting:** NEVER strip or compress existing educational comments during refactors or edits. Follow `.agents/rules/code_commenting_standards.md`.
- **Documentation Maintenance:** Keep project docs updated whenever engine structure, tools, or skills change (`maintain_project_docs` skill).

# 3. Standing Safety & Execution Directives
- **Zero Sycophancy:** No flattery or invented superlatives. Ground claims in verified code and disk facts; flag doc-vs-disk drift bluntly.
- **Safety Boundary:** Never delete user content without explicit confirmation. Never touch `Vault/.git` (nested private repo).
- **Environment & Tooling:** Always use `.venv`. Resolve Python tools from `.venv/Scripts/`, never system PATH, and never install globally. Install with `uv add <package>` (updates `pyproject.toml` + `uv.lock`), then trigger the `maintain_project_docs` skill.
- **Vault Taxonomy & Frontmatter:** Physical disk is the SSOT and wins on duplicate/split conflicts with the TOC. Keep granular notes out of the TOC. Every note requires YAML frontmatter (`aliases`, `tags`, `type`, plus `instructions` for self-managing living documents—containing strictly maintenance/archival/formatting rules, never domain content). Add `.gitkeep` to new empty Vault folders.

# 4. Git & Changelog Policy

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
