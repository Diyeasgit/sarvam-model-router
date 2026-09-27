"""Model backends.

LiveBackend  - any OpenAI-compatible /chat/completions endpoint (Sarvam, vLLM,
               TGI, Groq, Together, OpenRouter, Azure...). Standard library only.
SimBackend   - a seeded simulator used when no API keys are available. It holds
               a hidden "true" capability profile for each model, which differs
               from the router's prior, and uses the gold difficulty label that
               the router never sees. Its failures take the same forms as real
               ones: refusals, broken JSON, wrong-language answers, timeouts and
               silent low-quality answers (which no fallback check can see).
"""
import json
import math
import os
import random
import time
import urllib.error
import urllib.request

from . import config
from .features import est_tokens


class Response:
    def __init__(self, text, tokens_in, tokens_out, latency_ms, status="ok", sim_quality=None):
        self.text = text
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.latency_ms = latency_ms
        self.status = status          # ok | timeout | error
        self.sim_quality = sim_quality  # only set by SimBackend


# --------------------------------------------------------------------------- live
class LiveBackend:
    """Env vars per model: <PREFIX>_BASE_URL, <PREFIX>_API_KEY, <PREFIX>_MODEL
    e.g. SARVAM_BASE_URL=https://api.sarvam.ai/v1 SARVAM_MODEL=sarvam-m"""
    name = "live"

    def complete(self, model, req, timeout_ms):
        pre = config.MODELS[model]["env_prefix"]
        base = os.environ[pre + "_BASE_URL"].rstrip("/")
        key = os.environ.get(pre + "_API_KEY", "")
        body = {"model": os.environ[pre + "_MODEL"], "messages": req["messages"],
                "temperature": 0}
        if req.get("tools"):
            body["tools"] = [{"type": "function", "function": t} for t in req["tools"]]
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key,
                   "api-subscription-key": key}  # Sarvam accepts the latter
        r = urllib.request.Request(base + "/chat/completions", json.dumps(body).encode(), headers)
        t0 = time.perf_counter()
        prompt_text = "\n".join(m["content"] for m in req["messages"])
        try:
            with urllib.request.urlopen(r, timeout=timeout_ms / 1000) as resp:
                data = json.loads(resp.read())
        except Exception as e:  # timeout, 5xx, connection reset
            lat = (time.perf_counter() - t0) * 1000
            status = "timeout" if "timed out" in str(e).lower() else "error"
            return Response("", est_tokens(prompt_text, model), 0, lat, status)
        lat = (time.perf_counter() - t0) * 1000
        msg = data["choices"][0]["message"]
        text = msg.get("content") or ""
        if msg.get("tool_calls"):
            text += "\n" + json.dumps([tc["function"] for tc in msg["tool_calls"]])
        usage = data.get("usage") or {}
        return Response(text, usage.get("prompt_tokens", est_tokens(prompt_text, model)),
                        usage.get("completion_tokens", est_tokens(text, model)), lat)

    def classify(self, req):
        """LLM classifier: ask the small model for task + difficulty as JSON."""
        text = "\n".join(m["content"] for m in req["messages"])[:2000]
        prompt = ("Classify this request for an LLM router. Reply with JSON only: "
                  '{"task": one of [classify, extract, summarize, translate, chat, code, reasoning, tool_use], '
                  '"difficulty": 1-5}\n\nREQUEST:\n' + text)
        resp = self.complete(config.CLASSIFIER_MODEL, {"messages": [{"role": "user", "content": prompt}]}, 5000)
        try:
            out = json.loads(resp.text[resp.text.index("{"): resp.text.rindex("}") + 1])
            return out["task"], int(out["difficulty"]), resp
        except Exception:
            return None, None, resp


