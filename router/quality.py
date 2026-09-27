"""Two different quality checks, kept apart on purpose.

detect_issue()  runs in production, inside the request path. It has no gold
                answer, only cheap checks on the response: timeout, empty,
                refusal, JSON that does not parse, and an answer in the wrong
                script. A hit triggers a fallback.
score()         runs offline in the eval. It compares the answer with the gold
                spec. In sim mode it uses the simulator's hidden quality draw.
"""
import json
import re

from .features import dominant_script

REFUSAL = re.compile(r"\b(i'?m sorry|i cannot|i can'?t|i am unable|as an ai|i won'?t be able)\b", re.I)


def _parse_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        if "{" in t and "}" in t:
            try:
                return json.loads(t[t.index("{"): t.rindex("}") + 1])
            except Exception:
                return None
    return None


def detect_issue(resp, feats):
    if resp.status == "timeout":
        return "timeout"
    if resp.status != "ok":
        return "provider_error"
    text = resp.text.strip()
    if not text:
        return "empty"
    if REFUSAL.search(text[:200]):
        return "refusal"
    if feats["wants_json"] and feats["task"] == "extract" and _parse_json(text) is None:
        return "format_invalid"
    if feats.get("out_script") and feats["out_script"] != "latin" and "sim" not in text[:8]:
        if dominant_script(text) != feats["out_script"]:
            return "language_mismatch"
    return None


def score(resp, gold):
    """Return a quality score in [0, 1]."""
    if resp.status != "ok":
        return 0.0
    if resp.sim_quality is not None:
        return round(resp.sim_quality, 3)
    text = resp.text
    parts = []
    for chk in gold.get("checks", []):
        kind = chk["type"]
        if kind == "label":
            norm = re.sub(r"[^a-z_]", " ", text.lower()).split()
            parts.append(1.0 if chk["value"] in norm and len(norm) <= 6 else 0.0)
        elif kind == "json_keys":
            obj = _parse_json(text)
            parts.append(0.0 if not isinstance(obj, dict) else
                         sum(1 for k in chk["keys"] if k in obj) / len(chk["keys"]))
        elif kind == "keywords":
            hits = sum(1 for kw in chk["words"] if re.search(kw, text, re.I))
            parts.append(min(1.0, hits / (len(chk["words"]) * chk.get("min_frac", 0.6))))
        elif kind == "script":
            parts.append(1.0 if dominant_script(text) == chk["script"] else 0.0)
        elif kind == "tool_call":
            parts.append(1.0 if chk["name"] in text else 0.0)
    return round(sum(parts) / len(parts), 3) if parts else 0.5
