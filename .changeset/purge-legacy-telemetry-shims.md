---
type: patch
---
### Removed
- Removed post-migration legacy telemetry shims and file scanners across `src/nexus/core/chats_db.py`, `src/nexus/core/run_logger.py`, `src/nexus/api/main.py`, `src/nexus/core/trace.py`, `scripts/audit_agent_health.py`, and `scripts/audit_run_costs.py` (`migrate_legacy_telemetry_if_needed`, `_purge_legacy_files`, `RUNS_DIR`/`--runs-dir`, `message_traces` fallback, `dpfh_injected_files`, and legacy `RESULT_TRUNCATE_LEN`/`_truncate`), replacing `--runs-dir` on the audit CLIs with `--db-path`.
