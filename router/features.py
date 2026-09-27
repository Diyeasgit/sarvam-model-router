"""Step 1 of the router: classify the request.

Extracts cheap, explainable features from the prompt (structure, language,
code, tools, constraints), infers the task type and scores difficulty from 1
to 5. It also returns a confidence value; when that is low the router asks a
small LLM classifier for a second opinion (see policy.py).

Only the request is used here, never the gold labels.
"""
import re

from . import config

INDIC_RANGES = {
    "deva": (0x0900, 0x097F), "beng": (0x0980, 0x09FF), "guru": (0x0A00, 0x0A7F),
    "gujr": (0x0A80, 0x0AFF), "orya": (0x0B00, 0x0B7F), "taml": (0x0B80, 0x0BFF),
    "telu": (0x0C00, 0x0C7F), "knda": (0x0C80, 0x0CFF), "mlym": (0x0D00, 0x0D7F),
}

# Frequent romanised-Hindi function words used to detect Hinglish in Latin script.
ROMAN_HI = set("""
hai hain nahi nahin kya mera meri mere aap aapka aapki kar karo karu karna ho gaya gayi
tha thi bhi se ko ki ka hua raha rahi chahiye kyun kab acha accha theek paisa paise bhai ji
haan abhi wala wali kaise kaun kitna kitni batao bolo mujhe humko hum yeh woh ye wo toh
bol rahi raha mein pe par lekin aur jaldi dobara lagta kuch sab
""".split())

LANG_NAMES = {
    "hindi": "deva", "हिंदी": "deva", "हिन्दी": "deva", "marathi": "deva",
    "tamil": "taml", "bengali": "beng", "bangla": "beng", "telugu": "telu",
    "kannada": "knda", "malayalam": "mlym", "gujarati": "gujr", "punjabi": "guru",
    "odia": "orya", "english": "latin", "अंग्रेज़ी": "latin", "angrezi": "latin",
}

TASK_KEYWORDS = {
    "translate": ["translate", "translation", "अनुवाद", "into hindi", "into tamil", "into english",
                  "to english", "in english:"],
    "classify": ["classify", "label", "intent", "category", "sentiment", "one of",
                 "only the label", "one word", "reply with only", "answer with only",
                 "इरादा", "लेबल", "भावना", "हेतू", "फक्त"],
    "extract": ["extract", "json", "fields", "schema", "parse", "key-value", "keys:"],
    "summarize": ["summarise", "summarize", "summary", "tl;dr", "key points", "bullet",
                  "सारांश", "सार", "saaransh"],
    "code": ["```", "def ", "python", "sql", "function", "bug", "refactor", "regex",
             "javascript", "select ", "stack trace", "traceback"],
    "reasoning": ["step by step", "calculate", "prove", "compare", "which is cheaper",
                  "which is better", "trade-off", "eligible", "eligibility", "plan ",
                  "schedule", "reason", "derive", "पात्र", "गणना"],
    "chat": ["you are a voice", "voice agent", "voice assistant", "वॉइस", "reply in",
             "short answer", "छोटा जवाब", "max 2 sentences"],
}

REASONING_MARKERS = ["step by step", "show your work", "explain why", "justify", "prove",
                     "all constraints", "calculate", "compare", "trade-off"]


def script_counts(text):
    counts = {"latin": 0}
    for ch in text:
        o = ord(ch)
        if ch.isascii():
            if ch.isalpha():
                counts["latin"] += 1
            continue
        for name, (lo, hi) in INDIC_RANGES.items():
            if lo <= o <= hi:
                counts[name] = counts.get(name, 0) + 1
                break
    return counts


def dominant_script(text):
    c = script_counts(text)
    if not any(c.values()):
        return "latin"
    return max(c, key=c.get)


def est_tokens(text, model):
    """Estimate token count for `text` on `model`'s tokenizer (fertility-aware)."""
    m = config.MODELS[model]
    c = script_counts(text)
    latin = c.get("latin", 0)
    indic = sum(v for k, v in c.items() if k != "latin")
    other = max(0, len(text) - latin - indic)  # spaces, digits, punctuation
    return int(latin / m["cpt_latin"] + indic / m["cpt_indic"] + other / 3.0) + 4


def _flatten(messages):
    return "\n".join(m.get("content", "") for m in messages if isinstance(m.get("content"), str))


