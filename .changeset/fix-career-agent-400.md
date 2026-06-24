---
type: patch
---
### Fixed
- Fixed an issue where the Career Agent would crash with an OpenAI `invalid_request_error` (400) due to dangling tool calls in the LangGraph state checkpoint after interruptions. 
- Hardened the `propose_write` tool by resolving paths dynamically based on domain scopes and gracefully de-duplicating path nesting, preventing the creation of redundant directories outside of the Vault (such as in `PROJECT_ROOT`). 
- Updated the career agent prompt to use this new simplified pathing behavior.
