---
type: patch
---

Updated model constants in `src/nexus/core/constants.py` by renaming `AI_MODEL` to `AI_MODEL_LOW` and including `AI_MODEL_MEDIUM` and `AI_MODEL_HIGH`. Updated the Career Agent (`src/nexus/agents/career/graph.py`) to use `AI_MODEL_MEDIUM` for main LLM operations and `AI_MODEL_LOW` for conversation summarization, and updated all other model references across router, librarian, email agent, and eval runners to `AI_MODEL_LOW`.
