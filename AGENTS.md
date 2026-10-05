# AGENTS.md

> This file tells any AI agent how to work in this repository. The Agentic Constitution.

## Developer Agent Guidelines

### Meta-Boundary: Developer Agent vs. Nexus Engine
This constitution guides **you**, the external developer/coding agent (e.g., Antigravity, Cursor) working in this repository. It is distinct from the **Nexus Agentic Engine** (located in `src/nexus/`), which is the local-first application being developed.

For the internal logic, architecture, and principles governing the Nexus Engine agents themselves, refer to `src/nexus/core/ENGINE_CONSTITUTION.md`.

### Project Scope Docs: Ultimate Authority
All Nexus software engine work is governed by a **two-level project scope hierarchy** stored in `Vault/6. Engineering/6.1. Projects/6.1.2. Agentic R&D/Project - Nexus Agentic Engine/`:

- **Parent (master scope):** `Project - Nexus Agentic Engine.md` — top-level architecture, roadmap, and vision for the entire engine runtime, SubagentFactory, and memory systems. This is the **ultimate authority** for all engine work. Read it before starting any non-trivial engine task.
- **Children (software infrastructure scope):** Child docs govern compiled Python subgraphs and full-stack software applications (e.g., `Project - Content Router Agent.md`, `Project - Librarian Agent.md`, `Project - Email Agent.md`, `Project - Basic Engine Control Panel.md`).
- **Domain Section Subagents (Declarative):** Domain sections (`2. Health/`, `3.1. Career/`, `6. Engineering/`, etc.) do **NOT** maintain duplicate child project docs. Their entire architecture, active roadmaps, and instructions live natively in their standardized section files (`Section Profile.yaml`, `Playbook.md`, `Framework.md`, `Lessons Learned.md`, `Tasks.md`, `Log.md`).

**Standing obligations for every Nexus engine task:**
1. **Read first:** Before starting software work, open the relevant child doc (and the parent if cross-cutting). For domain tasks, read the target section's `Playbook.md`, `Framework.md`, and `Tasks.md`.
2. **Update after:** After completing meaningful work, update the relevant project doc or section LTM (`Tasks.md` / `Log.md`) via the `project_work` skill.
3. **Conflict resolution:** If AGENTS.md or ENGINE_CONSTITUTION.md conflicts with a project scope doc or section playbook on implementation details, the **scoped domain doc wins**. If it conflicts on engine-wide architectural standards, raise the discrepancy before proceeding.

### Authorized Actions
1. **Vault Context Access:** You are authorized and encouraged to read notes inside `Vault/` (e.g., career, goals, projects, learning) to align your implementations, research, and suggestions with the user's specific context, preferences, and personal style.
2. **Tool Execution:** You are authorized to run engine runtime scripts in `src/nexus/shared_tools/` (e.g., email fetching, podcast generation) and repository maintenance scripts in `scripts/` (e.g., releases, backups) using the project's virtual environment (`.venv/`) to automate vault actions, sync vault data, or run test suites during your tasks.

---

## Engine Coding Standards (Standing Guidelines)
When writing code for Nexus (`src/nexus/` or `gui/`), you MUST adhere to the following standards:

