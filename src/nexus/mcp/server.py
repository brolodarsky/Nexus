"""
server.py — Unified FastMCP Server for the Nexus Agentic Engine.

Exposes the exact same canonical tool registry (`nexus.agent.graph.TOOLS`) used in-process
by `NexusAgent`, eliminating the split between internal bound tools and standalone CLI scripts.
All tool invocations redirect stray `stdout` output to `stderr` and configure Loguru to log
exclusively to `stderr` when running over `stdio`, keeping MCP JSON-RPC frames clean.
"""
import argparse
import contextlib
import functools
import os
import sys
from typing import Any, Callable, Optional, Sequence

# Disable interactive OAuth popup flows inside headless MCP tool execution
os.environ.setdefault("NEXUS_NONINTERACTIVE_AUTH", "1")
# When invoked directly (`python -m nexus.mcp.server`), protect stdio before importing Nexus modules
if __name__ == "__main__":
    os.environ.setdefault("NEXUS_STDIO_MCP", "1")

from langchain_core.tools import BaseTool
from mcp.server.fastmcp import FastMCP

from nexus.agent.graph import TOOLS
from nexus.core.engine_constitution import inject_root_instructions
from nexus.core.hitl_queue import (
    get_hitl_execution_context,
    reset_hitl_execution_context,
    set_hitl_execution_context,
)
from nexus.core.logger import setup_logger

# Create the unified FastMCP server instance exposing all Nexus capabilities
mcp = FastMCP(
    "nexus",
    instructions=(
        "Unified Nexus Agentic Engine, Obsidian Vault, HITL queue, Gmail, Google Calendar, "
        "Chrome Browser Bridge, Tavily web search, YouTube/media transcription, and portfolio tools."
    ),
)


# Signature breakdown:
# - mcp_server: FastMCP instance onto which the LangChain tool is registered.
# - lc_tool: LangChain `BaseTool` (created via `@tool`) whose underlying `.func`, `.name`, and `.description`
#            are wrapped and exposed as an MCP tool with identical parameter schemas.
def _register_langchain_tool(mcp_server: FastMCP, lc_tool: BaseTool) -> None:
    """Wrap a LangChain `@tool` function for stdio-safe, context-aware execution in FastMCP."""
    raw_fn: Optional[Callable[..., Any]] = getattr(lc_tool, "func", None)
    if raw_fn is None:
        raise ValueError(f"Tool '{lc_tool.name}' has no underlying callable `.func` for MCP registration.")

    # `@functools.wraps(raw_fn)` copies `__name__`, `__annotations__`, `__signature__`, and `__defaults__`
    # so `FastMCP` generates the exact same JSON schema parameters as LangChain's `.bind_tools(TOOLS)`.
    @functools.wraps(raw_fn)
    def _mcp_wrapper(*args: Any, **kwargs: Any) -> Any:
        # Ensure an execution context exists so `conversation_cache` and `hitl_queue` scope cleanly per MCP session
        current_ctx = get_hitl_execution_context()
        ctx_token = None
        if not current_ctx.get("conversation_id"):
            ctx_token = set_hitl_execution_context(
                conversation_id="mcp_session",
                thread_id="mcp_session",
                agent_id="mcp_client",
                agent_role="MCP Client",
            )
        try:
            # Redirect any stray `print()` calls inside underlying tool libraries to stderr so stdio JSON-RPC never corrupts
            with contextlib.redirect_stdout(sys.stderr):
                return raw_fn(*args, **kwargs)
        finally:
            if ctx_token is not None:
                reset_hitl_execution_context(ctx_token)

    mcp_server.add_tool(
        _mcp_wrapper,
        name=lc_tool.name,
        description=lc_tool.description,
    )


# Register every canonical tool in `TOOLS` once at module load for exact 1:1 parity with `NexusAgent`
for _tool in TOOLS:
    _register_langchain_tool(mcp, _tool)


@mcp.resource("nexus://instructions/master")
def master_instructions_resource() -> str:
    """Return the hydrated `Vault/Master Instructions.md` constitutional prompt."""
    return inject_root_instructions()


def main(argv: Optional[Sequence[str]] = None) -> None:
    """CLI entrypoint (`python -m nexus.mcp.server` or `nexus-mcp`)."""
    parser = argparse.ArgumentParser(description="Run the unified Nexus MCP server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP transport protocol (default: stdio).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.transport == "stdio":
        os.environ["NEXUS_STDIO_MCP"] = "1"
        setup_logger()

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
