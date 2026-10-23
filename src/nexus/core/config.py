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
    # - ai_provider: `"auto"` (uses Gemini if a Gemini key is configured, else OpenAI), `"gemini"`, or `"openai"`
    gemini_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    ai_provider: str = "auto"
    # Default Gemini model identifiers mapped to the 3 capability tiers when running on the Gemini provider
    gemini_model_low: str = "gemini-3.8-flash"
    gemini_model_medium: str = "gemini-3.8-flash"
    gemini_model_strong: str = "gemini-4-argon"
    # Default tier selection (`"low"`, `"medium"`, or `"strong"`) for the parent NexusAgent vs. spawned subagents
    # Primary agent defaults to `"strong"` (Astra / `gemini-4-argon`) while subagents default to `"low"` (`gemini-3.8-flash`)
    nexus_primary_tier: str = "strong"
    nexus_subagent_tier: str = "low"
    # Provider Request Timeout & Retries:
    # - ai_request_timeout: HTTP request timeout in seconds (default 300s / 5 minutes) passed to provider chat clients.
    #   Deep reasoning models (`gemini-4-argon` / thinking mode) require ample headroom for complex multi-turn synthesis.
    # - ai_max_retries: Maximum automatic retry attempts on transient HTTP/gRPC errors (e.g. 504 DEADLINE_EXCEEDED, 429, 503).
    ai_request_timeout: int = 300
    ai_max_retries: int = 3
    tavily_api_key: Optional[str] = None
    
    # Telegram Interface
    telegram_bot_token: Optional[str] = None
    allowed_user_ids: str = ""
    
    # Gmail: auth lives in .secrets/token_gmail*.json (see shared_tools/gmail_engine.py); supports multiple accounts.

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
