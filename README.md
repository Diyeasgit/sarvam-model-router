# Sarvam Model Router

A router that sends each LLM request to the **cheapest model that is good enough for it**, checks the answer, and **escalates to a stronger model when something visibly goes wrong**.

> **Read this first: the headline numbers are SIMULATED.** No API keys were available in the build environment, so the models are played by a seeded simulator (`router/backends.py`). The live path, for any OpenAI-compatible endpoint including Sarvam, is implemented but was **not** exercised for this submission. Every price, latency and skill level is an assumption set in one file (`router/config.py`). What this repo proves is the **method and the measurement harness**. It does not prove a specific savings number. Section 7 lists what changes when you plug in real keys.

---

## 1. Results (Part 1 baselines)

40 held-out prompts × 30 random seeds. Held-out means none of these prompts were used to tune the router. `results/summary.md` has the full table and `logs/*.jsonl` has every request.

| Policy | Cost / 1k requests | vs always-frontier | p50 latency | p95 latency | Pass rate | Fallback rate |
|---|---|---|---|---|---|---|
| Always-cheapest (Llama-8B class) | $0.014 (₹1.2) | 1% | 0.4 s | 1.3 s | **42%** | n/a |
| Always-frontier | $1.80 (₹158) | 100% | 2.3 s | 7.5 s | 91% | n/a |
| **Router** | **$0.96 (₹84)** | **53%** | **1.1 s** | 7.3 s | **91%** | 3.8% |
| Router without fallback (ablation) | $0.88 | 49% | 1.1 s | 6.8 s | 89% | n/a |

**By language, which is where Sarvam's edge shows:**

| Segment | Frontier cost / 1k | Router cost / 1k | Router as % of frontier | Pass rate (frontier → router) |
|---|---|---|---|---|
| English | $2.13 | $1.50 | 70% | 92% → 91% |
| Indic + code-mixed | $1.50 | $0.47 | **31%** | 90% → 90% |

**In plain terms:**
1. **Always-cheapest is a false economy.** It costs almost nothing but fails more than half the time, and two-thirds of the time on Indian-language traffic. Each failure becomes a human re-work or an angry customer.
2. **The router matches frontier quality at about half the cost** (91% vs 91% pass rate). Median latency also halves, because most requests go to faster models.
3. **Savings concentrate in Indian-language traffic** (69% cheaper). An Indic-specialised model is both better and cheaper there. Frontier tokenizers also split Hindi or Tamil into more tokens, so the same sentence is billed at more tokens (see the `cpt_indic` assumption).
4. **p95 latency barely moves.** The slowest 5% of requests are the genuinely hard ones: reasoning, code and multi-tool tasks. The router still sends those to frontier, correctly. Routing improves typical latency, not worst-case latency.
5. **The fallback costs 8% more ($0.88 → $0.96) and lifts pass rate by 2 points.** Whether that is worth it is a customer decision. For a compliance workload, yes. For bulk tagging, maybe not.
6. **Seed-to-seed spread is wide** (router pass rate 82–98% across seeds), because 40 prompts is a small sample. A single 40-prompt run cannot separate 89% from 91%. A real POC needs 500+ prompts from the customer's own traffic.

Savings depend on the **traffic mix**. This test set is deliberately heavy on hard tasks (about a third are reasoning, code, tool-use or long compliance summaries). A typical call-centre mix, mostly intent tagging, short summaries and voice turns, would route more to the cheap tiers and save more. That is a projection, not a measurement.

---

## 2. How the router decides, in plain language

Think of it as a **triage desk in a hospital**.

1. **Triage (classify the request).** Before calling any model, the router reads the request and notes what kind of job it is (classification, extraction, summary, translation, voice reply, code, reasoning, tool use), what language it is in (English, Indian-script, or Hinglish written in English letters), and how hard it looks on a 1–5 scale. Difficulty goes up for long documents, many instructions ("must… never… at least…"), phrases like "step by step", several tools, nested JSON and code-mixing. This costs a fraction of a millisecond. **If the router is unsure what the task is** (confidence below 0.5), it asks a small, cheap LLM for a second opinion. That extra call is billed to the router and included in all totals.
2. **Pick the cheapest model that clears the bar.** Every task type has a quality bar: extraction 90%, summaries 85%, voice chat 80%, and so on (`DEFAULT_SLA`). For each model the router looks up its estimated chance of passing this kind of request, learned from a separate calibration run. It then takes the **cheapest model whose chance clears the bar**. Models that cannot meet a hard constraint are skipped first, for example a voice turn with a 1.5-second budget, or a document too long for a model's context window. If no model clears the bar, it uses the strongest one available.
3. **Check the answer and escalate if needed.** After the answer comes back, cheap automatic checks run: did it time out, come back empty, refuse, return broken JSON, or answer in the wrong language? If so, the router retries on the next-cheapest *stronger* model, up to 2 retries. The customer only sees the final answer, and the log records that a fallback fired and why.

