import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
# Privacy-first default (`S5`): prevent LangChain SDK from implicitly shipping private Vault/email prompts
# to external LangSmith cloud servers unless `LANGCHAIN_TRACING_V2=true` is explicitly opted in.
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")


class EngineSettings(BaseSettings):
    nexus_user_name: str = "User"
    
    # AI & Search
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-6-luna"
    # Gemini API credentials & provider routing:
    # - gemini_api_key / google_api_key: Optional API key from Google AI Studio (`GEMINI_API_KEY` or `GOOGLE_API_KEY` in `.env`)
    # - anthropic_api_key: Optional API key from Anthropic Console (`ANTHROPIC_API_KEY` in `.env`)
    # - ai_provider: `"auto"` (uses Gemini if a Gemini key is configured, else Anthropic if configured, else OpenAI), `"gemini"`, `"anthropic"`, or `"openai"`
    gemini_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    ai_provider: str = "auto"
    # Default Gemini model identifiers mapped symmetrically across all 3 capability tiers:
    # - `"low"` (`gemini-3.8-flash`): Fast, low-cost subagents, mobile queries, and lightweight extraction.
    # - `"medium"` (`gemini-4-hydrogen`): Everyday interactive Commander default (flat 1M rate, 23.6s avg latency).
    # - `"strong"` (`gemini-4-argon`): Frontier reasoning reserved for explicit escalation or `1× Boost` turns.
    gemini_model_low: str = "gemini-3.8-flash"
    gemini_model_medium: str = "gemini-4-hydrogen"
    gemini_model_strong: str = "gemini-4-argon"
    # Default Anthropic Claude model identifiers mapped to capability tiers (`claude-opus-5-5` strong, `claude-sonnet-5-5` medium, `claude-haiku-5-5` low)
    anthropic_model_low: str = "claude-haiku-5-5"
    anthropic_model_medium: str = "claude-sonnet-5-5"
    anthropic_model_strong: str = "claude-opus-5-5"
    # Default tier selection (`"low"`, `"medium"`, or `"strong"`) for the parent NexusAgent vs. spawned subagents:
    # Primary Commander defaults to `"medium"` (`gemini-4-hydrogen` / `claude-sonnet-5-5`), while subagents default to `"low"`.
    nexus_primary_tier: str = "medium"
    nexus_subagent_tier: str = "low"
    # Subagent Tier Clamp (`C3`): prevents Head Agent turns from fanning out expensive `"strong"` workers by default.
    # Override via `NEXUS_ALLOW_STRONG_SUBAGENTS=true` in `.env` when deep multi-worker Opus/Argon synthesis is needed.
    nexus_allow_strong_subagents: bool = False
    # Per-Tier HTTP Request Timeouts & SDK Retries:
    # Splitting timeouts by tier gives `"strong"` reasoning models (`180s`, `1` retry) headroom over deep context
    # windows while making `"medium"`/`"low"` calls fail fast (`60s`, `2` retries) instead of stalling 20 minutes on hung sockets.
    # Optional `AI_REQUEST_TIMEOUT` / `AI_MAX_RETRIES` overrides in `.env` take precedence across all tiers when set.
    ai_timeout_strong: int = 180
    ai_max_retries_strong: int = 1
    ai_timeout_default: int = 60
    ai_max_retries_default: int = 2
    ai_request_timeout: Optional[int] = None
    ai_max_retries: Optional[int] = None
    ai_include_thoughts: bool = True
    anthropic_thinking_max_tokens: int = 16384
    # Wall-clock execution timeouts (seconds) preventing hung external sockets/APIs from freezing worker threads:
    # - nexus_tool_timeout: Maximum wait for a single non-subagent tool batch (e.g. fetch_emails, web_search, CLI tools).
    # - nexus_subagent_timeout: Maximum total wall-clock budget for a single `spawn_subagent` worker loop.
    nexus_tool_timeout: int = 120
    nexus_subagent_timeout: int = 900
    # Subagent ReAct loop circuit breakers (`spawn_subagent` in `src/nexus/agent/subagent.py`):
    # Both fields live on `EngineSettings` (`pydantic_settings.BaseSettings`) and can be overridden in `.env`
    # via `SUBAGENT_MAX_TURNS` and `SUBAGENT_MAX_UNCACHED_INPUT_TOKENS`.
    # - subagent_max_turns: Maximum tool-calling iterations before forcing a final synthesis turn (soft notice at max_turns - 2).
    # - subagent_max_uncached_input_tokens: Cumulative *uncached* input-token ceiling (`input_tokens - cached_tokens`) per
    #   subagent run so KV-cached turns and `context_files` pre-hydration are not penalized while context bloat and broken-cache
    #   spirals remain bounded (soft notice at 80%).
    subagent_max_turns: int = 25
    subagent_max_uncached_input_tokens: int = 450_000
    tavily_api_key: Optional[str] = None
    
    # Gmail: auth lives in .secrets/token_gmail*.json (see shared_tools/gmail_engine.py); supports multiple accounts.

    # Control Panel API Security (`S6` — `src/nexus/api/security.py`):
    # - nexus_api_token: Optional static Bearer/X-Nexus-Token override (`NEXUS_API_TOKEN` in `.env`).
    #   When empty, `get_or_create_api_token()` generates and persists a 32-byte URL-safe secret in `.secrets/api_token`.
    # - nexus_localhost_only: When `True` (`NEXUS_LOCALHOST_ONLY=true`), rejects non-loopback `Host` headers and remote LAN/Tailscale peers.
    nexus_api_token: str = ""
    nexus_localhost_only: bool = False

    # Telegram Mobile Voice & Notification Bridge (`src/nexus/shared_tools/telegram_bridge.py`):
    # - telegram_bot_token: Optional Bot API token from @BotFather (`TELEGRAM_BOT_TOKEN` in `.env`).
    # - telegram_allowed_user_id: Optional numeric Telegram User ID (`TELEGRAM_ALLOWED_USER_ID` in `.env`) authorized to invoke
    #   NexusAgent. If omitted on first launch, the bridge automatically enrolls and locks onto the first user who messages the bot.
    # - telegram_default_tier: Default capability tier (`"low"`, `"medium"`, or `"strong"`) used for mobile turns unless overridden via `/fast` or `/strong`. Defaults to `"low"` for fast sub-second mobile turns.
    # - telegram_enabled: Master toggle (`True` by default) controlling automatic background long-polling during FastAPI startup.
    telegram_bot_token: Optional[str] = None
    telegram_allowed_user_id: Optional[str] = None
    telegram_default_tier: str = "low"
    telegram_enabled: bool = True

    # LangSmith Tracing (opt-in only; local SQLite telemetry in `logs/chats.db` supersedes external prompt shipping)
    langchain_tracing_v2: str = "false"
    langchain_project: Optional[str] = None
    langchain_api_key: Optional[str] = None

    class Config:
        import os
        from pathlib import Path
        env_file = str(Path(__file__).resolve().parent.parent.parent.parent / ".env")
        extra = "ignore"

settings = EngineSettings()

# Module-level guard ensuring the LangSmith privacy warning logs at most once per process startup
_langsmith_warned = False


def is_langsmith_tracing_enabled() -> bool:
    """Return True only when external LangSmith tracing (`LANGCHAIN_TRACING_V2`) is explicitly enabled."""
    raw = os.environ.get("LANGCHAIN_TRACING_V2")
    if raw is None:
        raw = EngineSettings().langchain_tracing_v2
    return str(raw or "").strip().lower() in ("true", "1", "yes")


def warn_if_langsmith_enabled() -> bool:
    """Emit a prominent one-time startup privacy warning if external LangSmith cloud tracing is active."""
    global _langsmith_warned
    if not is_langsmith_tracing_enabled():
        return False
    if not _langsmith_warned:
        _langsmith_warned = True
        from nexus.core.logger import logger

        logger.warning(
            "PRIVACY WARNING: LANGCHAIN_TRACING_V2 is enabled — full prompts, Vault notes, health/financial records, "
            "and email payloads are being sent to external LangSmith servers. Set LANGCHAIN_TRACING_V2=false in .env "
            "unless actively debugging."
        )
    return True