def extract(messages, tools=None, meta=None):
    meta = meta or {}
    tools = tools or []
    text = _flatten(messages)
    low = text.lower()

    # ---- language ---------------------------------------------------------
    sc = script_counts(text)
    latin = sc.get("latin", 0)
    indic = sum(v for k, v in sc.items() if k != "latin")
    total_letters = max(1, latin + indic)
    indic_ratio = indic / total_letters
    words = re.findall(r"[a-zA-Z]+", low)
    roman_hi_ratio = (sum(1 for w in words if w in ROMAN_HI) / len(words)) if words else 0.0

    target_script = None
    for pat in [r"(?:into|in|to)\s+([a-zA-Z]+)", r"([^\s]+)\s+(?:में|mein)"]:
        for mm in re.finditer(pat, low):
            name = mm.group(1)
            if name in LANG_NAMES:
                target_script = LANG_NAMES[name]
    in_script = max((k for k in sc if k != "latin"), key=lambda k: sc[k], default=None) if indic else "latin"

    if indic_ratio > 0.5:
        lang_bucket = "indic"
    elif roman_hi_ratio > 0.12 or (0.1 < indic_ratio <= 0.5):
        lang_bucket = "mixed"
    else:
        lang_bucket = "en"
    if target_script and target_script != "latin" and lang_bucket == "en":
        lang_bucket = "indic"  # English in, Indic out: generation quality is what matters

    # Script the answer is expected in (used by the language-mismatch fallback check).
    if target_script:
        out_script = target_script
    elif lang_bucket == "indic":
        out_script = in_script
    else:
        out_script = None  # unconstrained

    # ---- structure --------------------------------------------------------
    has_code = "```" in text or bool(re.search(r"\b(def|class|SELECT|FROM|return|import)\b", text))
    wants_json = "json" in low
    n_constraints = len(re.findall(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+", text)) + \
        len(re.findall(r"\b(must|should|do not|don't|never|always|exactly|at most|at least)\b", low))
    reasoning_hits = sum(1 for k in REASONING_MARKERS if k in low)
    n_numbers = len(re.findall(r"\d[\d,.]*", text))

    # ---- task type --------------------------------------------------------
    scores = {t: sum(1 for k in kws if k in low) for t, kws in TASK_KEYWORDS.items()}
    if tools:
        scores["tool_use"] = 3 + len(tools)
    if meta.get("channel") == "voice":
        scores["chat"] = scores.get("chat", 0) + 3
    if wants_json:
        scores["extract"] += 1
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (task, top), (_, second) = ranked[0], ranked[1]
    if top == 0:
        task, confidence = "chat", 0.2
    else:
        confidence = (top - second) / top
        confidence = min(1.0, confidence + (0.2 if top >= 3 else 0.0))

    # ---- difficulty -------------------------------------------------------
    base = {"classify": 1, "chat": 1, "translate": 2, "extract": 2, "summarize": 2,
            "code": 3, "tool_use": 3, "reasoning": 3}[task]
    d = float(base)
    reasons = ["base(%s)=%d" % (task, base)]
    tokens_in = est_tokens(text, config.FRONTIER)
    if tokens_in > 6000:
        d += 2; reasons.append("very long context +2")
    elif tokens_in > 1500:
        d += 1; reasons.append("long context +1")
    if n_constraints >= 4:
        d += 1; reasons.append("%d constraints +1" % n_constraints)
    if reasoning_hits and task != "reasoning":
        d += 1; reasons.append("reasoning markers +1")
    elif reasoning_hits >= 2:
        d += 1; reasons.append("heavy reasoning +1")
    if len(tools) >= 3:
        d += 1; reasons.append("%d tools +1" % len(tools))
    if wants_json and ("list" in low or "array" in low or "nested" in low):
        d += 0.5; reasons.append("nested JSON +0.5")
    if lang_bucket == "mixed":
        d += 0.5; reasons.append("code-mixed +0.5")
    if n_numbers >= 6 and task in ("reasoning", "extract"):
        d += 0.5; reasons.append("numeric-heavy +0.5")
    difficulty = int(max(1, min(5, round(d))))

    return {
        "task": task,
        "task_confidence": round(confidence, 2),
        "task_scores": {k: v for k, v in ranked if v},
        "lang_bucket": lang_bucket,
        "in_script": in_script,
        "out_script": out_script,
        "indic_ratio": round(indic_ratio, 2),
        "roman_hi_ratio": round(roman_hi_ratio, 2),
        "has_code": has_code,
        "wants_json": wants_json,
        "n_tools": len(tools),
        "n_constraints": n_constraints,
        "difficulty": difficulty,
        "difficulty_reasons": reasons,
        "chars": len(text),
        "channel": meta.get("channel", "text"),
        "latency_budget_ms": meta.get("latency_budget_ms"),
        "sla": meta.get("sla"),
        "classifier": "heuristic",
    }


def diff_bucket(d):
    return "low" if d <= 2 else ("mid" if d == 3 else "high")
