"""Models, prices, quality bars and contract rules - every assumption in one file.

Prices are the same list prices used in Part 2 of the README (INR per 1M
tokens), so Part 1's measured costs and Part 2's monthly projection use
the same numbers.
"""

# The platform's three model classes: Sarvam's own model, an open-weight model
# hosted on Sarvam, and a frontier API model.
MODELS = {
    "sarvam-105b": {
        "label": "Sarvam 105B (Sarvam's own model, Indic-first)",
        "price_in": 29.28, "price_out": 73.20,
        "ttft_ms": 350, "tps": 110, "timeout_p": 0.01,
        "ctx": 64_000, "cpt_latin": 4.0, "cpt_indic": 3.0,
        "env_prefix": "SARVAM",
    },
    "glm-5.3": {
        "label": "GLM-5.3 (open-weight, hosted on Sarvam, beta)",
        "price_in": 126.0, "price_out": 396.0,
        "ttft_ms": 500, "tps": 80, "timeout_p": 0.015,
        "ctx": 128_000, "cpt_latin": 4.0, "cpt_indic": 1.8,
        "env_prefix": "OPEN",
    },
    "opus-5": {
        "label": "Claude Opus 5 (frontier API)",
        "price_in": 480.0, "price_out": 2410.0,
        "ttft_ms": 1100, "tps": 55, "timeout_p": 0.02,
        "ctx": 200_000, "cpt_latin": 4.0, "cpt_indic": 2.0,
        "env_prefix": "FRONTIER",
    },
}
# cpt_* = characters per token. Indic text splits into more tokens on
# English-centric tokenizers, so the same Hindi prompt is billed at more
# tokens on GLM or Opus than on Sarvam. Part 2 conservatively ignores this.

CHEAPEST = "sarvam-105b"
FRONTIER = "opus-5"
CLASSIFIER_MODEL = "sarvam-105b"  # second-opinion classifier when the rules are unsure

# Per-use-case contract terms (see README Part 3, Q3):
#   bar = minimum estimated P(pass) before a model may take the request
#   pin = fixed route that skips the router (no classifier cost or latency)
USE_CASES = {
    "disposition_tagging": {"bar": 0.85, "pin": None},
    "call_summary":        {"bar": 0.85, "pin": None},
    "kyc_extraction":      {"bar": 0.90, "pin": None},
    "customer_notices":    {"bar": 0.90, "pin": None},
    "voice_agent":         {"bar": 0.80, "pin": "sarvam-105b"},  # latency: fixed route
    "compliance_review":   {"bar": 0.95, "pin": "opus-5"},       # high stakes: always frontier
}

# Fallback bar when a request carries no use-case tag.
DEFAULT_SLA = {
    "classify": 0.85, "extract": 0.90, "summarize": 0.85, "translate": 0.90,
    "chat": 0.80, "code": 0.90, "reasoning": 0.90, "tool_use": 0.90,
}

DEFAULT_TIMEOUT_MS = 20_000
VOICE_ATTEMPT_FRACTION = 0.6     # a voice turn gives its first attempt 60% of the budget
MAX_FALLBACKS = 2
LLM_CLASSIFIER_CONFIDENCE = 0.5  # below this rule confidence, ask the LLM classifier
PASS_THRESHOLD = 0.7             # an answer counts as a pass at quality >= this

# Rough output-length expectation (English-token units) by task, for pre-call estimates.
EXPECTED_OUT_TOKENS = {
    "classify": 5, "extract": 120, "summarize": 150, "translate": 60,
    "chat": 50, "code": 300, "reasoning": 350, "tool_use": 80,
}


def price(model, tokens_in, tokens_out):
    """Cost in INR."""
    m = MODELS[model]
    return (tokens_in * m["price_in"] + tokens_out * m["price_out"]) / 1e6
