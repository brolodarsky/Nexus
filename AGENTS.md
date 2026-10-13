# AGENTS.md

> How any IDE agent (Antigravity, Cursor) works in this repo. You are **Resident + Builder**:
> - **Operating IN Nexus (Resident):** Route all non-build behavior through [`Vault/Playbook.md`](Vault/Playbook.md) (`[[Playbook|Vault Playbook]]`), the target section's `Playbook.md` / `Lessons Learned.md` / `Tasks.md`, and the target note's `# Document Playbook`.
> - **Operating ON Nexus (Builder):** When writing engine code (`src/nexus/`, `gui/`, `scripts/`) or modifying Vault structure, follow the Builder rules below.

## Boot Sequence (every thread)
1. **Resident rules (always):** Read [`Vault/Playbook.md`](Vault/Playbook.md).
2. **Hydrate (always):** Identify the target Vault section(s) from the request and `Vault/Table of Contents.md`. Read their `Playbook.md`, `Lessons Learned.md`, and `Tasks.md` if they exist, plus any `# Document Playbook` in the target notes.
3. **Builder context (engine/Vault-structure work only):** Read `[[Concept - The Nexus Execution Lifecycle]]` (`Vault/6. Engineering/6.2. Library & Learning/6.2.1. Intelligent Agents & Autonomy/`) and the relevant scope doc in `Vault/6. Engineering/6.1. Projects/6.1.2. Agentic R&D/Project - Nexus Agentic Engine/`, then update via the `project_work` skill after completing work.

---

## Engine Coding Standards (Builder rules for `src/nexus/` and `gui/`)
Architecture behind these standards: see `[[Concept - The Nexus Execution Lifecycle]]`. Numbering is stable; other docs cite these numbers.

1. **AFS first:** Use deterministic file-system navigation over chunk-based RAG.
2. **SubagentFactory: PLANNED, NOT BUILT.** All current agents (`router`, `librarian`, `career`, `email`) are hardcoded LangGraph graphs. Don't describe spawning or factory compilation as working. Building it is gated by the Demo-Gated Rule in `Vault/1. Core/1.1. Philosophy & Personal North Star/Goals.md`.
3. **DPFH & Librarian escalation:** Inject local directory lists before running. All cross-domain lookups go through the Librarian subgraph (or direct cross-domain reads where configured).
4. **HITL queue:** Vault writes and real-world actions are two-phase commits through the SQLite queue.
5. **File structure:** Core infra agents use `api.py` / `graph.py` / `tools.py`. Section agents are declarative (Vault files, not Python packages).
6. **Tool boundaries:** Pure data layers (e.g., `vault_reader.py`) never contain `@tool`. Tool factories live in `src/nexus/shared_tools/shared.py`. Domains use the standard suite (`search_my_domain`, `read_note`, `propose_write`, `learn_rule`, `ask_librarian`); no domain-prefixed tools.
7. **Absolute imports** from the package root. No `sys.path` hacks.
8. **Config & logging:** Pydantic settings (`src/nexus/core/config.py`) and Loguru (`src/nexus/core/logger.py`). No raw `os.getenv` or `print()`.
9. **Ephemeral system prompts:** Build the prompt inside `call_model()` and prepend it for the LLM call only. Never put it in `graph.invoke()` input or in state updates (that duplicates it in the checkpointer).
10. **Memory windowing:** Use the shared `src/nexus/shared_tools/summarizer.py` (~30-message window → atomic `Events/YYYY/` note before pruning). Don't reimplement it per agent.
11. **Educational commenting (learning-first):** Dense, punchy 1-line annotations for complex syntax, generics, async, protocols, and framework idioms, with concrete examples. NEVER strip or compress existing educational comments. See `.agents/rules/code_commenting_standards.md`.
12. **Pydantic-first:** Tool args, router outputs, and reasoning nodes use explicit Pydantic models (`.with_structured_output()`). No untyped dicts or regex parsing for state transitions.
13. **Deterministic lint gates:** Markdown-mutating tools validate frontmatter (`aliases`, `tags`, `type`) and wiki-links in pure Python before HITL staging or LLM evaluation.
14. **Native `interrupt()` / `Command(resume=True)`:** HITL state is suspended in `memory.sqlite` and resumed through FastAPI endpoints.
15. **Prompt prefix isolation:** Static prefix (constitution, persona, schemas) + dynamic suffix (DPFH, lessons, summaries). Target ≥90% cache hits.
16. **Circuit breakers:** ≤5 tool iterations per turn in conditional edges. Timeouts and spend caps on background daemons.
17. **Centralized root playbook:** Universal agent behavior lives ONLY in [`Vault/Playbook.md`](Vault/Playbook.md) (loaded by `engine_constitution.py`). Section Playbooks hold only persona, domain workflows, and DPFH placeholders. Never duplicate generic mechanics into Section Playbooks or into this file.

