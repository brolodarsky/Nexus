from pathlib import Path
# Literal: Constrains string arguments to an explicit compile-time set of allowed values
# Any: Allows heterogeneous dictionary value types in model catalog metadata responses
from typing import Any, Literal
# BaseChatModel: Abstract base class shared by ChatGoogleGenerativeAI, ChatAnthropic, and ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
# ChatAnthropic: Official Anthropic Claude LangChain client supporting tool calling and prompt caching
from langchain_anthropic import ChatAnthropic
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

# AI Config — Anthropic Claude Native Client & Model Tiers
# Resolves `ANTHROPIC_API_KEY` from `.env`; maps Opus 5.5 to `strong` and Sonnet 4.5 to `low`
ANTHROPIC_API_KEY = settings.anthropic_api_key
ANTHROPIC_MODEL_LOW = settings.anthropic_model_low
ANTHROPIC_MODEL_MEDIUM = settings.anthropic_model_medium
ANTHROPIC_MODEL_STRONG = settings.anthropic_model_strong

# Type alias defining the three standardized reasoning/cost tiers across providers
ModelTier = Literal["low", "medium", "strong"]


# `model_id: str` is an incoming Anthropic model string (e.g. `"claude-opus-5.5"`, `"claude-opus-5-5"`, or `"claude-opus-4-5"`).
# `-> str` normalizes dot-separated version suffixes (`5.5`, `4.5`) into Anthropic's canonical hyphenated API format (`5-5`, `4-5`).
def _normalize_anthropic_model_name(model_id: str) -> str:
    """Normalize shorthand or dot-versioned Anthropic model strings into canonical Anthropic API identifiers."""
    cleaned = model_id.strip()
    lower = cleaned.lower()
    if lower in ("claude-opus-5.5", "opus-5.5", "opus-5-5", "opus 5.5"):
        return "claude-opus-5-5"
    if lower in ("claude-opus-4.5", "opus-4.5", "opus-4-5", "opus 4.5"):
        return "claude-opus-4-5"
    if lower in ("claude-sonnet-4.5", "sonnet-4.5", "sonnet-4-5", "sonnet 4.5"):
        return "claude-sonnet-4-5"
    return cleaned


# `tier: str | None` accepts a standardized tier (`"low"`, `"medium"`, `"strong"`), a provider-qualified tier (`"anthropic:strong"`),
# or an explicit model ID (e.g. `"gemini-4-argon"`, `"claude-opus-5-5"`, `"claude-sonnet-4-5"`).
# `provider: str | None` optionally overrides the target provider family (`"gemini"`, `"anthropic"`, `"openai"`), e.g. so subagents match the parent turn's provider.
# `-> dict[str, str]` returns resolved metadata (`tier`, `provider`, `model_name`, `label`) for telemetry and client instantiation.
def resolve_model_config(tier: str | None = None, provider: str | None = None) -> dict[str, str]:
    """Resolve a requested model tier or model identifier into concrete provider and model metadata.

    Re-reads `EngineSettings()` dynamically so `.env` edits and per-turn UI model selections apply immediately.
    """
    live_settings = EngineSettings()
    provider_setting = (provider or live_settings.ai_provider).strip().lower()
    gemini_key = live_settings.gemini_api_key or live_settings.google_api_key or GEMINI_API_KEY
    anthropic_key = live_settings.anthropic_api_key or ANTHROPIC_API_KEY

    # Determine default active provider when no explicit model/provider prefix overrides it
    if provider_setting == "anthropic":
        active_provider = "anthropic"
    elif provider_setting == "openai":
        active_provider = "openai"
    elif provider_setting == "gemini":
        active_provider = "gemini" if (gemini_key or provider) else "openai"
    else:
        # `"auto"` mode: prefer Gemini if key is present, else Anthropic if key is present, else OpenAI
        if gemini_key:
            active_provider = "gemini"
        elif anthropic_key:
            active_provider = "anthropic"
        else:
            active_provider = "openai"

    gemini_tier_map: dict[str, str] = {
        "low": live_settings.gemini_model_low,
        "medium": live_settings.gemini_model_medium,
        "strong": live_settings.gemini_model_strong,
    }
    anthropic_tier_map: dict[str, str] = {
        "low": _normalize_anthropic_model_name(live_settings.anthropic_model_low),
        "medium": _normalize_anthropic_model_name(live_settings.anthropic_model_medium),
        "strong": _normalize_anthropic_model_name(live_settings.anthropic_model_strong),
    }
    openai_tier_map: dict[str, str] = {
        "low": AI_MODEL_LOW,
        "medium": AI_MODEL_MEDIUM,
        "strong": AI_MODEL_STRONG,
    }
    provider_maps: dict[str, dict[str, str]] = {
        "gemini": gemini_tier_map,
        "anthropic": anthropic_tier_map,
        "openai": openai_tier_map,
    }

    # Normalize requested tier/model; fall back to `nexus_primary_tier` from `.env` when omitted
    raw_choice = (tier or "").strip()
    lower_choice = raw_choice.lower()
    default_tier = live_settings.nexus_primary_tier if live_settings.nexus_primary_tier in ("low", "medium", "strong") else "strong"

    # Support `"provider:tier"` composite selectors (e.g. `"anthropic:strong"`, `"anthropic:low"`, `"gemini:strong"`)
    if ":" in lower_choice:
        prefix_prov, suffix_tier = lower_choice.split(":", 1)
        if prefix_prov in provider_maps:
            active_provider = prefix_prov
            raw_choice = suffix_tier.strip()
            lower_choice = raw_choice.lower()

    active_map = provider_maps.get(active_provider, gemini_tier_map)

    if not raw_choice or lower_choice in ("default", "auto"):
        effective_tier = default_tier
        model_name = active_map[effective_tier]
    elif lower_choice in ("low", "medium", "strong"):
        effective_tier = lower_choice
        model_name = active_map[effective_tier]
    else:
        # Caller passed an explicit model name (e.g. `"gemini-3.8-flash"`, `"claude-opus-5-5"`, `"claude-sonnet-4-5"`):
        # 1. Detect provider from explicit model identifier if not explicitly overridden
        if any(tok in lower_choice for tok in ("claude", "opus", "sonnet", "haiku")):
            active_provider = "anthropic"
            raw_choice = _normalize_anthropic_model_name(raw_choice)
            lower_choice = raw_choice.lower()
        elif any(tok in lower_choice for tok in ("gemini", "argon")):
            active_provider = "gemini"
        elif any(tok in lower_choice for tok in ("gpt", "o1", "o3")):
            active_provider = "openai"

        active_map = provider_maps.get(active_provider, active_map)
        # 2. Reverse-lookup its tier if it matches a configured tier, else classify `"low"` vs `"strong"` by family name
        matched_tier = next((t for t, m in active_map.items() if m.lower() == lower_choice), None)
        is_fast_family = any(tok in lower_choice for tok in ("flash", "mini", "sonnet", "haiku"))
        effective_tier = matched_tier or ("low" if is_fast_family else "strong")
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
    anthropic_strong = _normalize_anthropic_model_name(live_settings.anthropic_model_strong)
    anthropic_low = _normalize_anthropic_model_name(live_settings.anthropic_model_low)

    models: list[dict[str, str]] = [
        {
            "id": "strong",
            "tier": "strong",
            "provider": strong_cfg["provider"],
            "model_name": strong_cfg["model_name"],
            "label": f"Strong ({strong_cfg['model_name']})",
            "short_label": "Strong",
            "description": f"Deep reasoning & complex synthesis — Astra ({strong_cfg['model_name']})",
        },
        {
            "id": "low",
            "tier": "low",
            "provider": low_cfg["provider"],
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
                "provider": medium_cfg["provider"],
                "model_name": medium_cfg["model_name"],
                "label": f"Medium ({medium_cfg['model_name']})",
                "short_label": "Medium",
                "description": f"Balanced speed & reasoning ({medium_cfg['model_name']})",
            },
        )

    # Append Anthropic Claude options (`claude-opus-5-5` for Strong, `claude-sonnet-4-5` for Low/Fast)
    # when the primary provider is not already Anthropic so all 4 options appear side-by-side in the Chat UI.
    if default_resolved["provider"] != "anthropic":
        models.extend(
            [
                {
                    "id": anthropic_strong,
                    "tier": "strong",
                    "provider": "anthropic",
                    "model_name": anthropic_strong,
                    "label": f"Opus 5.5 ({anthropic_strong})",
                    "short_label": "Opus 5.5",
                    "description": f"Anthropic deep reasoning & synthesis — Claude Opus 5.5 ({anthropic_strong})",
                },
                {
                    "id": anthropic_low,
                    "tier": "low",
                    "provider": "anthropic",
                    "model_name": anthropic_low,
                    "label": f"Sonnet 4.5 ({anthropic_low})",
                    "short_label": "Sonnet 4.5",
                    "description": f"Anthropic fast, low-cost execution — Claude Sonnet 4.5 ({anthropic_low})",
                },
            ]
        )

    return {
        "default_tier": default_resolved["tier"],
        "default_model": default_resolved["model_name"],
        "provider": default_resolved["provider"],
        "models": models,
    }


