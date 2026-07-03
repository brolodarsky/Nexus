---
type: minor
---
### Added
- Created `src/nexus/shared_tools/summarizer.py` with `summarize_conversation` for pruning and summarizing short-term recall.
- Added `summarizer_node` to `src/nexus/agents/career/graph.py` to compress working memory on the fly.
### Changed
- Refactored Career Agent (`api.py` and `graph.py`) to build the system prompt ephemerally inside `call_model`, preventing duplication bugs in the checkpointer state.
