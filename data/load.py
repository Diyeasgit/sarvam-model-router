"""Load data/prompts.csv into router requests.

The router only sees: prompt, tools, channel, latency budget and use case.
The gold_* columns are the answer key, used by the simulator and the scorer.
"""
import csv
import json
import os

PATH = os.path.join(os.path.dirname(__file__), "prompts.csv")


def lang_bucket(language):
    source = language.split("→")[0] if "→" in language else language
    target = language.split("→")[-1]
    if language == "Hinglish":
        return "mixed"
    if source == "English" and target == "English":
        return "en"
    return "indic"


def load(split):
    reqs = []
    with open(PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["split"] != split:
                continue
            meta = {"use_case": r["use_case"], "channel": r["channel"]}
            if r["latency_budget_ms"]:
                meta["latency_budget_ms"] = int(r["latency_budget_ms"])
            reqs.append({
                "id": r["id"], "language": r["language"],
                "messages": [{"role": "user", "content": r["prompt"]}],
                "tools": json.loads(r["tools"]) if r["tools"] else [],
                "meta": meta,
                "gold": {"task": r["gold_task"], "difficulty": int(r["gold_difficulty"]),
                         "lang_bucket": lang_bucket(r["language"]),
                         "out_tokens": int(r["gold_out_tokens"]),
                         "out_script": r["gold_out_script"] or None,
                         "wants_json": r["gold_task"] == "extract",
                         "checks": json.loads(r["gold_checks"])},
            })
    return reqs
