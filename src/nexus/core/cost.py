"""
cost.py — Real-time LLM inference pricing catalog and cost estimation engine.

Provides pricing lookup tables for supported Google Gemini and OpenAI model families,
taking into account:
1. Standard uncached input prompt tokens ($ / 1M tokens)
2. Prompt context caching discounts ($ / 1M tokens, e.g. 75% Gemini discount or 50% OpenAI discount)
3. Output / completion tokens ($ / 1M tokens)
"""

# Dict, Optional, Any: Type hints for pricing dictionary mapping and nullable parameters
from typing import Any, Dict, Optional


# ── Model Pricing Catalog (USD per 1,000,000 tokens) ─────────────────────────
# Pricing rates are expressed in dollars per 1M tokens ($ / 1,000,000).
# - "input": Standard prompt tokens evaluated without cache hit
# - "cached": Cached prompt tokens (Google Gemini context cache or OpenAI prompt cache)
# - "output": Generated candidate/completion tokens
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # ── Google Gemini Family ──────────────────────────────────────────────────
    # Fast / Low-Latency Tier: Gemini Flash family
    "gemini-3.8-flash": {
        "input": 0.10,      # $0.10 / 1M prompt tokens
        "cached": 0.025,    # $0.025 / 1M cached tokens (75% discount)
        "output": 0.40,     # $0.40 / 1M completion tokens
    },
    "gemini-2.5-flash": {
        "input": 0.075,
        "cached": 0.01875,
        "output": 0.30,
    },
    "gemini-1.5-flash": {
        "input": 0.075,
        "cached": 0.01875,
        "output": 0.30,
    },
    # Deep Reasoning / Strong Tier: Gemini Argon / Pro family
    "gemini-4-argon": {
        "input": 1.25,      # $1.25 / 1M prompt tokens (<= 128k context)
        "cached": 0.3125,   # $0.3125 / 1M cached tokens (75% discount)
        "output": 5.00,     # $5.00 / 1M completion tokens
    },
    "gemini-2.5-pro": {
        "input": 1.25,
        "cached": 0.3125,
        "output": 5.00,
    },
    "gemini-1.5-pro": {
        "input": 1.25,
        "cached": 0.3125,
        "output": 5.00,
    },

    # ── OpenAI Family ─────────────────────────────────────────────────────────
    # Fast / Low-Latency Tier: GPT Mini family
    "gpt-5.4-mini": {
        "input": 0.15,      # $0.15 / 1M prompt tokens
        "cached": 0.075,    # $0.075 / 1M cached tokens (50% discount)
        "output": 0.60,     # $0.60 / 1M completion tokens
    },
    "gpt-4o-mini": {
        "input": 0.15,
        "cached": 0.075,
        "output": 0.60,
    },
    # Balanced Medium Tier: GPT Terra / 4o family
    "gpt-5.6-terra": {
        "input": 2.50,      # $2.50 / 1M prompt tokens
        "cached": 1.25,     # $1.25 / 1M cached tokens (50% discount)
        "output": 10.00,    # $10.00 / 1M completion tokens
    },
    "gpt-4o": {
        "input": 2.50,
        "cached": 1.25,
        "output": 10.00,
    },
    # Deep Reasoning / Strong Tier: GPT Sol / o-series family
    "gpt-5.6-sol": {
        "input": 5.00,      # $5.00 / 1M prompt tokens
        "cached": 2.50,     # $2.50 / 1M cached tokens
        "output": 20.00,    # $20.00 / 1M completion tokens
    },
    "o1": {
        "input": 15.00,
        "cached": 7.50,
        "output": 60.00,
    },
    "o3-mini": {
        "input": 1.10,
        "cached": 0.55,
        "output": 4.40,
    },
}

# Fallback baseline pricing by standardized tier when model name is unmapped
TIER_FALLBACK_PRICING: Dict[str, Dict[str, float]] = {
    "low": MODEL_PRICING["gemini-3.8-flash"],
    "medium": MODEL_PRICING["gemini-2.5-pro"],
    "strong": MODEL_PRICING["gemini-4-argon"],
}


