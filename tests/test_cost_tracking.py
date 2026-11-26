"""
test_cost_tracking.py — Unit test suite for LLM inference pricing and cost observability.
Verifies rate lookups, prompt caching discounts, run snapshot cost attachment, and audit calculations.
"""

import json
from pathlib import Path
import pytest

from nexus.core.cost import (
    MODEL_PRICING,
    TIER_FALLBACK_PRICING,
    calculate_cache_savings,
    calculate_token_cost,
    resolve_model_pricing,
)
from nexus.core.run_logger import get_run, list_runs, log_run


def test_resolve_model_pricing():
    """Verifies exact, fuzzy, and tier-fallback pricing resolution."""
    # Exact matches
    hydrogen_rates = resolve_model_pricing("gemini-4-hydrogen")
    assert hydrogen_rates["input"] == 1.50
    assert hydrogen_rates["cached"] == 0.075
    assert hydrogen_rates["output"] == 7.50

    # Active Gemini 3.8 Flash introductory rates ($0.75 in / $0.075 cached / $3.75 out)
    flash_rates = resolve_model_pricing("gemini-3.8-flash")
    assert flash_rates["input"] == 0.75
    assert flash_rates["cached"] == 0.075
    assert flash_rates["output"] == 3.75

    # Active Gemini 4 Argon promotional rates ($2.00 in / $0.10 cached / $10.00 out)
    argon_rates = resolve_model_pricing("gemini-4-argon")
    assert argon_rates["input"] == 2.00
    assert argon_rates["cached"] == 0.10
    assert argon_rates["output"] == 10.00

    mini_rates = resolve_model_pricing("gpt-5.4-mini")
    assert mini_rates["input"] == 0.15
    assert mini_rates["output"] == 0.60

    # Anthropic Claude Opus 5.5, Sonnet 5.5, Haiku 5.5, and legacy Opus 4.5 / Sonnet 4.5 exact and dot-alias matches
    opus55_rates = resolve_model_pricing("claude-opus-5-5")
    assert opus55_rates["input"] == 4.00
    assert opus55_rates["cached"] == 0.20
    assert opus55_rates["output"] == 20.00
    assert resolve_model_pricing("claude-opus-5.5") == opus55_rates

    sonnet55_rates = resolve_model_pricing("claude-sonnet-5-5")
    assert sonnet55_rates["input"] == 2.00
    assert sonnet55_rates["cached"] == 0.10
    assert sonnet55_rates["output"] == 10.00
    assert resolve_model_pricing("claude-sonnet-5.5") == sonnet55_rates
    # Unknown/dated Sonnet aliases resolve to the active Sonnet 5.5 rate card
    assert resolve_model_pricing("claude-sonnet-latest") == sonnet55_rates

    haiku55_rates = resolve_model_pricing("claude-haiku-5-5")
    assert haiku55_rates["input"] == 0.10
    assert haiku55_rates["cached"] == 0.01
    assert haiku55_rates["output"] == 0.50
    assert resolve_model_pricing("claude-haiku-5.5") == haiku55_rates
    assert resolve_model_pricing("claude-haiku-latest") == haiku55_rates

    opus45_rates = resolve_model_pricing("claude-opus-4-5")
    assert opus45_rates["input"] == 5.00
    assert opus45_rates["cached"] == 0.50
    assert opus45_rates["output"] == 25.00
    assert resolve_model_pricing("claude-opus-4.5") == opus45_rates

    sonnet_rates = resolve_model_pricing("claude-sonnet-4-5")
    assert sonnet_rates["input"] == 3.00
    assert sonnet_rates["cached"] == 0.30
    assert sonnet_rates["output"] == 15.00
    assert resolve_model_pricing("claude-sonnet-4.5") == sonnet_rates

    # Opus and Sonnet stay flat above 128k context, while Haiku 5.5 steps up 5x strictly above 100k input tokens
    assert resolve_model_pricing("claude-opus-5-5", tier="strong", input_tokens=160_000) == opus55_rates
    assert resolve_model_pricing("claude-sonnet-5-5", tier="medium", input_tokens=160_000) == sonnet55_rates
    assert resolve_model_pricing("claude-haiku-5-5", tier="low", input_tokens=100_000) == haiku55_rates
    haiku55_long_rates = resolve_model_pricing("claude-haiku-5-5", tier="low", input_tokens=150_000)
    assert haiku55_long_rates == {"input": 0.50, "cached": 0.05, "output": 2.50}
    assert resolve_model_pricing("claude-opus-4-5", tier="strong", input_tokens=160_000) == opus45_rates
    assert resolve_model_pricing("claude-sonnet-4-5", tier="low", input_tokens=160_000) == sonnet_rates

    # Fuzzy matches
    fuzzy_hydrogen = resolve_model_pricing("models/gemini-4-hydrogen-exp")
    assert fuzzy_hydrogen == hydrogen_rates

    fuzzy_flash = resolve_model_pricing("models/gemini-3.8-flash-exp")
    assert fuzzy_flash == flash_rates

    # Tier fallbacks ("low" defaults to Gemini 3.8 Flash)
    low_rates = resolve_model_pricing(tier="low")
    assert low_rates == TIER_FALLBACK_PRICING["low"]
    assert low_rates == flash_rates

    strong_rates = resolve_model_pricing(tier="strong")
    assert strong_rates == TIER_FALLBACK_PRICING["strong"]


