"""
dashboard.py — Unified Engine Health & Status Aggregator.
Consolidates real-time telemetry across SQLite checkpointers (chats.db, memory.sqlite),
the HITL two-phase commit queue (hitl.db), and structured run dumps (logs/runs/).
"""
# json: Standard library for serializing dashboard metrics
import json
# sqlite3: Lightweight relational database driver for querying engine stores
import sqlite3
# datetime & timezone: Provides standardized UTC timestamps for dashboard rendering
from datetime import datetime, timezone
# Path: Object-oriented filesystem path manipulation
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexus.core.hitl_queue import get_pending_transactions
from nexus.core.run_logger import list_runs
from nexus.core.chats_db import get_conversations

# Project root paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
RUNS_DIR = LOGS_DIR / "runs"
CHATS_DB_PATH = LOGS_DIR / "chats.db"
HITL_DB_PATH = PROJECT_ROOT / "src" / "nexus" / "hitl.db"
VAULT_DIR = PROJECT_ROOT / "Vault"


def get_dashboard_summary() -> Dict[str, Any]:
    """
    Gathers real-time operational metrics across all engine sub-systems:
    1. Agent states & last run timestamps
    2. Pending Human-in-the-Loop (HITL) transaction queue size
    3. UI Conversation thread counts from SQLite chats.db
    4. Execution performance metrics (run count, average latency) from logs/runs/

    Returns:
        Structured dictionary containing aggregated metrics
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # 1. Pending HITL Transactions
    pending_txs = get_pending_transactions()
    pending_hitl_count = len(pending_txs)

    # 2. Conversations count from chats.db
    try:
        conversations = get_conversations()
        total_conversations = len(conversations)
    except Exception:
        total_conversations = 0

    # 3. Recent Runs & Performance Metrics
    recent_runs = list_runs(limit=50)
    total_runs_logged = len(recent_runs)
    
    latencies = [r["latency_seconds"] for r in recent_runs if r.get("latency_seconds") is not None]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    # 4. Agent Last Run Metadata Map
    agent_status_map = {
        "content_router": {"display_name": "Content Router", "status": "active", "last_run": None},
        "career": {"display_name": "Career Agent", "status": "active", "last_run": None},
        "librarian": {"display_name": "Librarian Agent", "status": "active", "last_run": None},
        "email": {"display_name": "Email Subgraph", "status": "active", "last_run": None},
        "health": {"display_name": "Health Agent", "status": "planned", "last_run": None},
    }

    # Populate latest run timestamp per agent from structured runs
    for run in recent_runs:
        agent_key = run.get("agent_name", "").lower()
        if agent_key in agent_status_map and agent_status_map[agent_key]["last_run"] is None:
            agent_status_map[agent_key]["last_run"] = run.get("timestamp")

    return {
        "timestamp": now_iso,
        "engine_version": "v2.11.0",
        "pending_hitl_count": pending_hitl_count,
        "pending_hitl_items": [
            {
                "id": tx["id"],
                "agent": tx["agent_name"],
                "action": tx["action_type"],
                "target_file": tx["target_file"],
                "created_at": tx.get("created_at"),
            }
            for tx in pending_txs[:5]
        ],
        "total_conversations": total_conversations,
        "total_runs_logged": total_runs_logged,
        "avg_latency_seconds": avg_latency,
        "agent_statuses": agent_status_map,
        "recent_runs": recent_runs[:5],
    }


def generate_dashboard_markdown(summary: Optional[Dict[str, Any]] = None) -> str:
    """
    Generates a clean, Obsidian-ready Markdown dashboard summary.

    Args:
        summary: Optional pre-fetched dashboard summary dictionary

    Returns:
        Formatted markdown document string
    """
    if summary is None:
        summary = get_dashboard_summary()

    lines = [
        "---",
        "aliases: [Engine Dashboard, Agent Status, System Status]",
        "tags: [nexus, engine, dashboard, telemetry]",
        "type: dashboard",
        "---",
        "**Back to:** [[Table of Contents]] | [[Project - Nexus Agentic Engine]]",
        "",
        "# 🖥️ Nexus Engine Unified Dashboard",
        f"*Generated: {summary['timestamp']} | Version: `{summary['engine_version']}`*",
        "",
        "## 📊 Operational Telemetry Overview",
        "",
        "| Metric | Value | Status |",
        "| :--- | :--- | :--- |",
        f"| **Pending HITL Decisions** | `{summary['pending_hitl_count']}` | {'🟡 Action Required' if summary['pending_hitl_count'] > 0 else '🟢 Clear'} |",
        f"| **Active UI Conversations** | `{summary['total_conversations']}` | 🟢 Healthy |",
        f"| **Total Structured Runs** | `{summary['total_runs_logged']}` | 🟢 Logged |",
        f"| **Average Agent Latency** | `{summary['avg_latency_seconds']}s` | ⚡ Nominal |",
        "",
        "---",
        "",
        "## 🤖 Agent Swarm Status Registry",
        "",
        "| Agent | Role / Domain | Operational State | Last Executed (UTC) |",
        "| :--- | :--- | :--- | :--- |",
    ]

    for key, info in summary["agent_statuses"].items():
        state_icon = "🟢" if info["status"] == "active" else "⚪"
        last_run_str = info["last_run"] or "*No recent runs*"
        lines.append(f"| **{info['display_name']}** | `{key}` | {state_icon} {info['status'].capitalize()} | {last_run_str} |")

    lines.extend([
        "",
        "---",
        "",
        "## ⏳ Pending HITL Transaction Queue",
        "",
    ])

    if summary["pending_hitl_count"] == 0:
        lines.append("> [!success] Zero Pending Transactions\n> All proposed agent modifications have been reviewed or resolved.")
    else:
        lines.extend([
            "| ID | Agent | Action Type | Target File | Created At |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ])
        for item in summary["pending_hitl_items"]:
            lines.append(f"| `#{item['id']}` | **{item['agent']}** | `{item['action']}` | `{item['target_file']}` | {item.get('created_at', 'N/A')} |")

    lines.extend([
        "",
        "---",
        "",
        "## 📜 Recent Agent Runs Snapshot",
        "",
        "| Run ID | Agent | Domain | Query Preview | Latency | Timestamp |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    if not summary["recent_runs"]:
        lines.append("*No recent run snapshots found in `logs/runs/`.*")
    else:
        for r in summary["recent_runs"]:
            query_snip = (r.get("query_preview", "") or "").replace("\n", " ").strip()
            if len(query_snip) > 40:
                query_snip = query_snip[:37] + "..."
            lines.append(
                f"| `{r.get('run_id')}` | **{r.get('agent_name')}** | `{r.get('domain') or 'N/A'}` | {query_snip} | `{r.get('latency_seconds')}s` | {r.get('timestamp', '')[:19]} |"
            )

    lines.append("")
    return "\n".join(lines)
