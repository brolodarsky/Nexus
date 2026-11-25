import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

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
    # Default Gemini model identifiers mapped to the 3 capability tiers when running on the Gemini provider
    # `"low"` and `"medium"` default to ultra-low-cost `gemini-3.8-flash` (subagents, titling, fast turns),
    # while `gemini-4-hydrogen` remains selectable as an explicit model option in the Chat UI.
    gemini_model_low: str = "gemini-3.8-flash"
    gemini_model_medium: str = "gemini-3.8-flash"
    gemini_model_strong: str = "gemini-4-argon"
    # Default Anthropic Claude model identifiers mapped to capability tiers (`claude-opus-5-5` strong, `claude-sonnet-5-5` medium, `claude-haiku-5-5` low)
    anthropic_model_low: str = "claude-haiku-5-5"
    anthropic_model_medium: str = "claude-sonnet-5-5"
    anthropic_model_strong: str = "claude-opus-5-5"
    # Default tier selection (`"low"`, `"medium"`, or `"strong"`) for the parent NexusAgent vs. spawned subagents
    # Primary agent defaults to `"strong"` (Gemini 4 Argon / `gemini-4-argon`) while subagents default to `"low"` (`gemini-3.8-flash`)
    nexus_primary_tier: str = "strong"
    nexus_subagent_tier: str = "low"
    # Provider Request Timeout & Retries:
    # - ai_request_timeout: HTTP request timeout in seconds (default 300s / 5 minutes) passed to provider chat clients.
    #   Deep reasoning models (`gemini-4-argon` / thinking mode) require ample headroom for complex multi-turn synthesis.
    # - ai_max_retries: Maximum automatic retry attempts on transient HTTP/gRPC errors (e.g. 504 DEADLINE_EXCEEDED, 429, 503).
    # - ai_include_thoughts: Enables visible thought/reasoning summaries for Gemini (`include_thoughts=True`) and Anthropic
    #   adaptive thinking models (`thinking={"type": "adaptive", "display": "summarized"}`) for audit & Thinking Panel visibility.
    # - anthropic_thinking_max_tokens: Explicit `max_tokens` floor when Anthropic adaptive thinking is active so reasoning
    #   tokens do not starve final text/tool output against LangChain's 4096 fallback ceiling on newer Claude 5.5 profiles.
    ai_request_timeout: int = 300
    ai_max_retries: int = 3
    ai_include_thoughts: bool = True
    anthropic_thinking_max_tokens: int = 16384
    # Wall-clock execution timeouts (seconds) preventing hung external sockets/APIs from freezing worker threads:
    # - nexus_tool_timeout: Maximum wait for a single non-subagent tool batch (e.g. fetch_emails, web_search, CLI tools).
    # - nexus_subagent_timeout: Maximum total wall-clock budget for a single `spawn_subagent` worker loop.
    nexus_tool_timeout: int = 120
    nexus_subagent_timeout: int = 900
    # Subagent ReAct loop circuit breakers (`spawn_subagent` in `src/nexus/agent/graph.py`):
    # - subagent_max_turns: Maximum tool-calling iterations before forcing a final tool-free synthesis turn.
    # - subagent_max_input_tokens: Cumulative input-token ceiling per subagent run to prevent TPM exhaustion and fallback spikes.
    subagent_max_turns: int = 12
    subagent_max_input_tokens: int = 400_000
    tavily_api_key: Optional[str] = None
    
    # Gmail: auth lives in .secrets/token_gmail*.json (see shared_tools/gmail_engine.py); supports multiple accounts.

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

    # LangSmith Tracing
    langchain_tracing_v2: Optional[str] = None
    langchain_project: Optional[str] = None
    langchain_api_key: Optional[str] = None

    class Config:
        import os
        from pathlib import Path
        env_file = str(Path(__file__).resolve().parent.parent.parent.parent / ".env")
        extra = "ignore"

settings = EngineSettings()