Every decision is written as a sentence in the log, for example:

```
H23 (Hinglish call summary) → sarvam-indic
  "llama-3.1-8b p=0.62<0.85; sarvam-indic p=0.94>=0.85 cheapest-sufficient"
  tokens 142 in / 65 out · $0.0000337 · 797 ms · quality 0.93 · fallback: no
```

Read that as: the cheapest model had a 62% chance of doing this well enough, below the 85% bar. The Sarvam model had 94%, so it won. Try it yourself:

```bash
python3 route.py "mera card kho gaya hai, jaldi block karo"
python3 route.py --voice "आप बैंक के वॉइस असिस्टेंट हैं। ग्राहक: मेरा बैलेंस कितना है?"
```

### Where do the "chance of passing" numbers come from?
From a **calibration set** of 24 prompts, kept separate from the 40 test prompts. Each of the 4 models answers each calibration prompt, and we count how often each model passed for each combination of task, language and difficulty. Cells with few observations are pulled towards the broader average: "Sarvam on Hindi summaries" leans on "Sarvam on Hindi overall" until it has enough data of its own. That keeps the numbers auditable. Every probability traces back to a pass count.

### The four models

| Model (class) | Role | Price in / out, per 1M tokens (assumed) | Speed (assumed) |
|---|---|---|---|
| Llama-3.1-8B | Very cheap, fast, fine for simple English tagging | $0.05 / $0.08 | first token 150 ms |
| **Sarvam Indic** (sarvam-m / 30B class) | Indian languages and Hinglish, efficient Indic tokenizer | $0.10 / $0.30 | 300 ms |
| Llama-3.3-70B | Mid-tier generalist | $0.60 / $0.80 | 400 ms |
| Frontier (Claude Sonnet / GPT-4.1 class) | Hard reasoning, code, multi-tool tasks | $3.00 / $15.00 | 900 ms |

---

## 3. Timeouts, refusals and other failures

| What happens | Detected how | Router's response |
|---|---|---|
| **Timeout** | No answer within the per-attempt limit: 20 s for text; for voice, 60% of the remaining latency budget, so time is left for a retry | Retry on the next stronger model **if it can still finish inside the budget**. Otherwise return a degraded response, e.g. "let me connect you to an agent", and log `no time left`. Input tokens of the timed-out call are assumed billed. |
| **Refusal** ("I'm sorry, I can't…") | Pattern match on the first 200 characters | Retry one tier up, since small models often refuse over-cautiously. **If frontier also refuses, the refusal stands** and is logged for human review. A refusal from the strongest model is usually a real policy boundary, not something to route around. |
| **Broken JSON** on extraction | JSON parse fails | Retry one tier up |
| **Wrong language** (asked for Tamil, got English) | Script detection | Retry one tier up |
| **Provider error** (5xx, reset) | HTTP error | Retry one tier up |
| **Answer looks fine but is wrong** | **Cannot be detected at run time** | Not caught. It shows up only in offline evaluation. This is the biggest blind spot. |

After fallbacks, 3.2% of router requests still ended with an unresolved issue: mostly frontier-tier timeouts or format errors with nothing stronger to escalate to.

---

## 4. What the quality measure does *not* capture

- **In this submission quality is simulated.** Each model has a hidden "true skill" that I set, so quality results reflect my assumptions about the models, not the models themselves. In particular, Sarvam beating frontier on Indic tasks is **an input assumption, not a finding**. A live run is needed to confirm it.
- In live mode, scoring uses **cheap automatic checks**: correct label, required JSON keys present, required keywords present, correct script. These miss:
  - **Fluency and tone.** A Hindi translation can be in Devanagari and contain the right number, yet sound robotic or use the wrong register (आप vs तुम).
  - **Faithfulness.** A summary can contain the right keywords and still invent a commitment the agent never made. That is the most dangerous failure in a compliance workflow.
  - **Partial correctness in reasoning.** Right final number, wrong working.
  - **Whether a tool call's arguments were right.** The check only confirms the right tool was called.
  - **Business outcome.** Did the customer's issue get resolved? Did the agent save time?
- **Pass/fail at 0.7 is a blunt line.** A 0.69 and a 0.2 are both "fail" but are very different to a customer.
- **Small, self-written test set.** I wrote both the prompts and the classifier rules, so classifier accuracy on this set (58/64 exact) is optimistic. Real traffic will be messier.
- A POC should add an **LLM-as-judge with a rubric**, **human spot-checks on a sample** (especially Indic), and ideally **a business KPI** from the customer (re-work rate, CSAT).

