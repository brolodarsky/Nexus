---
name: cognitive_boundary_flush
description: Execute the Cognitive Boundary Unit End (The Hippocampal Flush) at session closure or context switch. Always trigger when the user indicates wrap-up, bedtime, or ending a session (e.g., "call it a night", "heading to sleep", "done for now", "let's wrap up", "that's it for today", "good night") to proactively ask if they'd like to perform the Hippocampal Flush before closing.
---

# Cognitive Boundary Flush (The Hippocampal Flush)

> [!abstract] Purpose
> When a session reaches an event boundary (session wrap-up, bedtime, or major context switch), flush any unsaved decisions, task updates, and session summaries to the Vault so nothing important is stranded in chat history.

---

## Mandatory Protocol

### Step 1: Detect Boundary & Solicit Confirmation
When the user indicates they are winding down, calling it a night, switching contexts, or closing a task (and hasn't explicitly run `/flush`):
1. **Never** just respond with a casual sign-off or goodbye.
2. Proactively prompt the user:
   > *"Would you like me to run `/flush` (The Hippocampal Flush) to save our session's task updates, lessons, and event log to the Vault before wrapping up?"*
3. If the user confirms (or if they invoked `/flush` directly), proceed immediately to Step 2.

---

### Step 2: Synchronous Session Flush

Execute only the steps that actually apply to what happened in the session (do not invent filler updates):

#### 1. Reconcile Living State & Tasks:
- Check what files, projects, or tasks were modified or completed during the session.
- Update today's containers in `Vault/1. Core/1.1. Philosophy & Personal North Star/Plan.md` or the relevant section's `Tasks.md` / `To Do List.md` if statuses changed.

#### 2. Distill Procedural Rules (Only if a new reusable lesson emerged):
- If the session uncovered a concrete operational rule, preference, or anti-pattern, append a concise bullet to the relevant section's `Lessons Learned.md` (if that section maintains one).

#### 3. Write Atomic Episodic Event Note (For substantive sessions):
- For substantive multi-turn sessions (interviews, deep architectural decisions, major daily wrap-ups), create an atomic event note in `Vault/<Section>/Events/YYYY/YYYY-MM-DD - <Topic>.md`.
- Include standard YAML frontmatter:
  ```yaml
  aliases: [Event - YYYY-MM-DD - <Topic>]
  tags: [archive, event, <domain>]
  type: event-archive
  event_type: agent-session
  date: YYYY-MM-DD
  conversation_id: <current-conversation-id>
  ```
- Keep the body concise:
  - Backlinks to related notes.
  - **Summary:** 1 short paragraph on what was executed or decided.
  - **Key Outcomes / Decisions:** High-signal bullet points.
  - **Files Modified:** Clickable links to changed files.

#### 4. Record Engine ADR (Only for structural engine changes):
- If the session changed engine architecture or core repo standards, append a concise entry to `Vault/6. Engineering/Log.md`.

---

### Step 3: Confirm Closure
- Present a brief summary of which files were updated so the user can close the thread cleanly.
