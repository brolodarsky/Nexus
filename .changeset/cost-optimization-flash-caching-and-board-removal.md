---
type: minor
---

**Cost Optimization: Subagent Blackboard Removal, `gemini-3.8-flash` Low-Tier Restoration, Model Dropdown Menu, Anthropic Prompt Caching & User-Message Temporal Injection:**

- **Zero-Vestige Subagent Blackboard Removal (`src/nexus/`, `gui/`, `tests/`):** Removed `blackboard.py`, `/api/board` (`board.py`), `post_to_board`/`read_board` tools, automatic `post_bulletin` in `spawn_subagent`, `BlackboardDrawer.tsx`, `board.ts`, and `test_blackboard.py` to eliminate redundant output-token generation and dead UI/DB surface.
- **Restore `gemini-3.8-flash` as `"low"` Default & Switch UI Model Selector to Dropdown (`config.py`, `constants.py`, `cost.py`, `ChatInputBar.tsx`):** Reverted `"low"` and `"medium"` defaults and tier fallback pricing to `gemini-3.8-flash` while keeping `gemini-4-hydrogen` selectable as an explicit catalog option, and replaced the segmented model pills in `ChatInputBar.tsx` with an accessible dropdown menu.
- **Anthropic Prompt Caching & Subagent Prefix Stability (`constants.py`, `graph.py`):** Enabled top-level `model_kwargs={"cache_control": {"type": "ephemeral"}}` on `ChatAnthropic`, added block-level `cache_control` on Anthropic `SystemMessage` payloads (`_build_system_message`), and removed per-subagent `(Subagent #{serial})` variation from `spawn_subagent` system prompts so subagents hit the Turn-1 prefix cache.
- **User-Message Temporal Injection (`Master Instructions.md`, `engine_constitution.py`, `api.py`):** Removed `{current_time}` from `SystemMessage` and attached `[Current Time: YYYY-MM-DD HH:MM]` idempotently to each newly sent `HumanMessage` (`prepend_current_time_to_prompt`) so historical threads stay cache-stable across hour boundaries while keeping `chats.db` UI bubbles clean.
