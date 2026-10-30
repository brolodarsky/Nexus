---
type: minor
---
### Added
- **Anthropic Claude Model Options (`claude-opus-4-5` & `claude-sonnet-4-5`):** Added `langchain-anthropic` (`ChatAnthropic`) integration, `ANTHROPIC_API_KEY` / model tier settings in `src/nexus/core/config.py`, and side-by-side Chat UI model selector options (`Opus 4.5` for `strong` and `Sonnet 4.5` for `low`) in `src/nexus/core/constants.py`, `gui/src/components/chat/types.ts`, `gui/src/components/chat/ChatSidebar.tsx`, and `gui/src/components/chat/ChatInputBar.tsx`.
- **Provider-Matched Subagent Spawning (`spawn_subagent`):** Updated `call_model` and `spawn_subagent` in `src/nexus/agent/graph.py` so subagents spawned during an Anthropic Claude turn automatically route `low` tier execution to `claude-sonnet-4-5`.
- **Anthropic Cost & Prompt-Cache Pricing (`src/nexus/core/cost.py`):** Added Claude Opus 4.5 (`$5.00` input / `$0.50` cached / `$25.00` output per 1M tokens) and Claude Sonnet 4.5 (`$3.00` input / `$0.30` cached / `$15.00` output per 1M tokens) to the real-time pricing catalog and frontend fallback cost calculator.
