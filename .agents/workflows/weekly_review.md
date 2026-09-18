---
description: Generates a weekly review memory and plans the upcoming week. Use when the user asks to do a weekly review, review the week, or plans the next week on Sunday evenings.
---

# Steps

1. Analyze Git History (The Memory):
   - Navigate to `C:\Users\Willi\Documents\Projects\Nexus` and run `git log --since="1 week ago" --oneline`.
   - Read the commit messages to identify what the user accomplished in the Nexus Engine or Portfolio.
2. Analyze Vault Modifications (The Memory):
   - Search the Vault for files created or modified in the last 7 days (e.g., project notes, roadmap updates, career file edits, etc.).
3. Analyze Journal & Tasks:
   - Read `Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md` for completed items and currently active items.
   - Read the user's recent journal/memory logs if applicable.
4. Compile the Weekly Review Note:
   - Apply the `generate_obsidian_note` skill to create a new note in `Vault/1. The Core/1.1.1. Personal Logs/Weekly Reviews/`. 
   - The filename should be `Log - Weekly Review YYYY-WXX.md` (where YYYY is the year and XX is the week number).
   - In this note, write a structured summary under a "## Look Back (The Memory)" header. Bullet point exactly what was shipped, built, written, or experienced.
5. Plan the Upcoming Week (The Plan):
   - Read the user's `To Do List.md` and `Job Hunt War Room.md` to understand active priorities.
   - Prompt the user in the chat: "Based on last week's momentum, what are your top 3 non-negotiable goals for the coming week?"
   - Await the user's response.
6. Finalize the Plan:
   - Once the user replies, append their top 3 goals to the review note under a "## Look Forward (The Plan)" header.
   - Ask the user if they would like you to generate or update an `implementation_plan.md` artifact tailored to these goals to guide their Deep Work blocks for the week.
7. Slide Forward the Short Term Execution Plan:
   - Open `Vault/1. The Core/1.1. Philosophy & Personal North Star/Short Term Execution Plan.md`.
   - Apply the **`[-5, +5]` Sliding Window Protocol**:
     - Roll the previous 5 days of verified momentum into `### ⏪ Verified Momentum (T-5 to T-1)`.
     - Archive items older than 5 days off the active page without clutter.
     - Anchor `### 🎯 Active Anchor` on the current date (`T-0`).
     - Populate `### ⏩ Tactical Flight Path` with the concrete upcoming 5 days (`T+1` to `T+5`), aligning Day +5 with the 5-Day CRM Nudge Protocol.
     - Recalibrate the active window scorecard without psychological back-tax.