# Sarvam Model Router

**The pitch in one line:** send each request to the cheapest model that is good enough for it, check the answer, and escalate one tier up when something visibly goes wrong.

The router uses the platform's three model classes, at the same list prices as Part 2:

| Tier | Model | Price per 1M tokens (input / output) | Good at |
|---|---|---|---|
| Sarvam's own | **Sarvam 105B** | ₹29.28 / ₹73.20 | Indian languages, Hinglish, tagging, routine summaries |
| Open-weight (hosted on Sarvam) | **GLM-5.3** | ₹126 / ₹396 | Harder English documents and summaries |
| Frontier | **Claude Opus 5** | ₹480 / ₹2,410 | High-stakes review, the hardest reasoning |

The test traffic is a **BFSI contact centre**, the same segment as Part 3 Q7: disposition tagging, post-call summaries, KYC and document extraction, customer notices, voice turns and compliance review. 27 of the 40 test prompts are in Indian languages or Hinglish.

> **Honest caveat.** No API keys were available while this was built, so the three models are played by a seeded **simulator** with stated assumptions about each model's skill and speed (`router/backends.py`). The code to call the real models is included but was not run. What this proves is the **routing method and the measurement harness**, not a final savings number. Running on real models is one command once keys exist (see "How to run").

---

# Part 1: The router

## How it decides

**The policy in one paragraph.** If the request's use case is on the contract's pin list, it goes straight to the pinned model: voice goes to Sarvam 105B for speed, compliance review goes to Opus 5 for stakes. Otherwise the router reads the request and notes the task, the language and a 1–5 difficulty score. If those rules are unsure, it asks Sarvam 105B for a second opinion. It then looks up each model's chance of passing this kind of request, learned from a separate practice set, and sends the request to **the cheapest model whose chance clears the use case's quality bar**. After the answer comes back, quick checks look for a timeout, refusal, broken JSON or wrong language. If one fires, the request escalates one tier up, at most twice.

Think of it as a hospital triage desk. The senior surgeon (Opus) is not sent every cough.

**The quality bars and pins are contract terms**, the same ones in Part 3 Q3. They live in one table (`router/config.py`), so a customer can change them without touching code:

| Use case | Rule | Why |
|---|---|---|
| Disposition tagging | Bar 85% | High volume, low stakes |
| Call summary | Bar 85% | High volume, and the QA team samples them anyway |
| KYC / document extraction | Bar 90% | Errors flow into core systems |
| Customer notices (translation) | Bar 90% | Customer-facing, legal tone matters |
| Voice agent | **Pinned → Sarvam 105B** | Latency: a voice turn has 1.5 s, and routing overhead or a slow model breaks it |
| Compliance review | **Pinned → Opus 5** | Stakes: mis-selling, RBI complaints and AML are never downgraded |

## What each request logs

Every request writes one line with the route and the reason, the model, tokens, cost, latency, quality score and whether a fallback fired (`logs/router.jsonl`). Four real examples from the run:

| Request | Went to | Why (as logged) | Cost | Latency | Quality |
|---|---|---|---|---|---|
| Hinglish EMI-complaint summary | Sarvam 105B | "sarvam-105b p=0.91 ≥ 0.85, cheapest that clears the bar" | ₹0.011 | 1.2 s | 0.86 |
| English salary-slip extraction (nested JSON) | GLM-5.3 | "sarvam-105b p=0.60 < 0.90; glm-5.3 p=1.00 ≥ 0.90" | ₹0.055 | 2.0 s | 0.82 |
| Hindi voice turn (balance query) | Sarvam 105B | "pinned: voice_agent always goes to sarvam-105b" | ₹0.005 | 0.96 s | 0.92 |
| AML structuring review | Opus 5 | "pinned: compliance_review always goes to opus-5" | ₹0.61 | 6.8 s | 0.80 |

A fallback in action: on a Hinglish insurance-claim summary, Sarvam 105B **refused**. The router skipped GLM-5.3 (its chance on Hinglish was below the bar) and escalated to Opus 5, which answered. The log records `fallback_fired: true, fallback_reason: refusal`.

To see the reasoning for any prompt:
```bash
python3 route.py --use-case call_summary "Summarise this call in English. Customer: mera EMI do baar kat gaya, refund kab aayega?"
```

## What happens on a timeout or a refusal