# --------------------------------------------------------------------------- sim
# Hidden "ground truth" for the simulator. Deliberately not equal to the
# router's PRIOR_SKILL, so calibration has something real to learn.
TRUE_SKILL = {"llama-3.1-8b": 2.4, "sarvam-indic": 3.1, "llama-3.3-70b": 3.7, "frontier": 5.0}
TRUE_LANG = {
    "llama-3.1-8b": {"indic": -1.4, "mixed": -0.9},
    "sarvam-indic": {"indic": 0.9, "mixed": 0.7},
    "llama-3.3-70b": {"indic": -0.7, "mixed": -0.3},
    "frontier": {"indic": -0.3, "mixed": 0.0},
}
TRUE_TASK = {
    "llama-3.1-8b": {"classify": 0.6, "code": -0.4, "reasoning": -0.6, "tool_use": -0.6, "extract": -0.3},
    "sarvam-indic": {"code": -0.6, "tool_use": -0.8, "translate": 0.5},
    "llama-3.3-70b": {"code": 0.2},
    "frontier": {},
}
DETECTABLE_SHARE = 0.45  # share of failures that are visible (refusal / bad JSON / wrong language)


class SimBackend:
    name = "sim"

    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def true_p(self, model, gold):
        lang = gold["lang_bucket"]
        skill = TRUE_SKILL[model] + TRUE_LANG[model].get(lang, 0) + TRUE_TASK[model].get(gold["task"], 0)
        return 1 / (1 + math.exp(-1.7 * (skill - gold["difficulty"] + 0.5)))

    def complete(self, model, req, timeout_ms):
        m, gold, rng = config.MODELS[model], req["gold"], self.rng
        prompt_text = "\n".join(x["content"] for x in req["messages"])
        tin = est_tokens(prompt_text, model)
        out_indic = gold.get("out_script") not in (None, "latin")
        out_chars = gold["out_tokens"] * 4
        tout = max(1, int(out_chars / (m["cpt_indic"] if out_indic else m["cpt_latin"])
                          * rng.lognormvariate(0, 0.2)))
        latency = m["ttft_ms"] * rng.lognormvariate(0, 0.35) + tout / m["tps"] * 1000 * rng.lognormvariate(0, 0.2)
        latency += tin / 20  # prefill, ~20k tok/s
        if rng.random() < m["timeout_p"] or latency > timeout_ms:
            return Response("", tin, 0, timeout_ms, "timeout")

        json_task = gold["task"] == "extract" or gold.get("wants_json")
        if rng.random() < self.true_p(model, gold):
            text = '{"sim": "good answer"}' if json_task else "[sim] good answer"
            return Response(text, tin, tout, latency, sim_quality=rng.uniform(0.8, 1.0))
        if rng.random() < DETECTABLE_SHARE:
            if json_task:
                text = "Sure! name - Ravi, amount - 5000"             # fails the JSON parse
            elif out_indic:
                text = "Here is the answer in English instead."      # fails the script check
            else:
                text = "I'm sorry, but I can't help with that request."  # refusal
            return Response(text, tin, tout, latency, sim_quality=rng.uniform(0.0, 0.3))
        # silent failure: plausible text, wrong content; only the eval can see it
        text = '{"sim": "plausible but wrong"}' if json_task else "[sim] plausible but wrong"
        return Response(text, tin, tout, latency, sim_quality=rng.uniform(0.2, 0.65))

    def classify(self, req):
        """Simulated LLM classifier: right task 90% of the time, difficulty +/-1 noise."""
        gold, rng = req["gold"], self.rng
        tasks = list(config.DEFAULT_SLA)
        task = gold["task"] if rng.random() < 0.9 else rng.choice(tasks)
        diff = max(1, min(5, gold["difficulty"] + rng.choice([-1, 0, 0, 0, 1])))
        m = config.MODELS[config.CLASSIFIER_MODEL]
        tin = min(est_tokens("\n".join(x["content"] for x in req["messages"]), config.CLASSIFIER_MODEL), 700) + 120
        lat = m["ttft_ms"] * rng.lognormvariate(0, 0.3) + 25 / m["tps"] * 1000
        return task, diff, Response("", tin, 25, lat)
