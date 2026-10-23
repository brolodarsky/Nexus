---
type: patch
---
### Fixed
- **AI Request Timeout & Retry Resilience (`config.py` & `constants.py`):** Replaced hardcoded `timeout=90` and `max_retries=2` in `src/nexus/core/constants.py` with configurable `ai_request_timeout: int = 180` (default 180s) and `ai_max_retries: int = 3` in `src/nexus/core/config.py` (`EngineSettings`). Gives thinking/reasoning models (such as `gemini-4-argon`) adequate latency headroom and retry tolerance on heavy multi-turn conversation contexts (>150k characters) to eliminate premature `504 DEADLINE_EXCEEDED` errors.
- **Graceful Tier Fallback on Deadline Exceeded (`graph.py`):** Added resilient error recovery in `call_model()` (`src/nexus/agent/graph.py`). If the primary model tier (`gemini-4-argon` / `strong`) encounters a `504 DEADLINE_EXCEEDED` or request timeout after retries, `NexusAgent` automatically logs a trace alert and executes a seamless fallback to the low-latency tier (`gemini-3.8-flash` / `low`), preserving the active session and completing the turn instead of crashing.
- **Diagnostic Guidance for Chat Invocations (`api.py`):** Enhanced error reporting in `run_nexus_agent_with_trace()` (`src/nexus/agent/api.py`) to demystify provider deadline timeouts and provide actionable guidance to the user.
