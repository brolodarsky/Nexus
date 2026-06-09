---
type: patch
---
### Fixed
- Fixed `IndentationError` in `engine/agents/email/tools.py` due to missing `try` block for `list_recent_emails`.
- Fixed Content Router LLM hallucination where it aggressively triggered `fetch_emails` for local notes by tightening the `fetch_emails` tool docstring and router prompt.
