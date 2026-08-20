---
name: workflow_creator
description: Create new workflows, modify and improve existing workflows, and maintain workflow quality. Use this skill when the user wants to create a new slash-command workflow, edit or improve an existing workflow's steps or description, refactor a workflow to be clearer or more agentic, or review a set of workflows for consistency. If someone says "let's make a workflow for X" or "update this workflow", this skill applies.
---

# Workflow Creator

A skill for creating and improving .agents/workflows/ files — the slash-command recipes that define how the agent executes complex, multi-step tasks.

Workflows are different from skills: skills are automatic mandatory behaviors; workflows are explicit user-invoked procedures. A good workflow is a clear, step-by-step recipe the agent follows when the user calls /workflow-name.

---

## Anatomy of a Workflow

```
.agents/workflows/
└── my-workflow.md       # The entire workflow lives in one flat file
```

Workflows are a single markdown file — no bundled folders, no sub-resources. Keep them focused and readable.

### Required format (Lean Agentic)

```markdown
---
description: [What this workflow does and when to use it. Cross-reference alternatives if overlap exists.]
---

# Steps

1. Step Name: What to do. Be specific about which files to read, what to check, and what to output.
2. Step Name: ...
```

### Key Rules & Instruction Design

- Structural entry point: Start directly with `# Steps` (or a brief `# Context` block if critical domain framing is needed before steps). Never repeat the frontmatter description.
- description only in frontmatter: No `name:` field and no trigger sections in the body. Trigger logic lives in `description:` only.
- Atomic, numbered steps: Each numbered step should be a clear, imperative directive. Use sub-bullets (`-`) for specific substeps, paths, options, and failure modes rather than multi-sentence paragraphs.
- Explicit skill delegation: If a workflow relies on a skill (e.g., `generate_obsidian_note`, `project_work`), name the skill explicitly in the step text.
- Gate destructive actions: Any step that deletes, moves, or overwrites user content must be preceded by an explicit "Present plan and await user approval" step.
- Structural hierarchy over inline styling: Use lists and headers for agent signaling. Avoid relying on bolding for instruction emphasis.

---

## Creating a Workflow

### 1. Capture Intent

Start by understanding what the user wants the workflow to do. Extract from the conversation if possible:

- What is the user trying to accomplish?
- Is this truly a workflow (user-invoked, multi-step) or better suited as a skill (automatic behavior)?
- Does a similar workflow already exist? Check .agents/workflows/ before writing a new one.
- What are the inputs (user provides URL, note, raw text, etc.)?
- What is the expected output (new note, updated file, PDF, report)?

### 2. Check for Overlap

Before writing, scan existing workflow descriptions for semantic overlap. Workflows that are too similar will confuse the agent about which one to invoke. If overlap exists, either:
- Merge the new workflow into the existing one and add a step branch, or
- Add explicit cross-references in both descriptions (e.g., "For X, use /other-workflow instead").

The three content-handling workflows are a good example of how to differentiate:
- /capture_content → save raw external content for later (inbox)
- /distill_learning → deeply process a source into atomic Library notes
- /create_new_note → write an original internal thought into the Vault

### 3. Write the Workflow

Use the Lean Agentic format above. When writing steps:

- Be specific about file paths (e.g., Vault/5. Capture & Archive/5.1. Brain Dump & Inbox/Quick Capture.md).
- Be specific about which skill handles formatting, if applicable.
- Keep the total length reasonable — workflows should be readable in one pass. If a workflow exceeds ~50 lines, consider whether some steps can delegate to a skill.

### 4. Write a Sharp Description

The description: field is how the agent decides which workflow to invoke. It should:

1. State what the workflow produces (the output/outcome)
2. State the primary user context or trigger phrase
3. Cross-reference alternatives when overlap is possible

Weak: "Helps you add job postings to the vault."
Strong: "Extracts skills from a job description (URL, PDF, or text) and appends them to Employer Skill Requirements.md, then regenerates the AI summary. Use when reviewing or logging a new job posting."

### 5. Compile the Documentation

After writing the workflow file, you must delegate doc compilation:

1. Trigger maintain_project_docs: explicitly invoke this skill to auto-compile your new workflow into AGENTS.md and CHANGELOG.md. Do not manually edit AGENTS.md.
2. README.md — add an entry to the Agentic Workflows slash-command list.
3. Vault/6. Forge/6.1. Projects/6.1.2. Agentic R&D/List - Agentic Instructions.md — add a wiki-link under ### Workflows (Recipes).

---

## Improving an Existing Workflow

When asked to improve or refactor a workflow:

1. Read it first — use view_file to load the current content.
2. Check the description — is it specific enough? Does it cross-reference alternatives where needed?
3. Check the body — are there redundant ## Trigger or H1 Title sections? Remove them. Trigger logic belongs in description: only.
4. Check step clarity — are steps vague ("process the content") or specific ("read Quick Capture.md, extract each bullet as a distinct thought")?
5. Check skill references — does the workflow name the skills it depends on?
6. Propose changes — summarize what you'll change and why before editing, unless the changes are obviously cosmetic.