# `tier: ModelTier | str | None` selects the capability/cost level (`"low"`, `"medium"`, `"strong"`, or explicit model ID). If `None`, reads `nexus_primary_tier` fresh from `.env`.
# `provider: str | None` optionally forces the provider family (`"gemini"`, `"anthropic"`, `"openai"`), e.g. for subagent provider matching.
# `-> BaseChatModel` returns a configured LangChain chat model (`ChatGoogleGenerativeAI`, `ChatAnthropic`, or `ChatOpenAI`) ready for `.invoke()` or `.bind_tools()`.
def get_chat_model(
    tier: ModelTier | str | None = None,
    temperature: float = 0.0,
    provider: str | None = None,
) -> BaseChatModel:
    """Instantiate a tiered chat model routed to native Gemini (`ChatGoogleGenerativeAI`), Anthropic (`ChatAnthropic`), or OpenAI (`ChatOpenAI`).

    Re-reads `EngineSettings()` dynamically so `.env` model/tier edits and per-turn UI model overrides take effect
    on the very next turn without needing to edit `.py` files (which would cause `uvicorn --reload` to kill in-flight HTTP/SSE streams).
    """
    live_settings = EngineSettings()
    # Resolve configurable HTTP timeout (default 300s) and max retry count (default 3) from `.env`
    # Reasoning models (`gemini-4-argon`, `claude-opus-5-5`) require >90s on massive context histories to prevent 504 DEADLINE_EXCEEDED
    timeout = live_settings.ai_request_timeout
    max_retries = live_settings.ai_max_retries

    resolved = resolve_model_config(tier, provider=provider)
    effective_tier = resolved["tier"]
    model_name = resolved["model_name"]
    gemini_key = live_settings.gemini_api_key or live_settings.google_api_key or GEMINI_API_KEY
    anthropic_key = live_settings.anthropic_api_key or ANTHROPIC_API_KEY

    if resolved["provider"] == "anthropic":
        anthropic_kwargs: dict[str, Any] = {
            "model": model_name,
            "temperature": temperature,
            "timeout": timeout,
            "max_retries": max_retries,
        }
        if anthropic_key:
            anthropic_kwargs["api_key"] = anthropic_key
        return ChatAnthropic(**anthropic_kwargs)

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