| Problem | How it's spotted | What the router does |
|---|---|---|
| **Timeout** | No answer in 20 s (text) or within the 1.5 s voice budget | Escalate one tier up **if it can still finish in time**. If not (voice), return a graceful "let me connect you to an agent" and log it. Input tokens of the timed-out call are assumed billed. |
| **Refusal** | "I'm sorry, I can't…" at the start of the answer | Escalate one tier up: smaller models often refuse over-cautiously. **If Opus 5 also refuses, the refusal stands** and is flagged for human review, because that is usually a real policy line. |
| **Broken JSON** (extraction) | JSON doesn't parse | Escalate one tier up |
| **Wrong language** (asked for Tamil, got English) | Script check | Escalate one tier up |
| **Plausible but wrong answer** | **Can't be seen at run time** | Not caught. Only offline grading finds these (see "What the quality measure misses"). |

Fallbacks only ever go **up** a tier, never down.

## Results: 40 held-out prompts, three configurations

The test prompts were never used to tune the router. Each configuration was run 30 times with different random draws, and the averages are shown. The full output is in `results/summary.md`.

| Configuration | Cost per 1,000 requests | vs all-frontier | Typical wait (p50) | Slowest 5% (p95) | Pass rate |
|---|---|---|---|---|---|
| Always cheapest (Sarvam 105B) | ₹8 | 3% | 0.9 s | 3.0 s | 85% |
| Always frontier (Opus 5) | ₹234 | 100% | 2.3 s | 6.5 s | 87% |
| **Router** | **₹91** | **39%** | **0.9 s** | 6.5 s | **97%** |
| Router without the fallback safety net | ₹85 | 36% | 0.9 s | 5.9 s | 95% |

**Reading the table:**
1. **Same quality as frontier at 39% of the cost.** Leave out voice and both pass 96% of prompts. The router looks *better* overall only because Opus 5 is too slow for a 1.5 s voice turn: it passed 19% of voice prompts versus 100% for the router. That is exactly why voice is pinned to Sarvam.
2. **Always-cheapest is not the answer for English work.** Sarvam 105B passes 95% of Indian-language prompts but only 63% of English ones, mainly harder documents and compliance. That gap is why the open-weight tier exists.
3. **Indian-language traffic is where the money is.** On Indic and Hinglish prompts the router costs **19%** of frontier, versus 62% on English prompts.
4. **Where the traffic went:** 73% of requests to Sarvam 105B, 13% to GLM-5.3 and 14% to Opus 5, close to Part 2's 70 / 20 / 10 assumption.
5. **Typical wait drops from 2.3 s to 0.9 s, but the slowest 5% doesn't improve.** Those are compliance reviews, which are deliberately pinned to Opus. Routing speeds up the typical request, not the worst case.
6. **The fallback costs about 8% more (₹85 → ₹91 per 1,000) for about 2 points of pass rate.** For compliance-adjacent work that's worth it. For bulk tagging, a customer could switch it off.
7. **Forty prompts is a small sample.** The router's pass rate ranged from 90% to 100% across the 30 runs. A real pilot needs the bank's own 500+ graded prompts (Part 3 Q7).

**The router's own cost and latency** are included in every total. The rules take under 1 ms. The LLM second opinion didn't fire on this test set, because the rules were confident on every routed prompt. Real traffic will be messier, and Part 2 budgets ₹500 a month for it: at about ₹0.016 per check on Sarvam 105B, that covers roughly 30,000 checks a month.

**Cross-check with Part 2.** Part 2 assumes 70% of tokens go to Sarvam, 20% to GLM and 10% to Opus, and gets a 76% saving. On this test set Opus takes a bigger share of *tokens* (27%) than of *requests* (14%), because compliance reviews are long. Applying the test set's measured mix to 50M/10M tokens gives **₹16,700 a month, a 65% saving**. So the honest range is **65–76%**, depending on how much compliance-grade work the customer sends. The test set over-samples compliance on purpose (10% of prompts); a real contact centre sends far less.

## What the quality measure does *not* capture

- **In this submission quality is simulated.** The results reflect my assumptions about each model: Sarvam strongest on Indian languages, GLM on harder English, Opus best overall. They are not measurements. The strongest claims, such as "Sarvam beats frontier on Hinglish", need a live run.
- With real models, the automatic scoring checks the right label, the required JSON fields, required keywords and the right script. It misses:
  - **Tone and register.** A Hindi notice can be correct but use the wrong formality.
  - **Faithfulness.** A summary can hit every keyword and still invent a promise the agent never made. This is the most dangerous failure in a bank.
  - **Right answer, wrong reasoning** in compliance reviews.
  - **Business outcome:** whether the customer's issue got resolved or the QA analyst saved time.
