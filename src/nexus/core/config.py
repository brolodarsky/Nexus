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
    nexus_primary_tier: str = "medium"
    nexus_subagent_tier: str = "low"
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
