"""Model registry, SLA thresholds and global assumptions.

Every number here is an ASSUMPTION unless stated otherwise. They live in one
file so a customer POC can overwrite them with measured values (their own
price sheet, their own GPU throughput, their own tokenizer fertility).
"""

FX_INR_PER_USD = 88.0  # assumption, used only for the INR column in reports

# Prices are USD per 1M tokens. cpt_* = characters per token (tokenizer
# fertility). Indic text tokenises far worse on English-centric tokenizers,
# which means the SAME Hindi prompt costs a different number of tokens on
# each model. That is modelled explicitly because it often matters more than
# the headline price.
MODELS = {
    "llama-3.1-8b": {
        "label": "Small open-weight (Llama-3.1-8B class)",
        "price_in": 0.05, "price_out": 0.08,
        "ttft_ms": 150, "tps": 350, "timeout_p": 0.005,
        "ctx": 128_000, "cpt_latin": 4.0, "cpt_indic": 1.5,
        "env_prefix": "TINY",
    },
    "sarvam-indic": {
        "label": "Sarvam Indic model (sarvam-m / Sarvam-30B class)",
        "price_in": 0.10, "price_out": 0.30,
        "ttft_ms": 300, "tps": 120, "timeout_p": 0.01,
        "ctx": 32_000, "cpt_latin": 4.0, "cpt_indic": 3.0,
        "env_prefix": "SARVAM",
    },
    "llama-3.3-70b": {
        "label": "Large open-weight (Llama-3.3-70B class)",
        "price_in": 0.60, "price_out": 0.80,
        "ttft_ms": 400, "tps": 90, "timeout_p": 0.01,
        "ctx": 128_000, "cpt_latin": 4.0, "cpt_indic": 1.5,
        "env_prefix": "MID",
    },
    "frontier": {
        "label": "Frontier API model (Claude Sonnet / GPT-4.1 class)",
        "price_in": 3.00, "price_out": 15.00,
        "ttft_ms": 900, "tps": 60, "timeout_p": 0.02,
        "ctx": 200_000, "cpt_latin": 4.0, "cpt_indic": 2.0,
        "env_prefix": "FRONTIER",
    },
}

CHEAPEST = "llama-3.1-8b"
FRONTIER = "frontier"
CLASSIFIER_MODEL = "llama-3.1-8b"  # used for the LLM classifier when heuristics are unsure

# Quality bar per task: the minimum estimated P(success) a model must reach
# before the router will send it this task. These are the numbers a customer
# should negotiate, because they are the trade-off made explicit.
DEFAULT_SLA = {
    "classify": 0.85,
    "extract": 0.90,
    "summarize": 0.85,
    "translate": 0.85,
    "chat": 0.80,
    "code": 0.90,
    "reasoning": 0.85,
    "tool_use": 0.90,
}

DEFAULT_TIMEOUT_MS = 20_000
VOICE_ATTEMPT_FRACTION = 0.6    # a voice turn gives its first attempt 60% of the latency budget
MAX_FALLBACKS = 2
LLM_CLASSIFIER_CONFIDENCE = 0.5  # below this heuristic confidence, call the LLM classifier
PASS_THRESHOLD = 0.7            # a response counts as a pass at quality >= this

# Rough output-length expectations (English-token units) by task, used only
# for pre-call cost/latency estimates.
EXPECTED_OUT_TOKENS = {
    "classify": 5, "extract": 120, "summarize": 150, "translate": 60,
    "chat": 50, "code": 300, "reasoning": 350, "tool_use": 80,
}


def price(model, tokens_in, tokens_out):
    m = MODELS[model]
    return (tokens_in * m["price_in"] + tokens_out * m["price_out"]) / 1e6
