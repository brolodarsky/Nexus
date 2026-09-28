---
type: minor
---
### Added
- Added `cognitive_boundary_flush` skill (`.agents/skills/cognitive_boundary_flush/SKILL.md`) implementing the 4-tier Hippocampal Flush protocol.
- Added `/flush` slash-command workflow (`.agents/workflows/flush.md`) for explicit event boundary execution.
- Added Engine Coding Standard 21 to `AGENTS.md` mandating proactive Hippocampal Flush prompting upon session conclusion or context switches.

### Deprecated
- Deprecated and removed legacy `log_llm_conversation` skill in favor of localized atomic episodic archiving in `<Section>/Archive/Conversations/` and domain-scoped ADR logging.
