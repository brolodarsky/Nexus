# AGENTS.md

> This file tells any AI agent how to work in this repository. The Agentic Constitution.

## Developer Agent Guidelines

### Meta-Boundary: Developer Agent vs. Nexus Engine
This constitution guides **you**, the external developer/coding agent (e.g., Antigravity, Cursor) working in this repository. It is distinct from the **Nexus Agentic Engine** (located in `src/nexus/`), which is the local-first application being developed.

For the internal logic, architecture, and principles governing the Nexus Engine agents themselves, refer to `src/nexus/core/ENGINE_CONSTITUTION.md`.

### Project Scope Docs: Ultimate Authority
All Nexus engine work is governed by a **two-level project scope hierarchy** stored in `Vault/6. Forge/6.1. Projects/6.1.2. Agentic R&D/Project - Nexus Agentic Engine/`:

- **Parent (master scope):** `Project - Nexus Agentic Engine.md` — top-level architecture, roadmap, and vision for the entire engine. This is the **ultimate authority** for all engine work. Read it before starting any non-trivial engine task.
- **Children (agent-level scope):** `Project - <AgentName>.md` (e.g., `Project - Career Agent.md`, `Project - Librarian Agent.md`, `Project - Health Agent.md`, `Project - Email Agent.md`). Each child doc governs a specific domain agent. New child docs will emerge as new agents are built — always check this folder for new entries.

**Standing obligations for every Nexus engine task:**
1. **Read first:** Before starting, open the relevant child doc (and the parent if the task is cross-cutting). Use them as the ground truth for Current State, Architecture, and Roadmap.
2. **Update after:** After completing meaningful work, update the relevant child doc (and the parent if architecture or scope has shifted) via the `project_work` skill.
3. **Conflict resolution:** If AGENTS.md or ENGINE_CONSTITUTION.md conflicts with a project scope doc on implementation details, the **project scope doc wins** for that agent's domain. If it conflicts on engine-wide architectural standards, raise the discrepancy before proceeding.

### Authorized Actions
1. **Vault Context Access:** You are authorized and encouraged to read notes inside `Vault/` (e.g., career, goals, projects, learning) to align your implementations, research, and suggestions with the user's specific context, preferences, and personal style.
2. **Tool Execution:** You are authorized to run engine runtime scripts in `src/nexus/shared_tools/` (e.g., email fetching, podcast generation) and repository maintenance scripts in `scripts/` (e.g., releases, backups) using the project's virtual environment (`.venv/`) to automate vault actions, sync vault data, or run test suites during your tasks.

---

## Engine Coding Standards (Standing Guidelines)
When writing code for Nexus (`src/nexus/` or `gui/`), you MUST adhere to the following standards:

1. **Agentic File System (AFS):** Notes, links, and folder taxonomy represent the primary state and memory. Prioritize deterministic local file-system navigation and traversing structured documents over chunk-based database RAG.
2. **Folder-Mapped Swarm:** Domain-specific agents are restricted to their corresponding top-level directories in `Vault/` via prefix validation. They are peer-blind by default.
3. **Deterministic Pre-flight Hydration & Librarian Escalation:** Sibling agents receive their local directory lists injected directly before running. Any cross-domain lookups must be escalated to the Librarian subgraph; domain agents never query peer folders directly.
4. **HITL Transaction Queue:** Writes and real-world actions use a two-phase commit. Agents draft proposed modifications to a centralized SQLite queue; changes are written only after human approval.
5. **Strict File Structure:** Agents must be extracted into modular format. For example, `api.py` (public boundary), `graph.py` (orchestration), `tools.py` (domain tools), etc.
6. **Shared Tools & Architectural Boundaries:** Maintain strict separation between core engine logic and agentic wrappers. Pure Python data access layers (like `vault_reader.py`) must NEVER contain LangChain `@tool` decorators. Agentic schemas and `@tool` factories must reside in `shared_tools/shared.py` (for cross-agent use) or in an agent's specific `tools.py`. Always use existing shared wrappers (e.g., `get_read_note_tool`, `get_propose_write_tool`) rather than reimplementing path resolution or domain-boundary logic inside individual agents.
7. **Absolute Imports:** All internal imports must be absolute imports relative to the package root. Do not use `sys.path` manipulation hacks.
8. **Validation & Logging (Pydantic & Loguru):** Avoid raw `os.getenv` or `print()` statements in engine code. Use centralized configurations via Pydantic (`src/nexus/core/config.py`) and structured logging via Loguru (`src/nexus/core/logger.py`) where available.
9. **Ephemeral System Prompt Injection:** System prompts must NEVER be passed as part of `graph.invoke()` input or returned in node state updates. They are built fresh inside the `call_model()` graph node via DPFH and prepended to the message array only for the LLM call. This prevents duplicate system prompts from accumulating in the checkpointer across turns.
10. **Three-Tier Agent Memory:** Domain agents implement three memory tiers: (1) **Subconscious** — procedural rules and conversation summary injected via DPFH into the system prompt; (2) **Short-Term Recall** — the last ~30 raw messages persisted by `SqliteSaver` with a single eternal `thread_id`; (3) **Deep Recall** — episodic decision logs accessed via tools, never kept in active context. The `summarize_conversation` node enforces the ~30 message window by compressing older turns into the Subconscious summary. Old messages are archived to `Logs/Conversation Archive.md` (Deep Recall) before pruning — nothing is lost. Use the shared summarizer in `src/nexus/shared_tools/summarizer.py`; do not reimplement per-agent.

---

## Rules

1. Never delete user content without explicit confirmation.
2. Always use the .venv — resolve Python tools from .venv/Scripts/, not system PATH. Never install dependencies globally. Always use `uv add <package>` for installations, which automatically updates `pyproject.toml` and `uv.lock`. If a new requirement is added, immediately trigger the maintain_project_docs skill.
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
- Release Workflow: When the user asks to "do a release" or "release changesets", you MUST execute the `/release` workflow logic: execute `.venv/Scripts/python.exe scripts/release.py`, commit the result with `docs(changelog): compile vX.Y.Z release from changesets`, and `git push`.
5. The TOC is the single source of truth for Vault folder structure and the high-level concept of this entire project, but Physical Folder Structure on Disk takes precedence when resolving duplicate/split directory discrepancies to avoid breaking existing paths. Do not clutter the TOC with individual granular notes (e.g. single medical visits, individual articles, daily logs). Those should be linked and organized inside specialized "Hub" or "Map of Content" (MOC) notes (e.g., Health Summary, Auto Knowledge Base).
6. All notes must have YAML frontmatter with aliases, tags, and type fields.
7. Audio files are gitignored — they sync via Syncthing, not Git.
8. Keep AGENTS.md AND README.md updated. If you make fundamental changes to the project/brain functionality, update these files to reflect the changes.
9. Add .gitkeep to empty folders. Whenever creating a new empty directory in the Vault, always create an empty .gitkeep file inside it so it can be tracked by Git.
10. All Project - and Protocol - notes must be registered in To Do List.md. Ensure new projects are added to the Active Projects section of Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md.
11. Do not touch the Vault/.git directory. This is a nested private repository for the user's personal history. It is not part of the engine and should be ignored by all cleanup or auditing tools.