- **Pass / fail at 0.7 is blunt.** A 0.69 and a 0.2 both count as "fail".
- **I wrote both the prompts and the classification rules**, so the rules' accuracy (61 of 64 tasks right) is optimistic.
- A real pilot fixes this with the bank's QA team blind-grading a sample (Part 3 Q7) and an LLM judge with a written rubric.

## Trade-offs considered and dropped

| Option | Why not |
|---|---|
| **A trained "black-box" router** (learns from thousands of past comparisons) | Needs data we don't have, and it can't explain a decision in a sentence. Banks and regulators need an audit trail. The lookup table can be swapped for one later. |
| **Always ask an LLM to classify** | Adds latency and cost to *every* request, which breaks voice. Rules go first; the LLM is asked only when they are unsure. |
| **Always try the cheapest model first, escalate on failure** | Doubles the wait on every hard request and can't catch answers that look fine but are wrong. |
| **An LLM judge checking every answer live** | Doubles cost and latency. Used offline on a sample instead. |
| **Cheapest open model as the bottom tier** (e.g. DeepSeek V4 Flash) | Cheaper per token, but in beta and a hard sell to BFSI and government buyers. Sarvam 105B is the bottom tier we own and can tune. |
| **Blending cost and quality into one score** | More "optimal" on paper, but "cheapest model that clears the bar" maps directly onto an SLA a customer can sign. |

## Scaling inside a customer VPC or an air-gapped rack

- **It's small and self-contained.** The router is a few hundred lines of Python with no outside libraries and no calls home. It runs as a small service in front of the models, and scaling means adding copies of it; the GPUs are the real cost.
- **Customer VPC:** Sarvam 105B and GLM-5.3 run inside the VPC. Opus 5 is reached over a private link only if the bank's policy allows it. A per-use-case "never leave the VPC" rule is one more column in the contract table.
- **Air-gapped:** there is no frontier API, so the top tier becomes the largest model on the rack. The policy stays the same; only the model list changes. Cost per token becomes GPU time per token, and routing frees GPUs for other workloads.
- **Staying calibrated without data leaving:** logs stay on-site. A monthly job re-scores a sample of the bank's own traffic, graded by their QA team, and updates the pass-rate table. Only aggregate pass rates change.
- **Controls banks will ask for:** per-use-case bars and pins, a full decision log, and a kill switch that pins everything to one model within minutes (Part 3 Q8).

## The data

All test data is **plain text in the repo**: one CSV file, [`data/prompts.csv`](data/prompts.csv), with 64 rows. It opens in Excel or Google Sheets.

- **40 held-out test prompts:** 10 disposition tagging, 10 call summaries, 7 KYC extractions, 5 voice turns, 4 customer notices and 4 compliance reviews. The languages are English, Hindi, Hinglish, Tamil, Bengali and Marathi.
- **24 calibration prompts:** the practice set the router learns its pass rates from, never used for testing.
- Each row has the prompt (what the router sees) and an answer key (`gold_*` columns: the true task, difficulty and how to score the answer). All names, numbers and accounts are invented.

## Assumptions

- Prices are the Part 2 list prices. Speeds (time to first word: Sarvam 350 ms, GLM 500 ms, Opus 1,100 ms) and failure rates are estimates. All of them are in `router/config.py`.
- Each model's skill in the simulator is my assumption: Sarvam strongest on Indian languages, GLM strongest on harder English, Opus best overall.
- Indian-language text is billed as more tokens on GLM and Opus than on Sarvam (the tokenizer effect). Part 2 conservatively ignores this.
- A voice turn has 1.5 s end to end. Timed-out calls bill input tokens only. "Pass" means quality ≥ 0.7.

## How to run

Python 3.9, nothing to install.
```bash
python3 calibrate.py     # learn pass rates from the 24 practice prompts
python3 evaluate.py      # run the 40 test prompts through all configurations → results/summary.md, logs/
python3 route.py --use-case kyc_extraction "Extract JSON with keys name, amount ..."   # explain one decision
```
For real models, set `SARVAM_*`, `OPEN_*` and `FRONTIER_*` (each `_BASE_URL`, `_API_KEY`, `_MODEL`; any OpenAI-compatible endpoint), then run `python3 calibrate.py --live && python3 evaluate.py --live`.

| File | What it does |
|---|---|
| `router/config.py` | Models, prices, quality bars and pins: every business assumption |
| `router/features.py` | Step 1: reads a request, works out task, language and difficulty |
| `router/estimator.py` | Each model's chance of passing, learned from the practice set |
| `router/policy.py` | Steps 2 and 3: pick the cheapest model over the bar, escalate on problems, log everything |
| `router/quality.py` | The run-time checks (drive fallbacks) and the offline scoring (drives the report) |
| `router/backends.py` | Real-model client and the simulator |
| `data/prompts.csv` | The 64 test and practice prompts |

