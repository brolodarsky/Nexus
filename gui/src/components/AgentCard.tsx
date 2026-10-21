"use client";

import type { AgentStatus } from "@/lib/api";

interface AgentCardProps {
  agent: AgentStatus;
}

const STATUS_CONFIG: Record<
  AgentStatus["status"],
  { label: string; pillClass: string; icon: string }
> = {
  idle: { label: "Idle", pillClass: "glow-pill-idle", icon: "●" },
  running: { label: "Running", pillClass: "glow-pill-running", icon: "◉" },
  waiting_hitl: {
    label: "Awaiting HITL",
    pillClass: "glow-pill-waiting",
    icon: "◈",
  },
  not_built: {
    label: "Not Built",
    pillClass: "glow-pill-not-built",
    icon: "○",
  },
  error: { label: "Error", pillClass: "glow-pill-error", icon: "✕" },
};

const AGENT_ICONS: Record<string, string> = {
  nexus: "🧠",
  subagent: "⚡",
  librarian: "📚",
  career: "💼",
  medical: "🏥",
  content_router: "🔀",
  weekly_review: "📋",
  engine_architect: "⚙️",
};

export default function AgentCard({ agent }: AgentCardProps) {
  const config = STATUS_CONFIG[agent.status] ?? STATUS_CONFIG.not_built;
  const icon = AGENT_ICONS[agent.name] ?? "🤖";

  const lastRunLabel = agent.last_run
    ? new Date(agent.last_run).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Never";

  return (
    <div className="glass-card p-5 flex flex-col gap-4 group" id={`agent-${agent.name}`}>
      {/* ── Header Row ────────────────────────────────────── */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{icon}</span>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">
              {agent.display_name}
            </h3>
            <p className="text-xs text-text-muted mt-0.5 line-clamp-1">
              {agent.description}
            </p>
          </div>
        </div>
        <span className={`glow-pill ${config.pillClass}`}>
          <span className="text-[0.6rem]">{config.icon}</span>
          {config.label}
        </span>
      </div>

      {/* ── Stats Row ─────────────────────────────────────── */}
      <div className="flex items-center gap-6 text-xs text-text-secondary">
        <div className="flex items-center gap-1.5">
          <span className="text-text-muted">Last run:</span>
          <span className="text-text-primary font-medium">{lastRunLabel}</span>
        </div>
        {agent.error_count > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="text-accent-rose">⚠</span>
            <span className="text-accent-rose font-medium">
              {agent.error_count} error{agent.error_count > 1 ? "s" : ""}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
