from datetime import date
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
from nexus.core.cost import ARGON_PROMO_END_DATE, resolve_model_pricing

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
# Resolves `ANTHROPIC_API_KEY` from `.env`; maps Opus 5.5 to `strong`, Sonnet 5.5 to `medium`, and Haiku 5.5 to `low`
ANTHROPIC_API_KEY = settings.anthropic_api_key
ANTHROPIC_MODEL_LOW = settings.anthropic_model_low
ANTHROPIC_MODEL_MEDIUM = settings.anthropic_model_medium
ANTHROPIC_MODEL_STRONG = settings.anthropic_model_strong

# Type alias defining the three standardized reasoning/cost tiers across providers
ModelTier = Literal["low", "medium", "strong"]


# `model_id: str` is an incoming Anthropic model string (e.g. `"claude-opus-5.5"`, `"claude-sonnet-5.5"`, `"claude-haiku-5.5"`, or `"claude-opus-4-5"`).
# `-> str` normalizes dot-separated version suffixes (`5.5`, `4.5`) into Anthropic's canonical hyphenated API format (`5-5`, `4-5`).
def _normalize_anthropic_model_name(model_id: str) -> str:
    """Normalize shorthand or dot-versioned Anthropic model strings into canonical Anthropic API identifiers."""
    cleaned = model_id.strip()
    lower = cleaned.lower()
    if lower in ("claude-opus-5.5", "opus-5.5", "opus-5-5", "opus 5.5"):
        return "claude-opus-5-5"
    if lower in ("claude-sonnet-5.5", "sonnet-5.5", "sonnet-5-5", "sonnet 5.5"):
        return "claude-sonnet-5-5"
    if lower in ("claude-haiku-5.5", "haiku-5.5", "haiku-5-5", "haiku 5.5"):
        return "claude-haiku-5-5"
    if lower in ("claude-opus-4.5", "opus-4.5", "opus-4-5", "opus 4.5"):
        return "claude-opus-4-5"
    if lower in ("claude-sonnet-4.5", "sonnet-4.5", "sonnet-4-5", "sonnet 4.5"):
        return "claude-sonnet-4-5"
    return cleaned


# `tier: str | None` accepts a standardized tier (`"low"`, `"medium"`, `"strong"`), a provider-qualified tier (`"anthropic:strong"`),
# or an explicit model ID (e.g. `"gemini-4-argon"`, `"claude-opus-5-5"`, `"claude-sonnet-5-5"`, `"claude-haiku-5-5"`).
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

    # Normalize requested tier/model; fall back to `nexus_primary_tier` from `.env` (default `"medium"`) when omitted
    raw_choice = (tier or "").strip()
    lower_choice = raw_choice.lower()
    default_tier = live_settings.nexus_primary_tier if live_settings.nexus_primary_tier in ("low", "medium", "strong") else "medium"

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
    elif lower_choice in ("gemini-4-hydrogen", "hydrogen"):
        # Explicit selection of Hydrogen maps symmetrically to Gemini `"medium"` tier
        active_provider = "gemini"
        model_name = "gemini-4-hydrogen"
        effective_tier = "medium"
    elif lower_choice in ("low", "medium", "strong"):
        effective_tier = lower_choice
        model_name = active_map[effective_tier]
    else:
        # Caller passed an explicit model name (e.g. `"gemini-4-hydrogen"`, `"claude-opus-5-5"`, `"claude-sonnet-5-5"`, `"claude-haiku-5-5"`):
        # 1. Detect provider from explicit model identifier if not explicitly overridden
        if any(tok in lower_choice for tok in ("claude", "opus", "sonnet", "haiku")):
            active_provider = "anthropic"
            raw_choice = _normalize_anthropic_model_name(raw_choice)
            lower_choice = raw_choice.lower()
        elif any(tok in lower_choice for tok in ("gemini", "argon", "hydrogen")):
            active_provider = "gemini"
        elif any(tok in lower_choice for tok in ("gpt", "o1", "o3")):
            active_provider = "openai"

        active_map = provider_maps.get(active_provider, active_map)
        # 2. Reverse-lookup its tier if it matches a configured tier, else classify `"low"` vs `"medium"` vs `"strong"` by family name
        matched_tier = next((t for t, m in active_map.items() if m.lower() == lower_choice), None)
        is_fast_family = any(tok in lower_choice for tok in ("flash", "mini", "haiku"))
        is_medium_family = any(tok in lower_choice for tok in ("sonnet", "hydrogen", "terra"))
        effective_tier = matched_tier or ("low" if is_fast_family else "medium" if is_medium_family else "strong")
        model_name = raw_choice

    tier_labels = {
        "strong": f"Strong · {model_name}",
        "medium": f"Medium · {model_name}",
        "low": f"Fast · {model_name}",
    }
    return {
        "tier": effective_tier,
        "provider": active_provider,
        "model_name": model_name,
        "label": tier_labels.get(effective_tier, model_name),
    }


