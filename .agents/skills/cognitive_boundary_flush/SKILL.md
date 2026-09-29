---
name: cognitive_boundary_flush
description: Execute the Cognitive Boundary Unit End (The Hippocampal Flush) at session closure or context switch. Always trigger when the user indicates wrap-up, bedtime, or ending a session (e.g., "call it a night", "heading to sleep", "done for now", "let's wrap up", "that's it for today", "good night") to proactively ask if they'd like to perform the Hippocampal Flush before closing.
---

# Cognitive Boundary Flush (The Hippocampal Flush)

> [!abstract] Scope & Biological Grounding
> Implements Zacks & Radvansky's **Event Segmentation Theory (EST)** and the **Von Neumann memory hierarchy**. When a human or agent reaches a cognitive event boundary, active working memory (ALU/Registers) must be flushed into durable storage (AFS/Disk) to eliminate cognitive load (the Zeigarnik effect) and prevent context rot.

---

## Mandatory Protocol

### Step 1: Detect Boundary & Solicit Confirmation
When the user indicates they are winding down, calling it a night, switching contexts, or closing a task (and hasn't explicitly run `/flush`):
1. **Never** just respond with a casual sign-off or goodbye.
2. Proactively prompt the user:
   > *"Would you like me to execute the Cognitive Boundary Unit End (The Hippocampal Flush) to consolidate our session's decisions, tasks, and memory into the Vault before wrapping up?"*
3. If the user confirms (or if they invoked `/flush` directly), proceed immediately to Step 2.

---

### Step 2: Synchronous Real-Time Event Flush (The 4 Tiers)

Execute the following 4-tier flush synchronously:

#### Tier 1 — Reconcile Living State & LTM (Tier 3 Semantic Memory):
- Check what files, projects, or tasks were modified or completed during the session.
- Update the relevant domain's Local Task Module (`Vault/<Section>/Tasks.md`).
- If global project statuses shifted, update `Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md` (Active Projects or Completed Trophy Case).

#### Tier 2 — Distill Procedural Memory (Tier 2 Subconscious):
- Review the session for any newly discovered operational rules, formatting guidelines, architectural boundaries, or failure modes.
- Append concise, bulleted heuristics to the relevant section's `Lessons Learned.md` (e.g. `Vault/6. Forge/Lessons Learned.md` or `Vault/2. Health/Lessons Learned.md`).

#### Tier 3 — Write Atomic Episodic Archive (Tier 4 Episodic Memory):
- Determine the **most specific but truly applicable section** for the session.
- Create an atomic event note in `Vault/<Section>/Events/YYYY/YYYY-MM-DD - <Topic>.md`.
- Include standard YAML frontmatter:
  ```yaml
  aliases: [Event - YYYY-MM-DD - <Topic>]
  tags: [archive, event, ai-agents, <domain>]
  type: event-archive
  event_type: agent-session
  date: YYYY-MM-DD
  conversation_id: <current-conversation-id>
  ```
- Structure the body:
  - Backlinks to related projects and logs.
  - **Executive Summary:** 1-2 dense paragraphs summarizing what was explored and resolved.
  - **Key Architectural Decisions / Breakthroughs:** High-signal bullet points detailing choices and rationales.
  - **Documents Created, Archived & Modified:** Explicit list with clickable markdown links.

#### Tier 4 — Record Decision Ledger / ADR (if applicable):
- If the session produced structural engine decisions, system design changes, or architectural shifts, append a concise ADR entry to `Vault/<Section>/Log.md` (e.g., `Vault/6. Forge/Log.md`).

---

### Step 3: Clear Working Memory & Confirm Closure
- Present a clean, high-contrast summary showing each memory tier that was flushed.
- Conclude cleanly, confirming that working memory (ALU/Registers) is released and the state is staged for offline sleep/dream consolidation daemons.
