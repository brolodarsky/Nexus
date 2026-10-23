from pathlib import Path
# Literal: Constrains string arguments to an explicit compile-time set of allowed values
from typing import Literal
# BaseChatModel: Abstract base class shared by ChatGoogleGenerativeAI and ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
# ChatGoogleGenerativeAI: Official Google GenAI LangChain client that natively preserves Gemini 3+ `thought_signature`s
from langchain_google_genai import ChatGoogleGenerativeAI
# ChatOpenAI: LangChain client for OpenAI chat models
from langchain_openai import ChatOpenAI
from nexus.core.config import EngineSettings, settings

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
VAULT_PATH = PROJECT_ROOT / "Vault"

# AI Config — OpenAI Model Tiers
OPENAI_API_KEY = settings.openai_api_key
AI_MODEL_LOW = "gpt-5.4-mini"
AI_MODEL_MEDIUM = "gpt-5.6-terra"
AI_MODEL_STRONG = "gpt-5.6-sol"

# AI Config — Google Gemini Native Client & Model Tiers
# Resolves either `GEMINI_API_KEY` or `GOOGLE_API_KEY` from `.env`
GEMINI_API_KEY = settings.gemini_api_key or settings.google_api_key
GEMINI_MODEL_LOW = settings.gemini_model_low
GEMINI_MODEL_MEDIUM = settings.gemini_model_medium
GEMINI_MODEL_STRONG = settings.gemini_model_strong

# Type alias defining the three standardized reasoning/cost tiers across providers
ModelTier = Literal["low", "medium", "strong"]


# `tier: ModelTier | None` selects the capability/cost level (`"low"`, `"medium"`, or `"strong"`). If `None`, reads `nexus_primary_tier` fresh from `.env`.
# `-> BaseChatModel` returns a configured LangChain chat model (`ChatGoogleGenerativeAI` or `ChatOpenAI`) ready for `.invoke()` or `.bind_tools()`.
def get_chat_model(tier: ModelTier | None = None, temperature: float = 0.0) -> BaseChatModel:
    """Instantiate a tiered chat model routed to either native Gemini (`ChatGoogleGenerativeAI`) or OpenAI (`ChatOpenAI`).

    Re-reads `EngineSettings()` dynamically so `.env` model/tier edits take effect on the very next turn without
    needing to edit `.py` files (which would cause `uvicorn --reload` to kill in-flight HTTP/SSE streams).
    """
    live_settings = EngineSettings()
    # Resolve configurable HTTP timeout (default 180s) and max retry count (default 3) from `.env`
    # Reasoning models (`gemini-4-argon`) require >90s on massive context histories to prevent 504 DEADLINE_EXCEEDED
    timeout = live_settings.ai_request_timeout
    max_retries = live_settings.ai_max_retries

    effective_tier: str = tier or live_settings.nexus_primary_tier
    if effective_tier not in ("low", "medium", "strong"):
        effective_tier = "medium"

    provider = live_settings.ai_provider.strip().lower()
    gemini_key = live_settings.gemini_api_key or live_settings.google_api_key or GEMINI_API_KEY
    use_gemini = provider == "gemini" or (provider == "auto" and bool(gemini_key))

    if use_gemini and gemini_key:
        gemini_tier_map: dict[str, str] = {
            "low": live_settings.gemini_model_low,
            "medium": live_settings.gemini_model_medium,
            "strong": live_settings.gemini_model_strong,
        }
        model_name = gemini_tier_map.get(effective_tier, live_settings.gemini_model_medium)
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=gemini_key,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )

    # OpenAI tier map: `"low"` uses mini for fast/cheap subagent & summarizer work; `"medium"` / `"strong"` for synthesis
    openai_tier_map: dict[str, str] = {
        "low": AI_MODEL_LOW,
        "medium": AI_MODEL_MEDIUM,
        "strong": AI_MODEL_STRONG,
    }
    model_name = openai_tier_map.get(effective_tier, AI_MODEL_MEDIUM)
    # `gpt-5.6-*` models accept `reasoning_effort="none"` for deterministic low-latency tool calling
    if effective_tier in ("medium", "strong"):
        return ChatOpenAI(model=model_name, temperature=temperature, reasoning_effort="none", timeout=timeout, max_retries=max_retries)
    return ChatOpenAI(model=model_name, temperature=temperature, timeout=timeout, max_retries=max_retries)


# Shared Config
IGNORE_DIRS = {
    "Audio",
    ".trash",
    ".obsidian",
    ".stfolder",
    ".vscode",
    "Memories_Log_Images",
    "Pilot Diagrams",
    "node_modules",
    "__pycache__",
    ".venv",
    ".git",
}