# Standardized UI metadata keyed by canonical model ID (single source of truth for labels, concise explainers, and caveat pills)
_MODEL_CATALOG_META: dict[str, dict[str, str | None]] = {
    "gemini-4-argon": {
        "label": "Gemini 4 Argon",
        "short_label": "Argon",
        "description": "Deep multi-step reasoning, cross-document synthesis, and hard analytical problems.",
        "pricing_note": "$4/$20 Dec 1",
    },
    "gemini-4-hydrogen": {
        "label": "Gemini 4 Hydrogen",
        "short_label": "Hydrogen",
        "description": "Everyday coding, fast tool loops, and large-context work at mid-tier cost.",
        "pricing_note": None,
    },
    "gemini-3.8-flash": {
        "label": "Gemini 3.8 Flash",
        "short_label": "Flash",
        "description": "Quick lookups, routine summaries, and fast multimodal tasks on Gemini.",
        "pricing_note": "$1.50/$7.50 Jan 1",
    },
    "claude-opus-5-5": {
        "label": "Claude Opus 5.5",
        "short_label": "Opus 5.5",
        "description": "Flagship autonomous coding, nuanced writing, and high-stakes tasks.",
        "pricing_note": None,
    },
    "claude-sonnet-5-5": {
        "label": "Claude Sonnet 5.5",
        "short_label": "Sonnet 5.5",
        "description": "Balanced everyday drafting, coding, and reasoning at half Opus cost.",
        "pricing_note": None,
    },
    "claude-haiku-5-5": {
        "label": "Claude Haiku 5.5",
        "short_label": "Haiku 5.5",
        "description": "Near-instant, ultra-cheap replies, formatting, tagging, and light search.",
        "pricing_note": "5× >100K",
    },
    "gpt-5.6-sol": {
        "label": "GPT-5.6 Sol",
        "short_label": "Sol",
        "description": "Deep multi-step OpenAI reasoning, complex planning, and high-accuracy synthesis.",
        "pricing_note": None,
    },
    "gpt-5.6-terra": {
        "label": "GPT-5.6 Terra",
        "short_label": "Terra",
        "description": "Balanced everyday OpenAI model for writing, coding, and general tool workflows.",
        "pricing_note": None,
    },
    "gpt-5.4-mini": {
        "label": "GPT-5.4 Mini",
        "short_label": "Mini",
        "description": "Fast, low-cost OpenAI classification, short edits, and routine subagent tasks.",
        "pricing_note": None,
    },
}


# Formats a USD per-1M-token rate concisely (`$2` for whole integers, `$1.50` for cents, `$0.075` for sub-cent rates)
def _format_usd_rate(rate: float) -> str:
    if rate.is_integer():
        return f"${int(rate)}"
    formatted = f"{rate:.4f}".rstrip("0").rstrip(".")
    if "." in formatted and len(formatted.split(".")[1]) == 1:
        formatted += "0"
    return f"${formatted}"


