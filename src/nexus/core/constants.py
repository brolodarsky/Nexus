from pathlib import Path
# Literal: Constrains string arguments to an explicit compile-time set of allowed values
# Any: Allows heterogeneous dictionary value types in model catalog metadata responses
from typing import Any, Literal
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


# `tier: str | None` accepts a standardized tier (`"low"`, `"medium"`, `"strong"`) or an explicit model ID (e.g. `"gemini-4-argon"`).
# `-> dict[str, str]` returns resolved metadata (`tier`, `provider`, `model_name`, `label`) for telemetry and client instantiation.
def resolve_model_config(tier: str | None = None) -> dict[str, str]:
    """Resolve a requested model tier or model identifier into concrete provider and model metadata.

    Re-reads `EngineSettings()` dynamically so `.env` edits and per-turn UI model selections apply immediately.
    """
    live_settings = EngineSettings()
    provider_setting = live_settings.ai_provider.strip().lower()
    gemini_key = live_settings.gemini_api_key or live_settings.google_api_key or GEMINI_API_KEY
    use_gemini = provider_setting == "gemini" or (provider_setting == "auto" and bool(gemini_key))
    active_provider = "gemini" if (use_gemini and gemini_key) else "openai"

    gemini_tier_map: dict[str, str] = {
        "low": live_settings.gemini_model_low,
        "medium": live_settings.gemini_model_medium,
        "strong": live_settings.gemini_model_strong,
    }
    openai_tier_map: dict[str, str] = {
        "low": AI_MODEL_LOW,
        "medium": AI_MODEL_MEDIUM,
        "strong": AI_MODEL_STRONG,
    }
    active_map = gemini_tier_map if active_provider == "gemini" else openai_tier_map

    # Normalize requested tier/model; fall back to `nexus_primary_tier` from `.env` when omitted
    raw_choice = (tier or "").strip()
    lower_choice = raw_choice.lower()
    default_tier = live_settings.nexus_primary_tier if live_settings.nexus_primary_tier in ("low", "medium", "strong") else "strong"

    if not raw_choice or lower_choice in ("default", "auto"):
        effective_tier = default_tier
        model_name = active_map[effective_tier]
    elif lower_choice in ("low", "medium", "strong"):
        effective_tier = lower_choice
        model_name = active_map[effective_tier]
    else:
        # Caller passed an explicit model name (e.g. `"gemini-3.8-flash"` or `"gemini-4-argon"`):
        # reverse-lookup its tier if it matches a configured tier, else treat as custom `"strong"`/`"low"` based on name
        matched_tier = next((t for t, m in active_map.items() if m.lower() == lower_choice), None)
        effective_tier = matched_tier or ("low" if "flash" in lower_choice or "mini" in lower_choice else "strong")
        model_name = raw_choice

    tier_Wait_labels = {
        "strong": f"Strong · {model_name}",
        "medium": f"Medium · {model_name}",
        "low": f"Fast · {model_name}",
    }
    return {
        "tier": effective_tier,
        "provider": active_provider,
        "model_name": model_name,
        "label": tier_Wait_labels.get(effective_tier, model_name),
    }


# `-> dict[str, Any]` returns the structured catalog of selectable models/tiers for the Next.js Chat UI (`GET /api/agents/models`).
def get_available_models() -> dict[str, Any]:
    """Return the active provider, default tier, and selectable per-turn model options for the Chat UI."""
    live_settings = EngineSettings()
    default_resolved = resolve_model_config(None)
    strong_cfg = resolve_model_config("strong")
    medium_cfg = resolve_model_config("medium")
    low_cfg = resolve_model_config("low")

    models: list[dict[str, str]] = [
        {
            "id": "strong",
            "tier": "strong",
            "model_name": strong_cfg["model_name"],
            "label": f"Strong ({strong_cfg['model_name']})",
            "short_label": "Strong",
            "description": f"Deep reasoning & complex synthesis — Astra ({strong_cfg['model_name']})",
        },
        {
            "id": "low",
            "tier": "low",
            "model_name": low_cfg["model_name"],
            "label": f"Fast ({low_cfg['model_name']})",
            "short_label": "Fast",
            "description": f"High-speed, low-cost execution — Flash ({low_cfg['model_name']})",
        },
    ]

    # Include the `"medium"` tier option if it maps to a distinct model from `"low"` and `"strong"`,
    # or if `nexus_primary_tier` is explicitly set to `"medium"` in `.env`.
    if (
        medium_cfg["model_name"] not in (strong_cfg["model_name"], low_cfg["model_name"])
        or live_settings.nexus_primary_tier == "medium"
    ):
        models.insert(
            1,
            {
                "id": "medium",
                "tier": "medium",
                "model_name": medium_cfg["model_name"],
                "label": f"Medium ({medium_cfg['model_name']})",
                "short_label": "Medium",
                "description": f"Balanced speed & reasoning ({medium_cfg['model_name']})",
            },
        )

    return {
        "default_tier": default_resolved["tier"],
        "default_model": default_resolved["model_name"],
        "provider": default_resolved["provider"],
        "models": models,
    }


# `tier: ModelTier | str | None` selects the capability/cost level (`"low"`, `"medium"`, `"strong"`, or explicit model ID). If `None`, reads `nexus_primary_tier` fresh from `.env`.
# `-> BaseChatModel` returns a configured LangChain chat model (`ChatGoogleGenerativeAI` or `ChatOpenAI`) ready for `.invoke()` or `.bind_tools()`.
def get_chat_model(tier: ModelTier | str | None = None, temperature: float = 0.0) -> BaseChatModel:
    """Instantiate a tiered chat model routed to either native Gemini (`ChatGoogleGenerativeAI`) or OpenAI (`ChatOpenAI`).

    Re-reads `EngineSettings()` dynamically so `.env` model/tier edits and per-turn UI model overrides take effect
    on the very next turn without needing to edit `.py` files (which would cause `uvicorn --reload` to kill in-flight HTTP/SSE streams).
    """
    live_settings = EngineSettings()
    # Resolve configurable HTTP timeout (default 300s) and max retry count (default 3) from `.env`
    # Reasoning models (`gemini-4-argon`) require >90s on massive context histories to prevent 504 DEADLINE_EXCEEDED
    timeout = live_settings.ai_request_timeout
    max_retries = live_settings.ai_max_retries

    resolved = resolve_model_config(tier)
    effective_tier = resolved["tier"]
    model_name = resolved["model_name"]
    gemini_key = live_settings.gemini_api_key or live_settings.google_api_key or GEMINI_API_KEY

    if resolved["provider"] == "gemini" and gemini_key:
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=gemini_key,
            temperature=temperature,
            timeout=timeout,
            max_retries=max_retries,
        )

    # OpenAI tier map: `"low"` uses mini for fast/cheap subagent & summarizer work; `"medium"` / `"strong"` for synthesis
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