def resolve_model_pricing(
    model_name: Optional[str] = None,
    tier: Optional[str] = None,
) -> Dict[str, float]:
    """
    Resolves the exact or fuzzy pricing rates ($ / 1M tokens) for a given model or tier.
    
    Args:
        model_name: Concrete model identifier (e.g. 'gemini-4-argon', 'gpt-5.4-mini')
        tier: Standardized capability tier ('low', 'medium', 'strong')

    Returns:
        Dict with keys 'input', 'cached', 'output' containing rates per 1M tokens.
    """
    clean_model = (model_name or "").strip().lower()
    clean_tier = (tier or "").strip().lower()

    # 1. Exact match in catalog
    if clean_model in MODEL_PRICING:
        return MODEL_PRICING[clean_model]

    # 2. Fuzzy substring match in catalog (only if clean_model is non-empty)
    if clean_model:
        for key, rates in MODEL_PRICING.items():
            if key in clean_model or clean_model in key:
                return rates

        # 3. Model family heuristic patterns
        if "flash" in clean_model:
            return MODEL_PRICING["gemini-3.8-flash"]
        if "mini" in clean_model:
            return MODEL_PRICING["gpt-5.4-mini"]
        if "terra" in clean_model or "4o" in clean_model:
            return MODEL_PRICING["gpt-5.6-terra"]
        if "argon" in clean_model or "pro" in clean_model:
            return MODEL_PRICING["gemini-4-argon"]
        if "sol" in clean_model or "o1" in clean_model:
            return MODEL_PRICING["gpt-5.6-sol"]

    # 4. Fall back to standardized tier
    if clean_tier in TIER_FALLBACK_PRICING:
        return TIER_FALLBACK_PRICING[clean_tier]

    # 5. Default safe fallback (strong tier)
    return TIER_FALLBACK_PRICING["strong"]


def calculate_token_cost(
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    model_name: Optional[str] = None,
    tier: Optional[str] = None,
) -> float:
    """
    Computes total USD cost for a given token usage breakdown.

    Deducts `cached_tokens` from `input_tokens` so cached tokens are billed at
    their discounted cache rate and only net uncached prompt tokens pay full price.

    Args:
        input_tokens: Total prompt token count (including cached tokens)
        output_tokens: Generated completion token count
        cached_tokens: Prompt tokens served from provider context cache
        model_name: Provider model name for rate resolution
        tier: Capability tier fallback

    Returns:
        Total estimated cost in USD rounded to 6 decimal places.
    """
    rates = resolve_model_pricing(model_name=model_name, tier=tier)

    # Prompt tokens that were NOT served from cache
    uncached_input = max(0, int(input_tokens or 0) - int(cached_tokens or 0))
    cached_input = min(int(input_tokens or 0), max(0, int(cached_tokens or 0)))
    completion = max(0, int(output_tokens or 0))

    # Calculate costs (rates are per 1M tokens)
    input_cost = (uncached_input * rates["input"]) / 1_000_000.0
    cached_cost = (cached_input * rates["cached"]) / 1_000_000.0
    output_cost = (completion * rates["output"]) / 1_000_000.0

    total_cost = input_cost + cached_cost + output_cost
    return round(total_cost, 6)


def calculate_cache_savings(
    input_tokens: int,
    cached_tokens: int,
    model_name: Optional[str] = None,
    tier: Optional[str] = None,
) -> float:
    """
    Calculates the USD amount saved by prompt caching vs paying full input price.
    """
    rates = resolve_model_pricing(model_name=model_name, tier=tier)
    cached_count = min(int(input_tokens or 0), max(0, int(cached_tokens or 0)))
    # Difference between full input rate and discounted cached rate
    discount_per_million = rates["input"] - rates["cached"]
    savings = (cached_count * discount_per_million) / 1_000_000.0
    return round(max(0.0, savings), 6)
