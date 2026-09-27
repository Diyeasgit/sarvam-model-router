# Part 1 results (SIMULATED, 30 seeds x 40 held-out prompts)

| Policy | Cost per 1,000 requests | vs frontier | p50 latency | p95 latency | Mean quality | Pass rate | Fallback rate |
|---|---|---|---|---|---|---|---|
| always-cheapest (Sarvam 105B) | ₹8.16 | 3% | 913 ms | 2984 ms | 0.80 | 85% | 0.0% |
| always-frontier (Opus 5) | ₹234.43 | 100% | 2348 ms | 6540 ms | 0.79 | 87% | 0.0% |
| router | ₹91.46 | 39% | 918 ms | 6478 ms | 0.88 | 97% | 2.2% |
| router, no fallback | ₹84.68 | 36% | 938 ms | 5851 ms | 0.86 | 95% | 0.0% |

## By language

| Segment | Frontier ₹/1k | Router ₹/1k | Router vs frontier | Pass rate: cheapest / frontier / router |
|---|---|---|---|---|
| English | ₹339.37 | ₹209.18 | 62% | 63% / 89% / 95% |
| Indian languages + Hinglish | ₹183.90 | ₹34.78 | 19% | 95% / 86% / 98% |

## By use case (router)

| Use case | Rule | Where the router sent it | Router ₹/1k | Pass rate: frontier / router |
|---|---|---|---|---|
| disposition_tagging | bar 85% | sarvam-105b 99%, glm-5.3 1% | ₹2.01 | 97% / 100% |
| call_summary | bar 85% | sarvam-105b 66%, glm-5.3 29%, opus-5 4% | ₹47.29 | 97% / 94% |
| kyc_extraction | bar 90% | sarvam-105b 56%, glm-5.3 30%, opus-5 15% | ₹57.67 | 99% / 97% |
| customer_notices | bar 90% | sarvam-105b 99%, glm-5.3 1% | ₹6.91 | 98% / 100% |
| voice_agent | pinned → sarvam-105b | sarvam-105b 100% | ₹3.57 | 19% / 100% |
| compliance_review | pinned → opus-5 | opus-5 100% | ₹679.07 | 88% / 91% |

## Router details

- Share of requests by final model: sarvam-105b 73%, opus-5 14%, glm-5.3 13%
- Share of tokens by model (incl. fallback re-runs): sarvam-105b 51%, opus-5 27%, glm-5.3 21%
- Router's own cost, included above: ₹0.000 per 1,000 requests (0% of router spend)
- Router's own latency: under 1 ms for the rules; the LLM classifier fired on 0% of requests, adding a median 0 ms on those
- Requests still failing a check after all fallbacks: 0.6%

## Cross-check against Part 2 (50M input + 10M output tokens a month)

- All frontier: ₹48,100
- Routed, using the token mix measured on this test set (sarvam-105b 51%, glm-5.3 21%, opus-5 27%): ₹16,700, saving 65%

## Seed-to-seed range (40-prompt run)

- always-cheapest (Sarvam 105B): cost ₹0.304–₹0.347, pass rate 72%–92%
- always-frontier (Opus 5): cost ₹7.928–₹10.131, pass rate 80%–92%
- router: cost ₹2.955–₹4.319, pass rate 90%–100%
- router, no fallback: cost ₹2.532–₹4.013, pass rate 88%–100%
