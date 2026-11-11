---
type: minor
---

### Added
- **Dynamic AI Provider Rate-Limit (429 RESOURCE_EXHAUSTED) Backoff & Rollover:** Implemented `_extract_retry_delay`, `_cooperative_sleep`, and `_invoke_llm_with_resilience` in `src/nexus/agent/graph.py` across `call_model` (including deadline timeout fallback paths) and `spawn_subagent` ReAct loops to intercept 429 quota exhaustion errors, extract provider `retryDelay` metadata (or exponential backoff), stream structured SSE trace events to the Thinking Panel, and automatically retry upon sliding token-window rollover.
- **Demystified 429 User Diagnostic Guidance:** Added an actionable rate-limit diagnostic handler in `src/nexus/agent/api.py` explaining token-per-minute (TPM) sliding windows and sequential orchestration guidance.
- **Automated Regression Suite:** Authored 6 unit tests in `tests/test_model_config_and_resilience.py` verifying rate-limit error classification, delay extraction across Google RPC / natural text / headers, cooperative cancellation polling, backoff retry recovery, retry exhaustion, and diagnostic formatting (188/188 total pytest suite passing, 0 failures).
