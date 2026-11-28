"""
logger.py — Centralized Structured Logging System for the Nexus Engine.
Configures Loguru sinks for styled console output and rotated file persistence (logs/engine.log).
"""
import os
# sys: Provides access to standard output/error streams (sys.stdout, sys.stderr)
import sys
# Path: Object-oriented filesystem path manipulation for locating log files
from pathlib import Path

# loguru.logger: Third-party zero-boilerplate logging framework with automatic exception formatting
from loguru import logger

# Root log directory at project root: logs/
LOG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
ENGINE_LOG_FILE = LOG_DIR / "engine.log"

def setup_logger():
    """
    Configures Loguru handlers (sinks) for the Nexus Engine runtime:
    1. Console Sink: Formatted, colorized terminal stream for real-time developer feedback
       (routed to stderr when `NEXUS_STDIO_MCP=1` so stdio JSON-RPC frames stay uncorrupted).
    2. File Sink: Rotated, persistent JSON/text file log at logs/engine.log for post-mortem audits.
    """
    # Remove default unconfigured handler to prevent duplicate log outputs
    logger.remove()

    # When running as a stdio MCP server, stdout is exclusively reserved for JSON-RPC frames.
    use_stderr = os.environ.get("NEXUS_STDIO_MCP", "").strip().lower() in ("1", "true", "yes")
    console_stream = sys.stderr if use_stderr else sys.stdout

    # On Windows, ensure console stream uses utf-8 with replacement to prevent charmap UnicodeEncodeErrors on emojis
    if hasattr(console_stream, "reconfigure"):
        try:
            console_stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # 1. Console Handler: Color-coded output for terminal sessions (or stderr under stdio MCP)
    logger.add(
        console_stream,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=not use_stderr,
    )

    # 2. File Handler (engine.log): Rotated log sink with thread-safe async queueing
    logger.add(
        ENGINE_LOG_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",       # Rotate to a new file once log reaches 10 MB
        retention="10 days",     # Automatically purge logs older than 10 days
        compression="zip",      # Compress archived logs to save disk space
        enqueue=True,           # Thread-safe async logging across FastAPI & LangGraph threads
        encoding="utf-8",
    )
    return logger

# Initialize global singleton logger instance
engine_logger = setup_logger()

# Export 'logger' as primary alias
__all__ = ["logger", "engine_logger"]
