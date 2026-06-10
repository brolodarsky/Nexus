from typing import Optional
from pydantic_settings import BaseSettings

class EngineSettings(BaseSettings):
    nexus_user_name: str = "User"
    
    # AI & Search
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini-2024-07-18"
    tavily_api_key: Optional[str] = None
    
    # Telegram Interface
    telegram_bot_token: Optional[str] = None
    allowed_user_ids: str = ""
    
    # Email Agent
    email_address: Optional[str] = None
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993
    imap_folder: str = "INBOX"

    # LangSmith Tracing
    langchain_tracing_v2: Optional[str] = None
    langchain_project: Optional[str] = None
    langchain_api_key: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = EngineSettings()
