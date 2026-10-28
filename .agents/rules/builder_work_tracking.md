# Builder Agent Work Tracking & Attribution Standard

> Standing instruction for all Builder Agents operating on the Nexus Engine, tools, workflows, skills, documentation, or Vault structure.

## Core Mandate
Whenever an agent acts in the **Builder** role (modifying engine code, refactoring tools, writing skills/workflows, updating docs, or reorganizing repository/Vault structure), the agent **must update `Vault/1. Core/1.1. Philosophy & Personal North Star/Plan.md`** before concluding the session.

## Target Location & Placement in Plan.md
- **Target Section**: Locate `# Today` $\to$ `## Career & Technical` in `Vault/1. Core/1.1. Philosophy & Personal North Star/Plan.md`.
- **Item Format**: Locate the existing Nexus work line item (typically formatted as `- [x] **P1 — Nexus work...**` or `- [x] P1 - Nexus work: ...`). If no line item exists for today, add one under `## Career & Technical`.
- **Cumulative Synthesis**: Do not spam separate bullet points for individual turns. Merge and expand the existing bullet so the day's synthesis captures the cumulative progress across all turns and sessions.

## Mandatory Attribution Directives (Human-AI Co-Engineering)
Nexus is fundamentally an autopoietic human-AI partnership. The daily synthesis in `Plan.md` serves as a permanent historical record and must **accurately reflect who did what and how the work was executed**:

1. **Explicit Delineation of Roles**:
   - **What the Human Did**: Detail the human's contributions—e.g., strategic direction, prompt formulation, problem scoping, architectural review, edge-case guidance, or manual verification.
   - **What the Agent Did**: Detail the agent's contributions—e.g., code authoring, automated refactoring, rule/skill creation, test suite implementation, schema migrations, or changeset generation.
2. **No Monolithic or False Attribution**:
   - **Never** write the entry as though the human manually authored code or executed technical tasks that the agent performed (e.g., avoid "I spent the afternoon writing AST parsers" when the agent generated them).
   - **Never** erase the human's input or present the work as unprompted autonomous actions.
3. **High Signal & Technical Specificity**:
   - Specify concrete components, scripts, tools, or notes modified (using Obsidian `[[Wiki-Links]]` for Vault notes where appropriate).
   - Use concise, past-tense, action-oriented phrasing with high information density.

## Reference Examples

### Exemplary (Accurate Collaboration & Specificity)
> `- [x] **P1 — Nexus Work (Human-AI Co-Engineering):** William directed architectural refactoring and specified tracking criteria; agent authored `.agents/rules/builder_work_tracking.md`, updated `AGENTS.md`, wired tracking directives into [[Plan]], and created changeset fragment.`

### Counter-Example (Human Credit Inflation)
> `- [x] **P1 — Nexus Work:** William rebuilt the blackboard database schema, wrote 7 unit tests, and created the builder rules.` *(Fails attribution: obscures the agent's execution)*

### Counter-Example (Vague & Erases Human Intent)
> `- [x] **P1 — Nexus Work:** Updated code and fixed some instructions.` *(Fails attribution: zero technical signal, completely omits human direction)*

