---
type: patch
---
### Fixed
- **Cross-Provider Thought & Thinking Signature Isolation (`src/nexus/agent/graph.py`, `src/nexus/agent/api.py`):** Prevented HTTP 400 `INVALID_THOUGHT_SIGNATURE` errors when switching between model providers mid-conversation (e.g., `claude-opus-5-5` turns followed by `gemini-3.8-flash`). Added provider-aware ephemeral sanitization (`_sanitize_messages_for_provider`) in `call_model()` that strips foreign-provider `thinking`/`redacted_thinking`/`reasoning`/`tool_use` blocks and signature metadata from outgoing request copies while preserving same-provider object identity, KV prompt-cache stability, and persisted `SqliteSaver` checkpoints; added one-shot reactive signature recovery in `_invoke_llm_with_resilience()` and diagnostic guidance in `run_nexus_agent_with_trace()`.
