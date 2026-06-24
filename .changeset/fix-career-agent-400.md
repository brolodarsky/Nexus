---
type: patch
---

Fixed an issue where the Career Agent would crash with an OpenAI 400 invalid_request_error due to dangling tool calls in the LangGraph state. 
Also hardened the `propose_write` tool by resolving paths dynamically based on domain scopes and gracefully de-duplicating path nesting, preventing the creation of redundant directories outside of the Vault. Updated the career agent prompt to use this new simplified behavior.
