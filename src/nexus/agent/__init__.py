"""
nexus.agent — Single Universal Agent (`NexusAgent`) for the Nexus Engine.
"""
from nexus.agent.api import (
    ask_nexus,
    execute_vault_query,
    route_content,
    run_nexus_agent,
    run_nexus_agent_with_trace,
)
from nexus.agent.graph import nexus_graph, nexus_tracer

__all__ = [
    "ask_nexus",
    "execute_vault_query",
    "route_content",
    "run_nexus_agent",
    "run_nexus_agent_with_trace",
    "nexus_graph",
    "nexus_tracer",
]
