"use client";

import { useEffect, useState } from "react";
import AgentCard from "@/components/AgentCard";
import StatCard from "@/components/StatCard";
import { getAgentStatus, getHealth, getPendingHitl } from "@/lib/api";
import type { AgentStatus, HealthResponse, Transaction } from "@/lib/api";
import Link from "next/link";

export default function DashboardPage() {
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [pendingHitl, setPendingHitl] = useState<Transaction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // isFleetCollapsed: accordion toggle to collapse/expand the registered agent fleet card grid
  const [isFleetCollapsed, setIsFleetCollapsed] = useState(false);
  // isActionsCollapsed: accordion toggle to collapse/expand the quick actions launcher menu
  const [isActionsCollapsed, setIsActionsCollapsed] = useState(false);

  useEffect(() => {
    async function fetchData() {
      try {
        const [healthData, agentData, hitlData] = await Promise.all([
          getHealth(),
          getAgentStatus(),
          getPendingHitl()
        ]);
        setHealth(healthData);
        setAgents(agentData);
        setPendingHitl(hitlData);
        setError(null);
      } catch (e) {
        setError(
          e instanceof Error ? e.message : "Failed to connect to engine"
        );
      } finally {
        setLoading(false);
      }
    }

    fetchData();

    // Poll every 15 seconds for live status
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, []);

  // Derived stats
  const activeAgents = agents.filter((a) => a.status === "idle" || a.status === "running").length;
  const pendingHitlCount = pendingHitl.length;
  const totalAgents = agents.length;
  const notBuilt = agents.filter((a) => a.status === "not_built").length;

  return (
    <div className="px-8 py-8 max-w-7xl mx-auto">
      {/* ── Page Header ───────────────────────────────────── */}
      <header className="mb-8 animate-fade-in-up">
        <h1 className="text-3xl font-bold tracking-tight">
          <span className="gradient-text">Mission Control</span>
        </h1>
        <p className="text-text-secondary mt-1.5 text-sm">
          Real-time overview of all Nexus Engine agents and systems.
        </p>
      </header>

      {/* ── Connection Banner ─────────────────────────────── */}
      {error && (
        <div className="mb-6 glass-card p-4 border-accent-rose/30 animate-fade-in-up">
          <div className="flex items-center gap-3">
            <span className="text-accent-rose text-lg">⚠</span>
            <div>
              <p className="text-sm font-medium text-accent-rose">
                Engine Offline
              </p>
              <p className="text-xs text-text-muted mt-0.5">
                {error} — Is the FastAPI backend running on port 8000?
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ── Stat Summary ──────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8 stagger-grid">
        <StatCard
          label="Engine Status"
          value={health ? "Online" : loading ? "..." : "Offline"}
          icon={health ? "🟢" : loading ? "⏳" : "🔴"}
          accentColor={health ? "accent-emerald" : "accent-rose"}
          subtitle={health ? `v${health.version}` : undefined}
        />
        <StatCard
          label="Active Agents"
          value={loading ? "..." : `${activeAgents} / ${totalAgents}`}
          icon="🤖"
          accentColor="accent-cyan"
          subtitle={`${notBuilt} not yet built`}
        />
        <StatCard
          label="Pending HITL"
          value={loading ? "..." : pendingHitlCount}
          icon="🔒"
          accentColor="accent-amber"
          subtitle="Decisions awaiting review"
        />
        <StatCard
          label="Errors"
          value={
            loading
              ? "..."
              : agents.reduce((sum, a) => sum + a.error_count, 0)
          }
          icon="🛡️"
          accentColor="accent-violet"
          subtitle="Total across all agents"
        />
      </div>

      {/* ── Agent Fleet Grid ───────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-text-primary">
              Agent Fleet
            </h2>
            <span className="text-xs text-text-muted">
              ({agents.length} registered)
            </span>
          </div>
          <button
            type="button"
            onClick={() => setIsFleetCollapsed((prev) => !prev)}
            className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors flex items-center gap-1.5 text-xs font-medium"
            title={isFleetCollapsed ? "Expand Agent Fleet" : "Collapse Agent Fleet"}
            aria-expanded={!isFleetCollapsed}
          >
            <span>{isFleetCollapsed ? "Show fleet" : "Collapse"}</span>
            <svg
              className={`w-3.5 h-3.5 transition-transform duration-200 ${isFleetCollapsed ? "-rotate-90" : "rotate-0"}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>

        {!isFleetCollapsed && (
          loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {[...Array(6)].map((_, i) => (
                <div
                  key={i}
                  className="glass-card p-5 h-28 animate-pulse"
                />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 stagger-grid">
              {agents.map((agent) => (
                <AgentCard key={agent.name} agent={agent} />
              ))}
            </div>
          )
        )}
      </section>

      {/* ── Quick Actions Launcher Menu ───────────────────── */}
      <section className="mt-8 animate-fade-in-up" style={{ animationDelay: "0.4s" }}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-text-primary">
            Quick Actions
          </h2>
          <button
            type="button"
            onClick={() => setIsActionsCollapsed((prev) => !prev)}
            className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-surface transition-colors flex items-center gap-1.5 text-xs font-medium"
            title={isActionsCollapsed ? "Expand Quick Actions menu" : "Collapse Quick Actions menu"}
            aria-expanded={!isActionsCollapsed}
          >
            <span>{isActionsCollapsed ? "Show actions" : "Collapse"}</span>
            <svg
              className={`w-3.5 h-3.5 transition-transform duration-200 ${isActionsCollapsed ? "-rotate-90" : "rotate-0"}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>

        {!isActionsCollapsed && (
          <div className="flex flex-wrap gap-3">
            <Link
              href="/hitl"
              className="glass-card px-5 py-3 text-sm font-medium text-accent-amber hover:text-text-primary transition-colors flex items-center gap-2 border border-accent-amber/30"
            >
              <span>🔒</span> Review Queue ({pendingHitlCount})
            </Link>
            <a
              href="/ask"
              className="glass-card px-5 py-3 text-sm font-medium text-accent-cyan hover:text-text-primary transition-colors flex items-center gap-2"
            >
              <span>💬</span> Ask Brain
            </a>
            <button
              disabled
              className="glass-card px-5 py-3 text-sm font-medium text-text-muted opacity-40 cursor-not-allowed flex items-center gap-2"
            >
              <span>📋</span> Weekly Review
            </button>
            <button
              disabled
              className="glass-card px-5 py-3 text-sm font-medium text-text-muted opacity-40 cursor-not-allowed flex items-center gap-2"
            >
              <span>🔍</span> Audit Engine
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
