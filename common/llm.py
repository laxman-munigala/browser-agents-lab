"""The LLM every self-hosted level uses: an OpenRouter model (DeepSeek V4.1 Flash).

OpenRouter speaks the OpenAI chat-completions API, so any OpenAI-compatible
client works with BASE_URL + the key. Hosted agents (Browser Use Cloud,
TinyFish) bring their own models and don't use this.
"""

from __future__ import annotations

from common.config import env, require

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"

# USD per million tokens (input, output), from openrouter.ai/api/v1/models
# on 2026-09-27. Only used to estimate cost on the scoreboard.
PRICES = {
    "deepseek/deepseek-v4.1-flash": (0.035, 0.29),
    "deepseek/deepseek-v4-flash-0731": (0.021, 0.32),
}


def model() -> str:
    return env("LAB_LLM_MODEL") or DEFAULT_MODEL


def api_key() -> str:
    return require("OPENROUTER_API_KEY")


def estimate_cost(tokens_in: int, tokens_out: int, model_name: str | None = None) -> float | None:
    price = PRICES.get(model_name or model())
    if price is None:
        return None
    return (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000


def openai_client():
    """An openai.OpenAI client pointed at OpenRouter."""
    from openai import OpenAI

    return OpenAI(base_url=BASE_URL, api_key=api_key())
