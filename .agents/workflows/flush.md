---
description: Executes the Cognitive Boundary Unit End (The Hippocampal Flush) to consolidate active working memory, tasks, procedural heuristics, and atomic episodic archives into the Vault before session wrap-up or bedtime.
---

# /flush — Cognitive Boundary Unit End Protocol

> [!abstract] Purpose
> Triggers the synchronous **Hippocampal Flush** when wrapping up a session, calling it a night, or switching operational contexts. Flushes volatile working memory across all 4 tiers before subagent termination.

---

## Steps

1. **Reconcile Living State & Tasks (Semantic Memory / LTM):**
   - Review all files created, modified, or discussed during the active session.
   - Update the target section's Local Task Module (`Vault/<Section>/Tasks.md`) to mark completed items or append new sprint tasks.
   - If major project milestones were reached or archived, update `Vault/1. Core/1.1. Philosophy & Personal North Star/To Do List.md`.

2. **Extract Procedural Rules (Subconscious Memory):**
   - Check if the user corrected the agent, expressed preferences, or established a reusable heuristic.
   - Append concise heuristics to `Vault/<Section>/Lessons Learned.md`.

3. **Archive Atomic Event (Episodic Memory):**
   - Locate the most specific applicable section folder (e.g., `Vault/6. Engineering/`, `Vault/2. Health/`, `Vault/3. Operations/3.1. Career Strategy & Revenue/`).
   - Create an atomic markdown note in `Vault/<Section>/Events/YYYY/YYYY-MM-DD - <Topic>.md`.
   - Populate frontmatter (`aliases`, `tags`, `type: event-archive`, `event_type: agent-session | human-exchange`, `date`, `conversation_id`).
   - Include an Executive Summary, Key Decisions, and list of Documents Created/Modified.

4. **Append Decision Record (ADR):**
   - If architectural trade-offs, system designs, or structural decisions occurred, append an entry to `Vault/<Section>/Log.md`.

5. **Release Working Memory:**
   - Present a concise, structured confirmation table showing what was flushed to each tier.
   - Conclude cleanly, confirming that working memory is wiped and state is staged for offline consolidation.
