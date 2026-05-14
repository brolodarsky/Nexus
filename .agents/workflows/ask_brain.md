---
description: Agentic vault search. Uses a LangGraph ReAct agent to dynamically navigate the local filesystem and returns a grounded answer with source citations. Use when you need facts from your notes without reading files manually. No indexing required.
---

# Steps

1. Formulate the Query
   - Write a specific, context-rich question. Vague queries return poor results.
   - Good: `"What symptoms did the user report at the April 2026 PCP visit?"`
   - Bad: `"health stuff"`

2. Run the Agent
   - Execute from the project root using the main engine CLI:
     ```
     .venv\Scripts\python.exe engine/main.py "<your query>"
     ```

3. Read the Output
   - The agent returns a synthesized answer grounded in vault context.
   - Source note paths are printed at the bottom under `[Sources]`.
   - If the agent says "I don't have that in my notes" — rephrase with more specificity.

4. Use the Result
   - Incorporate the retrieved fact into your current workflow.
   - If a source note is cited, you may read it directly for full context: `view_file <source path>`.

# Query Tips

- More specific = better retrieval: Include domain, time period, or section name when possible.
- Use the section's own language: If the note uses "One-Off Tasks," query "one off tasks" — not "to-do items."
- Iterate if needed: First result weak? Rephrase with more context and run again.