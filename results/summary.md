# Results (simulated, 30 seeds x 40 held-out prompts)

| Policy | Cost / 1k req (USD) | Cost / 1k req (INR) | vs frontier | p50 latency | p95 latency | Mean quality | Pass rate | Fallback rate |
|---|---|---|---|---|---|---|---|---|
| always-cheapest | $0.0135 | ₹1.19 | 1% | 417 ms | 1274 ms | 0.551 | 42.3% | 0.0% |
| always-frontier | $1.7987 | ₹158.28 | 100% | 2278 ms | 7529 ms | 0.824 | 90.9% | 0.0% |
| router | $0.9566 | ₹84.18 | 53% | 1067 ms | 7261 ms | 0.846 | 90.7% | 3.8% |
| router-no-fallback | $0.8841 | ₹77.80 | 49% | 1061 ms | 6812 ms | 0.830 | 88.8% | 0.0% |

## By language segment

| Policy | Segment | Cost / 1k req | p95 | Pass rate |
|---|---|---|---|---|
| always-cheapest | english | $0.0141 | 1324 ms | 51.9% |
| always-cheapest | indic_or_mixed | $0.0130 | 1158 ms | 33.7% |
| always-frontier | english | $2.1250 | 8178 ms | 91.8% |
| always-frontier | indic_or_mixed | $1.5034 | 6041 ms | 90.2% |
| router | english | $1.4963 | 7932 ms | 91.4% |
| router | indic_or_mixed | $0.4684 | 5275 ms | 90.0% |
| router-no-fallback | english | $1.4508 | 7932 ms | 89.6% |
| router-no-fallback | indic_or_mixed | $0.3715 | 4188 ms | 88.1% |

## Router details

- Final-model mix: sarvam-indic 43%, frontier 28%, llama-3.1-8b 22%, llama-3.3-70b 7%
- Router overhead (LLM classifier calls), included above: $0.00110 per 1k requests
- Requests ending with an unresolved issue (timeout/refusal after all fallbacks): 3.2%

## Seed-to-seed range (cost per 40-prompt run, pass rate)

- always-cheapest: $0.0005-$0.0006, pass 28%-60%
- always-frontier: $0.0630-$0.0783, pass 82%-98%
- router: $0.0272-$0.0481, pass 82%-98%
- router-no-fallback: $0.0257-$0.0407, pass 78%-100%
