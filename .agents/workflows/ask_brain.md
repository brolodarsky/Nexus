---
description: Semantic vault search. Queries the ChromaDB index and returns a grounded answer with source citations. Use when you need facts from your notes without reading files manually. Requires `engine/agents/rag/ingest_vault.py` to be run first.
---

# Ask Brain (`/ask_brain`)

Use this workflow whenever you (or an orchestrating agent) need to retrieve factual information from the vault without reading individual notes manually.

> [!important] Prerequisite
> The ChromaDB index (`.chroma_db/`) must exist before this workflow can run. If it doesn't, run `ingest_vault.py` first:
> ```
> .venv\Scripts\python.exe engine/agents/rag/ingest_vault.py
> ```
> Re-run it after adding significant new notes. It is safe to re-run at any time.

## When to Use This

- You need longitudinal context from a domain (health history, project history, skill inventory).
- You were asked a question about the user's notes but don't know which file to read.
- You are mid-workflow and need a specific fact from the vault without interrupting the flow.

## When NOT to Use This

- The question requires real-time information (current dates, live prices, external news).
- You already know which specific note to read — just read it directly with `view_file`.
- The task is writing or creating, not retrieval.

## Steps

1. **Formulate the Query**
   - Write a specific, context-rich question. Vague queries return poor results.
   - Good: `"What symptoms did the user report at the April 2026 PCP visit?"`
   - Bad: `"health stuff"`

2. **Run the Agent**
   - Execute from the project root:
     ```
     .venv\Scripts\python.exe engine/ask_brain.py "<your query>"
     ```
   - Or, if the user has the PowerShell alias configured:
     ```
     brain <your query>
     ```

3. **Read the Output**
   - The agent returns a synthesized answer grounded in vault context.
   - Source note paths are printed at the bottom under `[Sources]`.
   - If the agent says "I don't have that in my notes" — rephrase with more specificity or check if `ingest_vault.py` needs to be re-run.

4. **Use the Result**
   - Incorporate the retrieved fact into your current workflow.
   - If a source note is cited, you may read it directly for full context: `view_file <source path>`.

## Query Tips

- **More specific = better retrieval.** Include domain, time period, or section name when possible.
- **Use the section's own language.** If the note uses "One-Off Tasks," query "one off tasks" — not "to-do items."
- **Iterate if needed.** First result weak? Rephrase with more context and run again.

## Integration Notes

Per the Architecture Decisions in [[Project - Vault RAG Agent (ask_brain)]], this workflow is deliberately **bounded**:
- ✅ Called explicitly by `/analyze_health` (longitudinal context is essential)
- ✅ Called explicitly by `/weekly_review` (project and task status)
- ❌ NOT auto-called by every workflow (adds latency, cost, and fragility)