def test_context_stepup_pricing_threshold():
    """Verifies legacy Gemini Pro 2x >128k step-up while Gemini 4 Argon, Hydrogen, and Flash stay flat across 1M context."""
    # Gemini 4 Argon stays flat at $2.00 in / $0.10 cached / $10.00 out across its 1M unified context window
    argon_standard = resolve_model_pricing("gemini-4-argon", input_tokens=100_000)
    assert argon_standard["input"] == 2.00
    assert argon_standard["cached"] == 0.10
    assert argon_standard["output"] == 10.00

    argon_long = resolve_model_pricing("gemini-4-argon", input_tokens=150_000)
    assert argon_long == argon_standard

    # Legacy Gemini 2.5 Pro <= 128k tokens: standard rates apply ($1.25 in / $0.3125 cached / $5.00 out)
    standard_rates = resolve_model_pricing("gemini-2.5-pro", input_tokens=100_000)
    assert standard_rates["input"] == 1.25
    assert standard_rates["cached"] == 0.3125
    assert standard_rates["output"] == 5.00

    # Legacy Gemini 2.5 Pro > 128k tokens: 2x step-up rates apply ($2.50 in / $0.625 cached / $10.00 out)
    stepup_rates = resolve_model_pricing("gemini-2.5-pro", input_tokens=150_000)
    assert stepup_rates["input"] == 2.50
    assert stepup_rates["cached"] == 0.625
    assert stepup_rates["output"] == 10.00

    # Gemini 4 Hydrogen and Flash models do NOT double above 128k context (flat rate across entire 1M window)
    hydrogen_stepup_low = resolve_model_pricing("gemini-4-hydrogen", tier="low", input_tokens=500_000)
    assert hydrogen_stepup_low["input"] == 1.50
    assert hydrogen_stepup_low["cached"] == 0.075
    assert hydrogen_stepup_low["output"] == 7.50

    hydrogen_stepup_med = resolve_model_pricing("gemini-4-hydrogen", tier="medium", input_tokens=500_000)
    assert hydrogen_stepup_med == hydrogen_stepup_low

    flash_stepup = resolve_model_pricing("gemini-3.8-flash", input_tokens=150_000)
    assert flash_stepup["input"] == 0.75
    assert flash_stepup["cached"] == 0.075
    assert flash_stepup["output"] == 3.75

    # Verify calculate_token_cost applies 2x rates above 128k for legacy Gemini 2.5 Pro
    # 200k input total (150k cached @ $0.625/1M, 50k uncached @ $2.50/1M) + 10k output @ $10.00/1M:
    # Uncached: 50,000 * 2.50 / 1M = $0.125
    # Cached:   150,000 * 0.625 / 1M = $0.09375
    # Output:   10,000 * 10.00 / 1M = $0.100
    # Expected: 0.125 + 0.09375 + 0.100 = $0.31875
    cost = calculate_token_cost(
        input_tokens=200_000,
        output_tokens=10_000,
        cached_tokens=150_000,
        model_name="gemini-2.5-pro",
    )
    assert cost == 0.31875


def test_calculate_token_cost_uncached():
    """Verifies cost computation for purely uncached token usage."""
    # 1,000,000 input tokens on Gemini 3.8 Flash @ $0.75/1M = $0.75
    # 1,000,000 output tokens on Gemini 3.8 Flash @ $3.75/1M = $3.75
    # Total = $4.50
    cost = calculate_token_cost(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cached_tokens=0,
        model_name="gemini-3.8-flash",
    )
    assert cost == 4.50


