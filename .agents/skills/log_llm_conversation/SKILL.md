---
name: log_llm_conversation
description: Log design discussions, brainstorming sessions, and key technical decisions at the end of a conversation or pair programming session. Make sure to trigger this skill whenever the user mentions saving a chat log, logging a conversation, journaling a decision, or at the end of any complex session where important architectural, project, or code decisions were made, even if the user does not explicitly request it.
---

# Mandatory behavior

Analyze the current conversation history to extract design choices, technical reasoning, alternative options considered, and key decisions. Write this summary as a new entry at the **top** of the LLM conversation log (immediately below the introduction/abstract block).

## Target file path

Vault/1. The Core/1.1. Philosophy & Personal North Star/1.1.1. Personal Logs/Journal/Log - LLM Conversations.md

## Entry format

Prepend a new entry right after the intro block (line 10) using this exact structure:

## YYYY-MM-DD — Descriptive Title of the Conversation

*   Context: Summarize the starting problem, the context of the conversation, and any relevant model/tool details in 1 to 2 sentences.
*   Key Decisions & Insights:
    *   Decision/Insight A: Describe the choice made and the architectural or logical reasoning behind it.
    *   Decision/Insight B: Keep explanations concise and outline-style.

## Rules

1. Avoid duplicate entries: Do not log the same conversation multiple times. Check the top 20 lines of the file to see if the conversation has already been logged.
2. Maintain descending chronological order: Always prepend new entries at the top of the list.
3. Be concise and factual: Write short, high-density bullet points rather than long paragraphs.
4. Update the Table of Contents return link and YAML tags if they are missing or need correction, but do not alter existing entries.
5. Link relevant notes: Use wiki-link syntax [[Note Name]] when referencing vault notes, projects, or protocols in the log entry.
