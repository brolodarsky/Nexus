---
type: patch
---
### Fixed
- Fixed bug where `RemoveMessage` objects from `summarize_conversation` were incorrectly appended to agent states instead of deleting old messages, causing an OpenAI `BadRequestError` (stringified as `Got unknown type`). Replaced `operator.add` with LangGraph's `add_messages` across career, router, librarian, and email agents.