def test_calculate_token_cost_with_caching_discount():
    """Verifies that cached tokens receive provider prompt caching discounts."""
    # 1,000,000 input tokens total, where 800,000 are cached on Gemini 4 Hydrogen (95% discount):
    # Uncached: 200,000 * $1.50 / 1M = $0.300
    # Cached:   800,000 * $0.075 / 1M = $0.060
    # Output:   100,000 * $7.50 / 1M = $0.750
    # Expected: $1.110
    hydrogen_cost = calculate_token_cost(
        input_tokens=1_000_000,
        output_tokens=100_000,
        cached_tokens=800_000,
        model_name="gemini-4-hydrogen",
    )
    assert hydrogen_cost == 1.11

    # Savings calculation: 800k * ($1.50 - $0.075) / 1M = 800k * 1.425 / 1M = $1.14
    hydrogen_savings = calculate_cache_savings(
        input_tokens=1_000_000,
        cached_tokens=800_000,
        model_name="gemini-4-hydrogen",
    )
    assert hydrogen_savings == 1.14

    # 1,000,000 input tokens total, where 800,000 are cached on Gemini 3.8 Flash (90% discount):
    # Uncached: 200,000 * $0.75 / 1M = $0.150
    # Cached:   800,000 * $0.075 / 1M = $0.060
    # Output:   100,000 * $3.75 / 1M = $0.375
    # Expected: $0.585
    cost = calculate_token_cost(
        input_tokens=1_000_000,
        output_tokens=100_000,
        cached_tokens=800_000,
        model_name="gemini-3.8-flash",
    )
    assert cost == 0.585

    # Savings calculation: 800k * ($0.75 - $0.075) / 1M = 800k * 0.675 / 1M = $0.540
    savings = calculate_cache_savings(
        input_tokens=1_000_000,
        cached_tokens=800_000,
        model_name="gemini-3.8-flash",
    )
    assert savings == 0.54


def test_calculate_token_cost_zero_tokens():
    """Verifies edge case handling for 0 or negative tokens."""
    cost = calculate_token_cost(input_tokens=0, output_tokens=0, cached_tokens=0)
    assert cost == 0.0


def test_log_run_persists_cost_and_subagent_breakdown():
    """Verifies log_run calculates and attaches cost_usd to the SQLite run snapshot and subagents."""
    trace_events = [
        # Root agent info
        {
            "type": "info",
            "agent_id": "nexus",
            "data": {
                "input_tokens": 100_000,
                "output_tokens": 2_000,
                "cached_tokens": 80_000,
            },
        },
        # Spawned subagent start & info
        {
            "type": "agent_start",
            "agent_id": "subagent-1",
            "data": {"model_tier": "low", "task_prompt": "Audit section 1"},
        },
        {
            "type": "info",
            "agent_id": "subagent-1",
            "data": {
                "input_tokens": 50_000,
                "output_tokens": 1_000,
                "cached_tokens": 40_000,
            },
        },
        {
            "type": "agent_end",
            "agent_id": "subagent-1",
        },
    ]

    run_id = log_run(
        agent_name="nexus",
        query="Test cost logging query",
        response="Test response",
        trace_events=trace_events,
        metadata={"model_tier": "strong", "model_name": "gemini-4-argon"},
    )

    assert isinstance(run_id, str)
    data = get_run(run_id)
    assert data is not None

    # Validate root cost_usd field exists and is positive
    assert "cost_usd" in data
    assert data["cost_usd"] > 0

    # Validate metadata token_usage contains cost_usd and cache_savings_usd
    tok = data["metadata"]["token_usage"]
    assert "cost_usd" in tok
    assert "cache_savings_usd" in tok
    assert tok["cost_usd"] == data["cost_usd"]

    # Validate subagent record contains its isolated cost_usd
    assert len(data["subagents"]) == 1
    sub = data["subagents"][0]
    assert "cost_usd" in sub
    assert sub["cost_usd"] > 0
    assert sub["input_tokens"] == 50_000
    assert sub["output_tokens"] == 1_000

    # Verify list_runs and get_run return cost_usd
    summaries = list_runs(limit=5)
    assert len(summaries) >= 1
    assert summaries[0]["cost_usd"] == data["cost_usd"]

    retrieved = get_run(data["run_id"])
    assert retrieved is not None
    assert retrieved["cost_usd"] == data["cost_usd"]