---

## 5. Trade-offs I considered and dropped

| Option | Why I didn't use it |
|---|---|
| **A trained neural router** (RouteLLM-style, predicting which model wins from embeddings) | Needs thousands of labelled comparisons we don't have, and its decisions can't be explained in a sentence. Enterprise and government buyers need to audit why a request went where it did. The lookup table can later be swapped for a learned model with the same interface. |
| **Always use an LLM to classify** | Adds 150–300 ms and a small cost to *every* request, which is a real cost for voice. The router uses rules first and calls the LLM only when unsure (about 7% of requests here). |
| **Cascade: always try cheapest, escalate on failure** | Simple, but it doubles latency on every hard request and can't catch silent failures. Picking the right model up front and escalating only on visible failures is faster. |
| **Minimise expected cost including fallback cost** | More "optimal" mathematically, but the tie-break is harder to explain. The threshold rule ("cheapest model that clears the bar") maps directly onto an SLA a customer can sign. |
| **LLM-as-judge on every response to trigger fallbacks** | Doubles cost and latency. Kept for offline evaluation and sampling instead. |
| **Semantic caching** | Valuable (voice FAQs repeat a lot) but a separate lever. Noted for the roadmap. |

---

## 6. Deploying inside a customer VPC or an air-gapped rack

The router is **under 1,000 lines of Python with no external dependencies** and makes no calls home, which is exactly what an air-gapped deployment needs.

- **Customer VPC:** run the router as a stateless service (a container behind the customer's load balancer) in front of models served in the same VPC (vLLM or TGI for Sarvam and Llama models) and, if policy allows, a private-link connection to one frontier API. Scale by adding router replicas. The router is cheap; the GPUs are the cost.
- **Air-gapped:** there is no frontier API, so the top tier becomes the **largest open-weight model on the rack**. The same policy applies with a different model list in `config.py`. Price per token becomes **GPU-seconds per token**. The router then optimises GPU utilisation rather than an API bill, often freeing a GPU for another workload.
- **Keeping it calibrated without sending data out:** request logs stay on-site. A monthly job re-runs `calibrate.py` on a sample of the customer's own traffic, scored by the local judge plus human reviewers, and updates the pass-rate table. Only aggregate pass rates change; no data leaves.
- **Controls customers will ask for:** per-tenant quality bars and budgets, a "never leave the VPC" flag on sensitive requests (hard-excludes external APIs), full audit log of every routing decision, and a kill switch to pin everything to one model.

---

## 7. Assumptions (made where the brief was silent)

- Prices, latencies, token fertility (`cpt_*`) and skill levels in `router/config.py` and `router/backends.py` are **illustrative**. Measure them in a POC, especially Indic token fertility, which can swing cost more than the headline price.
- USD→INR at 88.
- Timed-out calls bill input tokens but not output tokens.
- The simulated LLM classifier is right about the task 90% of the time, with difficulty ±1.
- "Pass" means quality ≥ 0.7.
- Voice turns have a 1.5 s end-to-end budget.
- All prompts are synthetic. Any names, IDs and amounts are invented.

## 8. Stack and how to run

Python 3.9, standard library only.

```bash
python3 calibrate.py      # learn pass rates from the calibration set → results/estimator.json
python3 evaluate.py       # run baselines + router on the held-out set → results/summary.md, logs/*.jsonl
python3 route.py "..."    # explain one routing decision
```

Live mode: set `<PREFIX>_BASE_URL`, `<PREFIX>_API_KEY` and `<PREFIX>_MODEL` for each prefix TINY, SARVAM, MID and FRONTIER (any OpenAI-compatible endpoint; e.g. `SARVAM_BASE_URL=https://api.sarvam.ai/v1`, `SARVAM_MODEL=sarvam-m`). Then run `python3 calibrate.py --live && python3 evaluate.py --live`.

| File | What it is |
|---|---|
| `router/features.py` | Step 1: reads the request, works out task, language and difficulty |
| `router/estimator.py` | "Chance of passing" table, learned from calibration |
| `router/policy.py` | Step 2 (cheapest model over the bar) and step 3 (fallbacks), plus the per-request log |
| `router/quality.py` | Run-time failure checks (drive fallbacks) and offline scoring (drives the report) |
| `router/backends.py` | Live API client and the simulator |
| `router/config.py` | Models, prices, quality bars: every assumption in one place |
| `data/prompts.py` | 24 calibration + 40 held-out synthetic prompts (English, Hindi, Hinglish, Marathi, Tamil, Bengali, Kannada, Telugu) |

## Parts 2 & 3

*(To be added: the brief as received covered Part 1 only.)*
