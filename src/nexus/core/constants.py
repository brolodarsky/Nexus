from pathlib import Path
# Literal: Constrains string arguments to an explicit compile-time set of allowed values
from typing import Literal
# BaseChatModel: Abstract base class shared by ChatGoogleGenerativeAI and ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
# ChatGoogleGenerativeAI: Official Google GenAI LangChain client that natively preserves Gemini 3+ `thought_signature`s
from langchain_google_genai import ChatGoogleGenerativeAI
# ChatOpenAI: LangChain client for OpenAI chat models
from langchain_openai import ChatOpenAI
from nexus.core.config import settings

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


# `tier: ModelTier` selects the capability/cost level (`"low"`, `"medium"`, or `"strong"`).
# `-> BaseChatModel` returns a configured LangChain chat model (`ChatGoogleGenerativeAI` or `ChatOpenAI`) ready for `.invoke()` or `.bind_tools()`.
def get_chat_model(tier: ModelTier = "medium", temperature: float = 0.0) -> BaseChatModel:
    """Instantiate a tiered chat model routed to either native Gemini (`ChatGoogleGenerativeAI`) or OpenAI (`ChatOpenAI`).

    Why native `ChatGoogleGenerativeAI` instead of `ChatOpenAI` over `/v1beta/openai/`:
      Gemini 3+ thinking models attach encrypted `thought_signature` tokens to `functionCall` and text parts.
      `ChatOpenAI` strips `extra_content.google.thought_signature` when serializing tool-call history, causing
      HTTP 400 `INVALID_ARGUMENT` on step 2 of tool loops. `ChatGoogleGenerativeAI` natively stores and replays
      `__gemini_function_call_thought_signatures__` in `AIMessage.additional_kwargs` and handles cross-model history.
    """
    provider = settings.ai_provider.strip().lower()
    use_gemini = provider == "gemini" or (provider == "auto" and bool(GEMINI_API_KEY))

    if use_gemini and GEMINI_API_KEY:
        gemini_tier_map: dict[str, str] = {
            "low": GEMINI_MODEL_LOW,
            "medium": GEMINI_MODEL_MEDIUM,
            "strong": GEMINI_MODEL_STRONG,
        }
        model_name = gemini_tier_map.get(tier, GEMINI_MODEL_MEDIUM)
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=GEMINI_API_KEY,
            temperature=temperature,
        )

    # OpenAI tier map: `"low"` uses mini for fast/cheap subagent & summarizer work; `"medium"` / `"strong"` for synthesis
    openai_tier_map: dict[str, str] = {
        "low": AI_MODEL_LOW,
        "medium": AI_MODEL_MEDIUM,
        "strong": AI_MODEL_STRONG,
    }
    model_name = openai_tier_map.get(tier, AI_MODEL_MEDIUM)
    # `gpt-5.6-*` models accept `reasoning_effort="none"` for deterministic low-latency tool calling
    if tier in ("medium", "strong"):
        return ChatOpenAI(model=model_name, temperature=temperature, reasoning_effort="none")
    return ChatOpenAI(model=model_name, temperature=temperature)


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
