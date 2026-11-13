# Real API usage before the ledger (reconstructed 2026-11-13, no API calls made)

From `data/sessions/*/traces.jsonl`, `eval/results/faults-v*/faults.json` and pytest temp traces. List prices (no prompt caching): Sonnet 5.5 $2/$10 per MTok, Opus 5.5 $4/$20.

| Source | Real calls | Model | Input tokens | Output tokens | Est. USD |
|---|---|---|---|---|---|
| Pipeline runs (95 sessions) | 1,225 billed + 11 rejected (credit) | claude-sonnet-5-5 | 5,715,667 | 533,630 | 16.77 |
| Fault injection v1 + v2 | 309 | claude-sonnet-5-5 | 1,133,139 | 93,286 | 3.20 |
| Grader in run_eval (not traced then) | ≈160 | claude-opus-5-5 | unknown | unknown | ≈4–10 (estimate) |
| E3 leaks from pytest (now fixed) | 4 billed + 4 rejected | claude-sonnet-5-5 | 6,108 | 778 | 0.02 |
| Connection test | 1 | claude-sonnet-5-5 | 397 | 49 | 0.00 |
| **Total** | ≈1,700 billed | | | | **≈25–30** |

No Deepgram calls. From now on every real call is gated by `SCRIBE_ALLOW_REAL=1` and appended to `data/api_ledger.jsonl`.
