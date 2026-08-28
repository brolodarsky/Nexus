"""
logger.py — Centralized Structured Logging System for the Nexus Engine.
Configures Loguru sinks for styled console output and rotated file persistence (logs/engine.log).
"""
# sys: Provides access to standard output streams (sys.stdout, sys.stderr)
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
    1. Console Sink: Formatted, colorized terminal stream for real-time developer feedback.
    2. File Sink: Rotated, persistent JSON/text file log at logs/engine.log for post-mortem audits.
    """
    # Remove default unconfigured handler to prevent duplicate log outputs
    logger.remove()

    # 1. Console Handler (stdout): Color-coded output for terminal sessions
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
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