# Builds one standardized catalog entry combining UI metadata with live rates resolved from `nexus.core.cost`
def _build_model_catalog_entry(entry_id: str, tier: str, provider: str, model_name: str) -> dict[str, Any]:
    meta = _MODEL_CATALOG_META.get(model_name, {})
    rates = resolve_model_pricing(model_name=model_name, tier=tier)
    fallback_short = model_name.split("/")[-1]
    # Clear the temporary Argon Dec 1 promo pill automatically once the cutover date arrives
    pricing_note = meta.get("pricing_note")
    if model_name == "gemini-4-argon" and date.today() >= ARGON_PROMO_END_DATE:
        pricing_note = None
    return {
        "id": entry_id,
        "tier": tier,
        "provider": provider,
        "model_name": model_name,
        "label": meta.get("label") or model_name,
        "short_label": meta.get("short_label") or fallback_short,
        "description": meta.get("description") or f"Use {model_name} for {tier}-tier execution.",
        "pricing": {
            "input_per_m": rates["input"],
            "output_per_m": rates["output"],
            "cached_per_m": rates["cached"],
            "summary": f"{_format_usd_rate(rates['input'])} / {_format_usd_rate(rates['output'])}",
            "note": pricing_note,
        },
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
    anthropic_medium = _normalize_anthropic_model_name(live_settings.anthropic_model_medium)
    anthropic_low = _normalize_anthropic_model_name(live_settings.anthropic_model_low)

    models: list[dict[str, Any]] = [
        _build_model_catalog_entry("strong", "strong", strong_cfg["provider"], strong_cfg["model_name"]),
    ]

    # Include the `"medium"` tier option if it maps to a distinct model from `"low"` and `"strong"`,
    # or if `nexus_primary_tier` is explicitly set to `"medium"` in `.env`.
    if (
        medium_cfg["model_name"] not in (strong_cfg["model_name"], low_cfg["model_name"])
        or live_settings.nexus_primary_tier == "medium"
    ):
        models.append(
            _build_model_catalog_entry("medium", "medium", medium_cfg["provider"], medium_cfg["model_name"])
        )

    # Order Gemini symmetrically (Strong -> Hydrogen Medium -> Low Flash) when Hydrogen isn't already bound above
    if (
        default_resolved["provider"] != "anthropic"
        and "gemini-4-hydrogen" not in (strong_cfg["model_name"], low_cfg["model_name"])
        and not any(m["model_name"] == "gemini-4-hydrogen" for m in models)
    ):
        models.append(
            _build_model_catalog_entry("gemini-4-hydrogen", "medium", "gemini", "gemini-4-hydrogen")
        )

    models.append(
        _build_model_catalog_entry("low", "low", low_cfg["provider"], low_cfg["model_name"])
    )

    # Append Anthropic Claude options (`claude-opus-5-5` Strong, `claude-sonnet-5-5` Medium, `claude-haiku-5-5` Low)
    # when the primary provider is not already Anthropic so all selectable models appear together in the Chat UI.
    if default_resolved["provider"] != "anthropic":
        models.extend(
            [
                _build_model_catalog_entry(anthropic_strong, "strong", "anthropic", anthropic_strong),
                _build_model_catalog_entry(anthropic_medium, "medium", "anthropic", anthropic_medium),
                _build_model_catalog_entry(anthropic_low, "low", "anthropic", anthropic_low),
            ]
        )

    return {
        "default_tier": default_resolved["tier"],
        "default_model": default_resolved["model_name"],
        "provider": default_resolved["provider"],
        "models": models,
    }


def resolve_resilience_max_retries(tier: str, live_settings: EngineSettings | None = None) -> int:
    """Resolve the outer `_invoke_llm_with_resilience` retry budget for a capability tier."""
    cfg = live_settings or EngineSettings()
    if cfg.ai_max_retries is not None:
        return int(cfg.ai_max_retries)
    return int(cfg.ai_max_retries_strong if tier == "strong" else cfg.ai_max_retries_default)


# `tier: ModelTier | str | None` selects the capability/cost level (`"low"`, `"medium"`, `"strong"`, or explicit model ID). If `None`, reads `nexus_primary_tier` fresh from `.env`.
# `provider: str | None` optionally forces the provider family (`"gemini"`, `"anthropic"`, `"openai"`), e.g. for subagent provider matching.
# `include_thoughts: bool | None` optionally overrides `EngineSettings.ai_include_thoughts` (e.g. `False` for lightweight background titling).
# `-> BaseChatModel` returns a configured LangChain chat model (`ChatGoogleGenerativeAI`, `ChatAnthropic`, or `ChatOpenAI`) ready for `.invoke()` or `.bind_tools()`.
def get_chat_model(
    tier: ModelTier | str | None = None,
    temperature: float = 0.0,
    provider: str | None = None,
    include_thoughts: bool | None = None,
) -> BaseChatModel:
    """Instantiate a tiered chat model routed to native Gemini (`ChatGoogleGenerativeAI`), Anthropic (`ChatAnthropic`), or OpenAI (`ChatOpenAI`).

    Re-reads `EngineSettings()` dynamically so `.env` model/tier edits and per-turn UI model selections take effect
    on the very next turn without needing to edit `.py` files (which would cause `uvicorn --reload` to kill in-flight HTTP/SSE streams).
    """
    live_settings = EngineSettings()
    # Resolve whether Gemini/Anthropic should return visible reasoning summaries (per-call override wins over .env default)
    effective_include_thoughts = (
        bool(live_settings.ai_include_thoughts) if include_thoughts is None else bool(include_thoughts)
    )

    resolved = resolve_model_config(tier, provider=provider)
    effective_tier = resolved["tier"]
    model_name = resolved["model_name"]
    # Resolve tier-appropriate HTTP timeout & SDK retry budget unless explicitly overridden via `AI_REQUEST_TIMEOUT` / `AI_MAX_RETRIES`:
    # `"strong"` models get 180s + 1 retry for deep reasoning; `"medium"`/`"low"` models fail fast at 60s + 2 retries.
    timeout = (
        int(live_settings.ai_request_timeout)
        if live_settings.ai_request_timeout is not None
        else int(live_settings.ai_timeout_strong if effective_tier == "strong" else live_settings.ai_timeout_default)
    )
    max_retries = resolve_resilience_max_retries(effective_tier, live_settings=live_settings)
    gemini_key = live_settings.gemini_api_key or live_settings.google_api_key or GEMINI_API_KEY
    anthropic_key = live_settings.anthropic_api_key or ANTHROPIC_API_KEY

    if resolved["provider"] == "anthropic":
        lower_name = model_name.lower()
        # Newer Anthropic reasoning models (Opus 5.5, Opus 4.7+, Sonnet 5+, Haiku 5+) have deprecated custom sampling
        # dials (temperature, top_p, top_k) and return HTTP 400 (`temperature is deprecated for this model`).
        # Omitting or passing `temperature=None` causes `ChatAnthropic._get_request_payload` to exclude `temperature`
        # entirely from the JSON payload, respecting the model's native default sampling behavior.
        is_temp_deprecated = any(
            tok in lower_name
            for tok in ("opus-5", "opus 5", "opus-4-7", "opus 4.7", "sonnet-5", "sonnet 5", "haiku-5", "haiku 5")
        )
        # Adaptive thinking (`type="adaptive", display="summarized"`) is supported by Claude 4.6+ / 5.x models;
        # legacy 4.5 models keep standard non-thinking invocation unless configured otherwise.
        is_adaptive_thinking_model = any(
            tok in lower_name
            for tok in (
                "opus-5",
                "opus 5",
                "opus-4-6",
                "opus 4.6",
                "opus-4-7",
                "opus 4.7",
                "sonnet-5",
                "sonnet 5",
                "sonnet-4-6",
                "sonnet 4.6",
                "haiku-5",
                "haiku 5",
            )
        )
        # Enable Anthropic Prompt Caching automatically across the conversation and tool-loop prefix:
        # Top-level `cache_control={"type": "ephemeral"}` instructs the Anthropic Messages API to place an
        # automatic ephemeral cache breakpoint (5-minute TTL, 0.05x–0.1x cached read rate on hits) on the final cacheable
        # block in each request payload, eliminating redundant re-processing across multi-turn chats & tool loops.
        anthropic_kwargs: dict[str, Any] = {
            "model": model_name,
            "timeout": timeout,
            "max_retries": max_retries,
            "model_kwargs": {"cache_control": {"type": "ephemeral"}},
        }
        if effective_include_thoughts and is_adaptive_thinking_model:
            # Summarized adaptive thinking returns readable `thinking` blocks + cryptographic signatures;
            # raise `max_tokens` above LangChain's 4096 fallback so thinking tokens do not starve final output.
            anthropic_kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
            anthropic_kwargs["max_tokens"] = max(4096, int(live_settings.anthropic_thinking_max_tokens or 16384))
        # Anthropic rejects requests that combine `thinking` with a custom `temperature`
        if not is_temp_deprecated and "thinking" not in anthropic_kwargs and temperature is not None:
            anthropic_kwargs["temperature"] = temperature
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
            include_thoughts=effective_include_thoughts,
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