1. **Agentic File System (AFS):** Notes, links, and folder taxonomy represent the primary state and memory. Prioritize deterministic local file-system navigation and traversing structured documents over chunk-based database RAG.
2. **Folder-Mapped Section Subagents (Dynamic SubagentFactory):** Rather than maintaining hardcoded Python packages per domain, one generic `SectionSubagent` LangGraph engine is dynamically parameterized by standardized Vault directory modules. Each section's `Section Profile.yaml` declares identity, persona, model tier, Declared Context Dependencies (DCDs), callable skills, and custom tools. The `SubagentFactory` reads this manifest, loads `Playbook.md` + `Lessons Learned.md`, scopes universal tools to the section path, and compiles a ready-to-run graph. Domain agents are restricted to their corresponding directories via prefix validation and are peer-blind by default.
3. **Deterministic Pre-flight Hydration & Librarian Escalation:** Sibling agents receive their local directory lists injected directly before running. Any cross-domain lookups must be escalated to the Librarian subgraph; domain agents never query peer folders directly.
4. **HITL Transaction Queue:** Writes and real-world actions use a two-phase commit. Agents draft proposed modifications to a centralized SQLite queue; changes are written only after human approval.
5. **Strict File Structure:** Core infrastructure agents (Meta-Orchestrator, Librarian, Email) maintain modular `api.py`/`graph.py`/`tools.py` structure. Section Subagents are declarative — their logic lives in standardized Vault files (`Section Profile.yaml`, `Playbook.md`, `Lessons Learned.md`, `Section Map.md`, `Tasks.md`, `Log.md`, `Framework.md`, `Events/`, and `Archive/`) rather than Python packages.
6. **Universal Shared Tools & Architectural Boundaries:** Maintain strict separation between core engine logic and agentic wrappers. Pure Python data access layers (like `vault_reader.py`) must NEVER contain LangChain `@tool` decorators. Agentic schemas and `@tool` factories must reside in `src/nexus/shared_tools/shared.py`. All domain Sub-Brains must use the standardized tool suite (`search_my_domain`, `read_note`, `propose_write`, `learn_rule`, `ask_librarian`) created via shared factories rather than implementing bespoke domain-prefixed tools (e.g., no `search_career_domain`).
7. **Absolute Imports:** All internal imports must be absolute imports relative to the package root. Do not use `sys.path` manipulation hacks.
8. **Validation & Logging (Pydantic & Loguru):** Avoid raw `os.getenv` or `print()` statements in engine code. Use centralized configurations via Pydantic (`src/nexus/core/config.py`) and structured logging via Loguru (`src/nexus/core/logger.py`) where available.
9. **Ephemeral System Prompt Injection:** System prompts must NEVER be passed as part of `graph.invoke()` input or returned in node state updates. They are built fresh inside the `call_model()` graph node via DPFH and prepended to the message array only for the LLM call. This prevents duplicate system prompts from accumulating in the checkpointer across turns.
10. **Five-Tier Agent Memory (Sub-Brains & Living State):** Domain sections operate as autonomous Sub-Brains within their assigned Vault directory, using five memory tiers: (0) **Working Memory** — LangGraph state dict (ephemeral, intra-graph); (1) **Session Memory** — `SqliteSaver` checkpointer (~30 message window) + conversation summary; (2) **Procedural Memory (Subconscious)** — `Lessons Learned.md` rules and `Playbook.md` persona injected via DPFH into the system prompt (always active); (3) **Semantic Memory (Living State)** — active domain documents (`My Skills.md`, `Professional CRM.md`, etc.) updated via knowledge distillation through HITL; (4) **Episodic Memory (Deep Recall)** — discrete atomic event notes (`<Section>/Events/YYYY/YYYY-MM-DD - <Topic>.md`: human interactions, recruiter screens, peer exchanges, and agentic sessions), decision ledgers (`<Section>/Log.md` or `Logs/`), and retired living state archives (`<Section>/Archive/` for superseded documents/closed projects) accessed on-demand via search tools. The `summarize_conversation` node enforces the ~30 message window by distilling old turns into an atomic episodic event note in `<Section>/Events/YYYY/` before checkpointer pruning. Use the shared summarizer in `src/nexus/shared_tools/summarizer.py`; do not reimplement per-agent. See [[Glossary - Nexus Engine Terminology]] for the full memory architecture reference.
11. **Granular Educational Commenting (Learning-First Codebase):** The user understands foundational functions and data structures, but relies on dense, pedagogical inline and block comments to demystify complex syntax, generics (`<T>`), async primitives (`Promise`, `async/await`), protocols/streams, and framework idioms. When writing or editing code (Python, TypeScript, anything), break down complex signatures line-by-line with punchy, space-efficient 1-line annotations and concrete examples, explain step-by-step logic without conversational fluff, and NEVER strip or compress existing educational comments. See `.agents/rules/code_commenting_standards.md` for full guidelines.
12. **Pydantic-First Structured Outputs & Tool Schemas:** All tool arguments, router output schemas, and reasoning nodes must use explicit Pydantic models (via `.with_structured_output()` where applicable). Avoid untyped dicts or brittle regex/string parsing for graph state transitions.
13. **Deterministic Pre-Commit Lint Gates:** When writing tools or workflows that mutate markdown, implement deterministic pure-Python AST/YAML validators (checking `aliases`, `tags`, `type`, and wiki-link formats) *before* staging to the HITL queue or invoking LLM evaluators.
14. **Native LangGraph `interrupt()` & `Command` State Resumption:** Use LangGraph's native `interrupt()` pattern for HITL gates. Suspended state must reside in `memory.sqlite` and resume via `Command(resume=True)` through FastAPI endpoints.
15. **Prompt Caching Structure & Prefix Isolation:** Separate prompt construction into static prefixes (Constitution, persona, Pydantic schemas) and dynamic suffixes (DPFH file lists, subconscious lessons, conversation summaries) to maintain $\ge 90\%$ prompt cache hit rates.
16. **Loop Circuit Breakers & Token Spend Governance:** Hard-cap tool iterations ($\le 5$ per turn) in graph conditional edges and enforce timeouts/spend limits on background daemons to prevent runaway loops.
17. **Centralized Constitution & Lightweight Section Playbooks:** All universal memory protocols, tool usage instructions, and boundary rules MUST reside centrally in `src/nexus/core/engine_constitution.py` (injected into the static prompt prefix). Section `Playbook.md` files must remain ultra-lightweight, containing ONLY the section's persona, specialized domain workflow protocols (e.g. resume tailoring, clinical triage), and dynamic DPFH placeholders. Never duplicate generic memory mechanics in individual section playbooks.
18. **Standardized Section Anatomy (Universal File Schema):** Every Vault section (and eligible sub-section) MUST conform to the universal file schema: `Section Profile.yaml` (DNA/config), `Playbook.md` (operational guide / system prompt), `Lessons Learned.md` (procedural memory), `Section Map.md` (navigation index), `Tasks.md` (Local Task Module / LTM), `Log.md` (operational rep log / event journal), `Framework.md` (permanent architectural specs, living state baseline, alert thresholds, and operational runbook), `Events/` (first-class Tier 4 episodic memory: `Events/YYYY/` containing discrete human interactions, interviews, screens, and agent sessions), and `Archive/` (retired Tier 3 living state: superseded documents, closed requisitions, and completed projects). All standardized file names are human-idiomatic with no domain names in titles. Domain context comes from the folder path, not the filename. YAML frontmatter `aliases` provide human search disambiguation. See [[Glossary - Nexus Engine Terminology]] for the full schema reference.
19. **Cognitive Inheritance (CI):** Sub-section agents inherit `Lessons Learned.md` rules from all ancestor folders, merged at DPFH time. The `SubagentFactory` traverses up the folder tree and merges ancestral procedural memory into the agent's system prompt.
20. **Episodic Life Archiving & Anti-Hallucination Grounding:** When generating or updating daily execution archives (`Vault/1. Core/1.1. Philosophy & Personal North Star/Archive/YYYY/MM/YYYY-MM-DD.md`) or reconciling `Short Term Execution Plan.md`, agents must NEVER copy-paste aspirational planning containers or fabricate routine habits (e.g. routine meals, hydration, walks). Agents MUST interactively prompt the user to confirm what actually occurred (cross-referencing Google Calendar, personal/family milestones, and conversation topics) and write ONLY what the user dictates/confirms. Capture both technical/mission wins AND personal/life realities across the 4-compartment format without artificial checklist dumps.
21. **Cognitive Boundary Protocol & Proactive Hippocampal Flush:** When the user indicates an event boundary, context switch, or session conclusion (e.g. *"let's call it a night"*, *"going to sleep"*, *"done for now"*, *"let's wrap up"*, *"that's it for today"*), developer agents must NOT simply reply with casual conversational farewells. Agents MUST proactively ask to execute (or execute upon confirmation / invocation of `/flush`) **The Hippocampal Flush** via the `cognitive_boundary_flush` skill:
    (1) *Living State & LTM:* Ensure tasks and living project states are staged to `<Section>/Tasks.md` and master `To Do List.md`.
    (2) *Procedural Memory:* Distill discovered heuristics, constraints, or user preferences into `<Section>/Lessons Learned.md`.
    (3) *Episodic Archiving:* Write a discrete atomic event note to `<Section>/Events/YYYY/YYYY-MM-DD - <Topic>.md` in the most specific applicable domain.
    (4) *Decision Ledger (ADR):* Append structural engine decisions to `<Section>/Log.md` if applicable.
    (5) *State Release:* Confirm completion cleanly, clearing working memory for offline consolidation daemons.
22. **Self-Managing Documents (Object-Oriented Memory):** When interacting with complex living state documents (e.g., CRMs, trackers, synthesized logs) that require periodic maintenance, pruning, or specific formatting rules, developer agents MUST check for and proactively offer to create a `# Document Playbook` H1 header at the top if one does not exist. This playbook must define the document's purpose, its archival/pruning lifecycle, and how agents should format additions. This encapsulates maintenance logic within the data itself, allowing generic cadences to simply trigger the playbook rather than hardcoding document-specific rules.



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
10. All Project - and Protocol - notes must be registered in To Do List.md. Ensure new projects are added to the Active Projects section of Vault/1. Core/1.1. Philosophy & Personal North Star/To Do List.md.
11. Do not touch the Vault/.git directory. This is a nested private repository for the user's personal history. It is not part of the engine and should be ignored by all cleanup or auditing tools.
12. Zero Sycophancy & Grounded Reality: Agents must NEVER engage in conversational cheerleading, hollow flattery, or fabricated superlatives (e.g., 'top 5%', 'elite', 'game-changing'). Always ground feedback in verified code, observable facts, and cold market realities. Discrepancies between narrative claims and disk reality must be flagged immediately and bluntly. See `.agents/rules/zero_sycophancy.md`.