---

# Part 2: The economics

**Customer:** 50 million input and 10 million output tokens a month.
**The three configurations** are the same three as in the Part 1 results: all-cheapest, all-frontier and routed.

## The four numbers

| Configuration | Monthly cost |
|---|---|
| All frontier (Claude Opus 5) | **₹48,100** |
| All cheapest (Sarvam 105B) | **₹2,196** |
| Routed (70% Sarvam / 20% GLM-5.3 / 10% Opus) | **₹11,304** |
| **Saving: routed vs all-frontier** | **76%** |

## How the routed number is built

| Line | Tokens | Cost |
|---|---|---|
| Sarvam 105B | 35M in + 7M out | ₹1,537 |
| GLM-5.3 | 10M in + 2M out | ₹2,052 |
| Opus 5 | 5M in + 1M out | ₹4,810 |
| Escalations (5% of volume re-run on Opus 5) | 2.5M in + 0.5M out | ₹2,405 |
| Router's classifier | about 30,000 second-opinion checks on Sarvam 105B | ₹500 |
| **Total** | | **₹11,304** |

## Assumptions

- **Prices per 1M tokens (input / output):** Sarvam 105B ₹29.28 / ₹73.20; GLM-5.3 ₹126 / ₹396; Opus 5 ₹480 / ₹2,410.
- **70 / 20 / 10 split by tokens,** in line with Part 1, where the router sent 73% / 13% / 14% of requests.
- **5% of tokens escalate** and are re-run on Opus 5. This is a deliberate buffer: Part 1 measured a 2% fallback rate.
- **The same token count on every model.** In reality Indian-language text uses fewer tokens on Sarvam's tokenizer, so this is conservative.
- **Why DeepSeek V4 Flash was left out:** it is cheaper (₹1,584 a month all-in), but it's in beta and a hard sell to BFSI and government buyers.

## Things a reviewer will ask

- **"All-Sarvam is ₹2,196. Why not just use that?"** Because quality drops where it matters. In Part 1, Sarvam alone passed 95% of Indian-language prompts but only 63% of English ones, mostly harder documents and compliance.
- **"All open-weight (GLM-5.3) is ₹10,260, about the same as routed. Why route?"** GLM-5.3 is in beta, it still misses the hardest 10% of queries, and it is weaker in Indian languages. Routing keeps frontier quality on the requests that need it. **The router is a quality floor, not just a cost cut.**
- **"How sure is the 76%?"** Applying Part 1's measured token mix to the same volumes gives ₹16,700, a 65% saving. Part 1's test set deliberately over-samples long compliance reviews that are pinned to Opus. **Honest range: 65–76%,** depending on how much compliance-grade work the customer sends.

---

# Part 3: Business questions

### 1. Pricing for a ₹2 crore a year BFSI account

**Pick: per-model pass-through with a platform margin.** The bank pays each routed model's rate plus our margin.

- **Trust.** Every call shows which model served it and what it cost (the Part 1 log). With a blended rate, a bank assumes we are quietly routing to cheap models.
- **No margin bleed.** If traffic shifts to complex fraud or legal work, revenue rises with cost, so Sarvam never absorbs a mix shift.
- **Chargeback.** KYC, collections, wealth and support can each be billed for exactly what they used.

**Illustrative maths:** everything on the frontier model would cost ₹3.5 Cr. Routing brings serving cost to about ₹1.35 Cr (39% of frontier, as measured in Part 1). With our margin the price is ₹2 Cr, so the bank saves ₹1.5 Cr and we keep about a third of revenue.

**Why not the others:** a blended rate breaks if frontier fallback runs at 40% instead of 10%. A subscription caps the upside as new departments come on. Outcome pricing means arguing every month over what counts as a "good summary".

### 2. Routing shrinks the tokens we bill. Build it anyway?

**Yes. Revenue per token falls, but profit and account size go up.**

- **If we don't, someone else will.** An open-source router or the bank's own team halves the bill, and we lose the account, not just the tokens.
- **Margin substitution.** Reselling frontier tokens earns a thin margin. Traffic routed to our own Indic models is where we make money.
- **Cheaper means more usage.** Call centres QA 2–5% of calls today. At a third of the cost they can summarise all of them, and use cases stuck on unit economics open up.
- **It makes VPC and air-gapped deployments work.** Most traffic stays local, and only exceptions go to the frontier model.
- **We own the switchboard.** Every model call runs through our gateway, which brings stickiness and visibility.