> Standards 18–22 (section anatomy, Cognitive Inheritance, life archiving, flush trigger, Document Playbooks) moved on 2026-10-07 to the SSOT (anatomy, CI) and to `Vault/Playbook.md` (§6, §8, §9, §10).

---

## Rules

1. Never delete user content without explicit confirmation.
2. Always use `.venv`. Resolve Python tools from `.venv/Scripts/`, never system PATH, and never install globally. Install with `uv add <package>` (updates `pyproject.toml` + `uv.lock`), then trigger the `maintain_project_docs` skill.
3. Commit messages follow Conventional Commits (`conventional_commits` skill).
4. Git & Changelog Policy:

| What changed? | Commit? | Changeset? | Version bump |
|---|---|---|---|
| Tool, skill, or workflow code | ✅ | ✅ (write fragment to `.changeset/`) | Minor or patch (via release script) |
| New H1/H2 *section* in TOC / global structural paradigm change | ✅ | ✅ (write fragment to `.changeset/`) | Minor or patch (via release script) |
| Project docs (AGENTS.md, README.md) | ✅ | ✅ (write fragment to `.changeset/`) | Patch (via release script) |
| `.gitkeep` additions for new empty folders | ✅ | ❌ | — |
| Note wiki-links added to existing TOC sections | ❌ | ❌ | — |
| Individual note creation, edits, or deletions in `Vault/` | ❌ | ❌ | — |

- Git covers the Engine (tools, skills, workflows, project docs) and Vault *structure*, not individual notes. Notes are encrypted and backed up locally. Avoid micro-commits.
- Changesets: new file `.changeset/<unique-name>.md` with frontmatter `type: major|minor|patch`. Never edit `CHANGELOG.md` / `CHANGELOG-RECENT.md` directly.
- Release ("do a release"): run the `/release` workflow → `.venv/Scripts/python.exe scripts/release.py`, commit `docs(changelog): compile vX.Y.Z release from changesets`, then `git push`.
5. The TOC is the SSOT for Vault structure, but the physical disk wins on duplicate/split conflicts. Keep granular notes out of the TOC; link them from Hub/MOC notes.
6. Every note has YAML frontmatter with `aliases`, `tags`, `type`.
7. Audio files are gitignored (they sync via Syncthing).
8. Keep AGENTS.md and README.md current after fundamental changes.
9. Add `.gitkeep` to every new empty Vault folder.
10. Register every `Project -` / `Protocol -` note under Active Projects in `Vault/1. Core/1.1. Philosophy & Personal North Star/To Do List.md`.
11. Never touch `Vault/.git`. It is a nested private repo, so exclude it from cleanup and audit tools.
12. Zero sycophancy: no flattery or invented superlatives. Ground claims in verified code and facts, and flag doc-vs-disk drift bluntly. See [`Vault/Playbook.md`](Vault/Playbook.md) §11.