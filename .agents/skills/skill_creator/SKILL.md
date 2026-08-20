---
name: skill-creator
description: Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.
---

A skill for creating new skills and iteratively improving them.

At a high level, the process of creating a skill goes like this:

- Decide what you want the skill to do and roughly how it should do it
- Write a draft of the skill

# Creating a skill

## Capture Intent

Start by understanding the user's intent. The current conversation might already contain a workflow the user wants to capture (e.g., they say "turn this into a skill"). If so, extract answers from the conversation history first — the tools used, the sequence of steps, corrections the user made, input/output formats observed. The user may need to fill the gaps, and should confirm before proceeding to the next step.

1. What should this skill enable Agents to do?
2. When should this skill trigger? (what user phrases/contexts)
3. What's the expected output format?
4. Should we set up test cases to verify the skill works? Skills with objectively verifiable outputs (file transforms, data extraction, code generation, fixed workflow steps) benefit from test cases. Suggest the appropriate default based on the skill type, but let the user decide.

## Interview and Research

Proactively ask questions about edge cases, input/output formats, example files, success criteria, and dependencies. Wait to write test prompts until you've got this part ironed out.

Check available MCPs - if useful for research (searching docs, finding similar skills, looking up best practices), research in parallel via subagents if available, otherwise inline. Come prepared with context to reduce burden on the user.

## Write the SKILL.md (Lean Agentic)

Based on the user interview, fill in these components:

- name: Skill identifier
- description: When to trigger, what it does. This is the primary triggering mechanism - include both what the skill does AND specific contexts for when to use it. All "when to use" info goes here, not in the body. Note: currently Agents have a tendency to "undertrigger" skills -- to not use them when they'd be useful. To combat this, please make the skill descriptions a little bit "pushy". So for instance, instead of "How to build a simple fast dashboard to display internal Anthropic data.", you might write "How to build a simple fast dashboard to display internal Anthropic data. Make sure to use this skill whenever the user mentions dashboards, data visualization, internal metrics, or wants to display any kind of company data, even if they don't explicitly ask for a 'dashboard.'"
- compatibility: Required tools, dependencies (optional, rarely needed)
- the rest of the skill :)

## Compile the Documentation

Once you have written a complete SKILL.md, you MUST invoke the maintain_project_docs skill so it can auto-compile your newly written skill into AGENTS.md and the CHANGELOG.md. Do not perform this compilation manually yourself.

## Skill Writing Guide

### Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

### Lean Formatting & Instruction Design

- Structural hierarchy over inline styling: Use markdown headers (#, ##, ###), numbered lists (1., 2.), and sub-bullets (-) to structure content. Agents parse document structure through hierarchy, not visual formatting.
- Concise structural anchors: Start the body with a clean anchor (e.g., `# Mandatory Behavior` or `# Steps`). A brief context or domain framing section is welcome if it adds new context, but never repeat the frontmatter description.
- Atomic instruction density: One directive per numbered item. Use sub-bullets for related rules, caveats, or failure modes rather than dense, run-on paragraphs.
- description only in frontmatter: Keep the triggering logic and scope in YAML frontmatter. The body is strictly for execution logic.
- Explicit cross-references: Explicitly name any sibling skills (e.g., `generate_obsidian_note`, `project_work`) or workflows that compose with this skill.
- Bold styling guidance: Use bolding sparingly for human scanners if helpful, but never rely on bolding to signal importance to agents—use list hierarchy, numbered sequence, and imperative directives instead.

### Progressive Disclosure

Skills use a three-level loading system:
1. Metadata (name + description) - Always in context (~100 words)
2. SKILL.md body - In context whenever skill triggers (<500 lines ideal)
3. Bundled resources - As needed (unlimited, scripts can execute without loading)

These word counts are approximate and you can feel free to go longer if needed.

Key patterns:
- Keep SKILL.md under 500 lines; if you're approaching this limit, add an additional layer of hierarchy along with clear pointers about where the model using the skill should go next to follow up.
- Reference files clearly from SKILL.md with guidance on when to read them
- For large reference files (>300 lines), include a table of contents

Domain organization: When a skill supports multiple domains/frameworks, organize by variant:
```
cloud-deploy/
├── SKILL.md (workflow + selection)
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```

### Writing Patterns

Prefer using the imperative form in instructions.

Defining output formats - You can do it like this:
```markdown
# Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

Examples pattern - It's useful to include examples. You can format them like this:
```markdown
## Commit message format
Example 1:
Input: Added user authentication with JWT tokens
Output: feat(auth): implement JWT-based authentication
```

### Writing Style

Try to explain to the model why things are important in lieu of heavy-handed musty MUSTs. Use theory of mind and try to make the skill general and not super-narrow to specific examples. Start by writing a draft and then look at it with fresh eyes and improve it.

### How skill triggering works

Understanding the triggering mechanism helps design better eval queries. Skills appear in Agents available_skills list with their name + description, and Agents decide whether to consult a skill based on that description. The important thing to know is that Agents only consult skills for tasks it can't easily handle on its own — simple, one-step queries like "read this PDF" may not trigger a skill even if the description matches perfectly, because Agents can handle them directly with basic tools. Complex, multi-step, or specialized queries reliably trigger skills when the description matches.

This means your eval queries should be substantive enough that Agents would actually benefit from consulting a skill. Simple queries like "read file X" are poor test cases — they won't trigger skills regardless of description quality.

Good luck!
