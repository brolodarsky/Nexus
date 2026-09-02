---
name: log_llm_conversation
description: Log high-level design discussions, architectural trade-offs, and conceptual idea forging at the end of a session. Trigger this skill whenever important engine architecture, system design, or foundational technical/philosophical decisions are made. Do NOT trigger for routine domain workflows, recruiter conversations, or daily life task minutiae.
---

# Mandatory Behavior

Analyze the conversation history to extract high-level architectural decisions, technical reasoning, foundational trade-offs, and idea forging. Prepend the structured summary to the top of the LLM conversation log.

## Target File

`Vault/1. The Core/1.1. Philosophy & Personal North Star/1.1.1. Personal Logs/Journal/Log - LLM Conversations.md`

## Entry Structure

Prepend the entry immediately below the introduction header/frontmatter block using this template:

```markdown
## YYYY-MM-DD — Descriptive Title of the Conversation

- Context: Summarize the starting problem, conversation context, and relevant models/tools in 1-2 sentences.
- Key Decisions & Insights:
  - Decision A: Choice made and the architectural or logical reasoning.
  - Decision B: Key trade-offs or alternatives considered.
```

## Rules

1. Scope boundary:
   - Restrict entries to engine architecture, technical paradigms, and macro cognitive evolution.
   - Route domain-specific life minutiae (recruiter interactions, medical logs, daily tasks) to dedicated domain living notes (`Professional CRM`, `Saved Job Listings`) and localized atomic archives (`Archive/Conversations/`).
2. Prevent duplicate entries: Check the top entries of the file to verify the conversation was not already logged.
3. Maintain descending chronological order: Always prepend new entries at the top of the log list.
4. High signal density: Write factual, concise bullet points rather than narrative paragraphs.
5. Link relevant entities: Use `[[Note Name]]` wiki-links when referencing vault notes, projects, or protocols.
6. Preserve document integrity: Do not modify existing historical log entries.
