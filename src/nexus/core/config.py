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
    openai_model: str = "gpt-4o-mini-2024-07-18"
    tavily_api_key: Optional[str] = None
    
    # Telegram Interface
    telegram_bot_token: Optional[str] = None
    allowed_user_ids: str = ""
    
    # Gmail: auth lives in .secrets/token_gmail.json (see shared_tools/gmail_engine.py); no env config needed.

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
