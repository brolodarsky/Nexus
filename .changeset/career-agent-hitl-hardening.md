---
type: minor
---
### Added
- `get_master_resume()` tool for the Career Agent — reads `Resume - Master.md` for resume tailoring workflows.
- Resume Tailoring Protocol in the Career Agent system prompt — agent reads master resume, crafts tailored version, and proposes via HITL.
- `run_career_agent_with_trace()` API — returns tool call metadata alongside agent response for eval observability.
- Known Cross-Domain File Paths section in the Career Agent prompt — provides exact vault paths for files outside the career domain (Current Learning, To Do List).

### Changed
- Hardened Career Agent HITL compliance via mandatory trigger rules in the system prompt (interview status changes, learning completions, skill acquisitions, job applications).
- Upgraded eval runner grader to use actual tool call traces instead of inferring HITL compliance from response prose.

### Fixed
- Career Agent HITL compliance: pass rate improved from 33% (1/3) to 100% (3/3), avg score from 5.0 to 8.0.
- Career Agent failing to call `propose_write` for cross-domain files (e.g., `Current Learning.md`) because it couldn't see them in its domain listing.
