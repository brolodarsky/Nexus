# Session Transcript Archival Standard (Prompt-First)

> Standing instruction for all AI coding, builder, and resident agents operating across this repository.

## The Core Mandate
Whenever concluding a non-trivial engineering, building, or deep debugging session (or when executing a Cognitive Boundary Flush), **proactively ask the user if they want to archive the session transcript** into the Vault.

**CRITICAL DIRECTIVE: NEVER ARCHIVE TRANSCRIPTS AUTOMATICALLY.**  
Silent, automatic archiving creates repository and Vault clutter with low-signal, routine, or throwaway exploratory turns. The decision to archive a session transcript belongs strictly to the human director.

---

## When to Prompt the User
Offer to archive the session transcript when:
1. **Architectural & System Milestones:** A non-trivial feature, new engine endpoint, database schema update, or GUI module was conceived, designed, and implemented.
2. **Deep Debugging & Failure Resolution:** The session surfaced and resolved unexpected runtime bugs, serialization traps, upstream dependency breaks (e.g. library payload structure changes), or obscure environment friction.
3. **High-Signal Co-Engineering & Learning:** The session served as an educational walkthrough where key design tradeoffs, token cost optimizations, or mental models were demystified.
4. **Cognitive Boundary Flush:** The user indicates wrap-up, end of day, or context switch (e.g., *"done for now"*, *"let's call it a night"*).

### Recommended Prompt Phrasing
Keep the question concise, direct, and un-sycophantic:
> *"Would you like me to export and archive this session's transcript into `Vault/<Project>/Transcripts/` and link it to the build log before we wrap up?"*

---

## Execution Protocol (Upon Human Confirmation)

Once the user approves transcript archival:

1. **Target Location:**
   Place the transcript inside a dedicated `Transcripts/` folder co-located with the relevant active project or section:
   ```text
   Vault/<Section>/.../<Project>/Transcripts/YYYY-MM-DD — <Title> (Session Transcript).md
   ```

2. **Deterministic Extraction:**
   Run the universal conversation exporter tool from `.venv`:
   ```bash
   .venv\Scripts\python.exe -m nexus.shared_tools.export_conversation <conversation_id|latest> -o "<path>"
   ```

3. **Curated Header & Architectural Retrospective:**
   Prepend the generated file with:
   - **YAML Frontmatter:** `tags: [engineering, transcript, session-log, autopoiesis]`, `conversation_id: <uuid>`, `type: transcript`, and `status: { archived: false }`.
   - **Bidirectional Links:** `[[Project - <Name>]]` and `[[Build Log - <Name>]]`.
   - **Executive Retrospective:** Concise breakdown of the human direction, failure modes encountered, non-obvious bugs debugged, and architectural lessons learned.

4. **Build Log Cross-Linkage:**
   Add a cross-reference link in the project's companion build log (`[[Build Log - <Name>]]`) under today's dated milestone:
   `- **Full Session Transcript & Learning Log:** [[YYYY-MM-DD — <Title> (Session Transcript)]]`