### 3. The router saves 55% but adds 120 ms at p95 and loses 3% on the hardest tenth. Wrong for whom, and what goes in the contract?

**Wrong for:**
- Real-time voice. A natural turn needs under about 800 ms end to end, and 120 ms on top of speech recognition and synthesis is noticeable.
- Real-time fraud and UPI screening, where transaction SLAs are tight.
- High-stakes judgement: credit decisions, legal and regulatory review, claims.
- Zero-error work such as clinical scribing or legal contract audits.

**In the contract:**
- **SLAs by workload.** Voice and compliance skip the router on fixed routes; Part 1 pins voice to Sarvam and compliance to Opus. Bulk work (summaries, KYC) accepts the 120 ms in exchange for the savings.
- **A quality floor on a test set the bank owns,** including its hardest 500 Hinglish queries. A breach triggers frontier fallback at Sarvam's cost until the router is recalibrated.
- **A pin list** of categories that always go to the frontier model.
- **Service credits** for quality or latency breaches, monthly routing reports, and rollback within hours.

### 4. "We will just send everything to the frontier model and eat the cost."

That works at today's volume, but the bill grows with every workload you add, and in Indian languages the frontier model often uses more tokens for output that is no better. Don't trust our router, test it: run it in shadow on a week of your traffic, have your team grade the results, and decide workload by workload. If the numbers don't hold, you've lost nothing and gained a benchmark in your own languages.

**First discovery question:** *"Which workloads have you shelved, or only sampled, because running them at full volume on the frontier model didn't pencil out?"* The real cost isn't the bill. It's the use cases they aren't running.

### 5. OpenRouter, Not Diamond, Martian and every hyperscaler offer routing. Where does Sarvam win and lose?

**Wins:**
- **Sovereign and air-gapped deployment.** Independent routers are cloud APIs, and hyperscalers route within their own catalogue. Neither runs inside a bank's rack.
- **Indic depth.** Our own models, Indian-language evaluations and cheaper tokenization mean routing can improve quality, not just cost.
- **We own the cheap tier.** We set its price and can fine-tune it per customer. A broker can do neither.
- **The full voice stack,** plus trust with government and regulators.

**Loses:**
- Breadth, and speed of access to new frontier models.
- Less cross-model traffic to learn routing from.
- Neutrality: we route to our own models, so customers may suspect our motives.
- Hyperscaler bundling: cloud commits and credits.
- English-only workloads.

**Win where language, sovereignty or deployment decides the deal. Don't fight for English-only, cloud-native traffic.**

### 6.

*(Question 6 was missing from the copy of the brief we worked from; to be added.)*

### 7. One Indian segment: first workload, week-two proof, path to ₹10 crore

**Segment:** BFSI contact centres, meaning collections and service at private banks and NBFCs.

**First workload:** post-call summaries and disposition tagging in Hinglish and regional languages. It is batch work, high volume, easy to measure, and today only sampled. Tagging and most summaries go to Sarvam 105B, harder English documents to GLM-5.3, and complaint and mis-selling reviews to Opus 5. This is exactly the traffic Part 1 was tested on.

**Week-two proof:**
- A shadow run on about 10,000 real calls.
- The bank's QA team blind-grades 500 routed outputs against frontier outputs, and they land within the agreed threshold.
- No compliance flags missed.
- A measured drop in cost per call.
- CISO sign-off on the deployment mode.

**To ₹10 Cr:**
- Go from sampled calls to 100% of calls, funded by the savings.
- Add voice agents, KYC and grievance workloads to take the anchor account from ₹2 Cr to ₹4 Cr.
- Partner with BPOs such as Firstsource, each serving several banks, to add three or four more ₹2 Cr accounts.

### 8. Six months in, quality quietly degrades on the customer's most valuable 5%, and users notice first. How do we keep them?

**Within 48 hours:**
- Own it, and don't debate the data.
- Pin that slice to the frontier model the same day; the Part 1 pin list makes this a config change.
- Credit back the savings on affected traffic.
- Hold a senior-level call, and deliver a written root cause within a week: model update, traffic drift, or new query types.

**Fix the system:**
- Monitor by segment, not by average, with a dashboard for the slice the customer defines as high-value.
- Keep shadow-grading a sample of routed high-value queries against the frontier model.
- Refresh the test set monthly and run regression tests before every update.
- Treat edits, escalations and repeat questions as alarms.
- Never downgrade the top 5% unless the customer opts in.

Customers don't churn over one incident. They churn when they find problems before you do. Share the same dashboard, and flag the next problem first.
