---
name: log_llm_conversation
description: Log design discussions, brainstorming sessions, and key technical decisions at the end of a conversation or pair programming session. Make sure to trigger this skill whenever the user mentions saving a chat log, logging a conversation, journaling a decision, or at the end of any complex session where important architectural, project, or code decisions were made, even if the user does not explicitly request it.
---

# Mandatory Behavior

Analyze the conversation history to extract design choices, technical reasoning, trade-offs, and architectural decisions. Prepend this summary to the top of the LLM conversation log.

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

1. Prevent duplicate entries: Check the top entries of the file to verify the conversation was not already logged.
2. Maintain descending chronological order: Always prepend new entries at the top of the log list.
3. High signal density: Write factual, concise bullet points rather than narrative paragraphs.
4. Link relevant entities: Use `[[Note Name]]` wiki-links when referencing vault notes, projects, or protocols.
5. Preserve document integrity: Do not modify existing historical log entries.
