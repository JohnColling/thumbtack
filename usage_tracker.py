"""ThumbTack Token Usage Tracker

Provides UsageStats dataclass, pricing lookup, and cost calculation
for LLM calls.  Compatible with OpenAI-Responses, Anthropic, and LiteLLM.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

# ── Pricing (per 1M tokens in USD) — fallback baked-in ───────────────
# Source: LiteLLM/OpenRouter prices as of May 2026
_DEFAULT_PRICES: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-4o":               {"input": 2.50,   "output": 10.00},
    "gpt-4o-mini":          {"input": 0.150,  "output": 0.600},
    "gpt-4-turbo":          {"input": 10.00,  "output": 30.00},
    "gpt-3.5-turbo":        {"input": 0.50,   "output": 1.50},
    "o3-mini":              {"input": 1.10,   "output": 4.40},
    "o1":                   {"input": 15.00,  "output": 60.00},
    "o1-mini":              {"input": 1.10,   "output": 4.40},
    # Anthropic
    "claude-sonnet-4":      {"input": 3.00,   "output": 15.00},
    "claude-opus-4":        {"input": 15.00,  "output": 75.00},
    "claude-haiku-3.5":     {"input": 0.80,   "output": 4.00},
    # Local / Ollama (free)
    "qwen:2.5-coder":       {"input": 0.0,    "output": 0.0},
    "qwen:3.0":             {"input": 0.0,    "output": 0.0},
    "qwen2.5-coder":        {"input": 0.0,    "output": 0.0},
    "kimi-k2.6:cloud":      {"input": 0.0,    "output": 0.0},
    "llama3.3":             {"input": 0.0,    "output": 0.0},
    "mixtral":              {"input": 0.0,    "output": 0.0},
    "phi4":                 {"input": 0.0,    "output": 0.0},
}


def _load_model_prices() -> Dict[str, Dict[str, float]]:
    """Load model prices from LiteLLM's public pricing file, or fall back to baked-in."""
    # Try LiteLLM's bundled price map if available
    try:
        import litellm
        if hasattr(litellm, "model_cost"):
            return litellm.model_cost
    except Exception:
        pass

    # Try loading from a local JSON dump
    local = Path(__file__).parent / "model_prices.json"
    if local.exists():
        try:
            return json.loads(local.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    return dict(_DEFAULT_PRICES)


# ── UsageStats ─────────────────────────────────────────────────────────

@dataclass
class UsageStats:
    """Aggregated usage for a single LLM call or session."""
    model: str = ""
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0

    def add(self, other: "UsageStats") -> "UsageStats":
        """Return a new UsageStats that is the sum of self + other."""
        return UsageStats(
            model=self.model if self.model == other.model else f"{self.model},{other.model}",
            request_count=self.request_count + other.request_count,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            cost=round(self.cost + other.cost, 6),
        )

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "request_count": self.request_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost": self.cost,
        }


# ── Helpers ────────────────────────────────────────────────────────────

_MODEL_PRICES = _load_model_prices()


def get_price(model: str) -> Dict[str, float]:
    """Return {input, output} price per 1M tokens for a model, or zeros."""
    # Exact match
    if model in _MODEL_PRICES:
        p = _MODEL_PRICES[model]
        if isinstance(p, dict) and "input" in p and "output" in p:
            return p
    # Try stripping provider prefix (e.g. "openai/gpt-4o" → "gpt-4o")
    if "/" in model:
        short = model.split("/")[-1]
        if short in _MODEL_PRICES:
            p = _MODEL_PRICES[short]
            if isinstance(p, dict) and "input" in p and "output" in p:
                return p
    # Try fuzzy match
    for key, p in _MODEL_PRICES.items():
        if key in model or model in key:
            if isinstance(p, dict) and "input" in p and "output" in p:
                return p
    return {"input": 0.0, "output": 0.0}


def calculate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Return USD cost for a given token count and model."""
    prices = get_price(model)
    inp = (input_tokens / 1_000_000) * prices["input"]
    out = (output_tokens / 1_000_000) * prices["output"]
    return round(inp + out, 6)


def extract_usage_from_response(response, model: str = "") -> UsageStats:
    """Extract UsageStats from a raw LLM response object.
    
    Supports:
    - OpenAI Responses API (response.usage)
    - OpenAI Chat Completions (response.usage)
    - Anthropic Messages (response.usage)
    """
    if response is None:
        return UsageStats()

    u = getattr(response, "usage", None)
    if u is None:
        # Try dict-style access
        if isinstance(response, dict):
            u = response.get("usage")
        if u is None:
            return UsageStats()

    model_name = model or getattr(response, "model", "")

    # OpenAI style
    prompt_tokens  = getattr(u, "prompt_tokens", None)
    completion_t   = getattr(u, "completion_tokens", None)
    total_t        = getattr(u, "total_tokens", None)
    cached_t       = getattr(u, "prompt_tokens_details", None)
    reasoning_t    = getattr(u, "completion_tokens_details", None)

    # Dict fallback
    if prompt_tokens is None:
        prompt_tokens  = u.get("prompt_tokens", 0) if isinstance(u, dict) else 0
    if completion_t is None:
        completion_t   = u.get("completion_tokens", 0) if isinstance(u, dict) else 0
    if total_t is None:
        total_t        = u.get("total_tokens", 0) if isinstance(u, dict) else 0

    cached_tokens = 0
    if cached_t is not None:
        if isinstance(cached_t, dict):
            cached_tokens = cached_t.get("cached_tokens", 0)
        else:
            cached_tokens = getattr(cached_t, "cached_tokens", 0)

    reasoning_tokens = 0
    if reasoning_t is not None:
        if isinstance(reasoning_t, dict):
            reasoning_tokens = reasoning_t.get("reasoning_tokens", 0)
        else:
            reasoning_tokens = getattr(reasoning_t, "reasoning_tokens", 0)

    # Anthropic style (input_tokens / output_tokens)
    if prompt_tokens == 0 and completion_t == 0:
        prompt_tokens  = getattr(u, "input_tokens", 0)
        completion_t   = getattr(u, "output_tokens", total_t or 0)
        if completion_t and not total_t:
            total_t = prompt_tokens + completion_t

    total_t = total_t or (prompt_tokens + completion_t)

    cost = calculate_cost(prompt_tokens, completion_t, model_name)

    return UsageStats(
        model=model_name,
        request_count=1,
        input_tokens=prompt_tokens,
        output_tokens=completion_t,
        total_tokens=total_t,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        cost=cost,
    )


def format_usage_for_display(stats: UsageStats, currency: str = "AUD") -> str:
    """Rich-text formatted string for terminal / UI display."""
    lines = []
    lines.append(f"Requests: {stats.request_count}")
    lines.append("Tokens:")
    lines.append(f"  Input:  {stats.input_tokens:,}")
    lines.append(f"  Output: {stats.output_tokens:,}")
    lines.append(f"  Total:  {stats.total_tokens:,}")
    if stats.cached_tokens:
        lines.append(f"  Cached: {stats.cached_tokens:,}")
    if stats.reasoning_tokens:
        lines.append(f"  Reasoning: {stats.reasoning_tokens:,}")

    # Convert to AUD (rough approximation)
    rate = 1.54  # USD → AUD
    cost_local = stats.cost * rate
    lines.append(f"Cost: ${cost_local:.6f} {currency}")
    return "\n".join(lines)
