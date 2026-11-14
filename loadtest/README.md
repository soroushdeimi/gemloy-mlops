# Explicit-target load test

Run only after deployment to an approved test environment. The URL and target are mandatory; no load test has been run against a real model, current host, public endpoint or cluster during implementation. Tests use local fixtures and mocked transports.

Direct vLLM streaming sweep:

```sh
.tools/venv/bin/python loadtest/run.py --target model --url http://VLLM:8000 \
  --concurrency 1,2,4 --requests 10
```

App sweep:

```sh
.tools/venv/bin/python loadtest/run.py --target app --url http://TEST_SUMMARIZER:8080 \
  --concurrency 1,2,4 --requests 10
```

The model target sends `/v1/chat/completions` with alias `gemma4-summary`, streaming enabled and `stream_options.include_usage=true`. It requests a final usage event rather than estimating tokens from text. TTFT measures time until the first nonempty content or reasoning delta; role-only events do not count. Missing usage, malformed/incomplete streams, transport failures and unsuccessful HTTP status codes count as failures. The app target sends `/summarize`, reads `completion_tokens` from its response and reports TTFT as null because that endpoint does not stream.

Each level prints one JSON object with concurrency, request count, failure count, median/p95 successful request latency, median TTFT and aggregate output tokens/second. P95 uses nearest rank: sorted latencies at index ceil(0.95 × successful requests) − 1. Latency and TTFT begin after acquiring the local concurrency slot and include upstream queue time. Throughput = sum of successful response completion-token usage / total level wall time, including all request rounds and failures. Partial failed responses contribute no tokens. There are no retries or warm-up requests; include separate warm/cold runs before drawing capacity conclusions. An all-failed level has null latencies and zero throughput.

## Recommendation rule

Supply positive, strictly increasing concurrency levels. Requests per level must be at least the highest concurrency. The first level is the fallback recommendation only if it has zero failures and positive throughput. A subsequent level qualifies only if it and the immediately preceding level both have zero failures and its aggregate output tok/s is at least 1.10 times the preceding level's positive throughput. The final `recommended concurrency` line reports the highest qualifying level, retaining the baseline if no higher level qualifies. If there is no valid baseline or qualifying level, it prints `unavailable`.

This is an adjacent-level rule: a plateau does not stop the sweep, and a later level can qualify against its own preceding level. It is a throughput recommendation, not a latency SLO guarantee; review TTFT and tail latency before adopting it. Any failed request causes a nonzero process exit after all levels are reported, even if another level qualifies. The 10% threshold is the requested improvement policy: (current − previous) / previous ≥ 0.10. For example, rates 100, 110 and 120 tok/s at concurrency one, two and four recommend two: 110 / 100 = 1.10, while 120 / 110 ≈ 1.091.

Ten requests is a proposed smoke sample = five rounds at concurrency two, not a benchmark-sized experiment. Output cap 128 is one quarter of the app maximum 512. The request timeout is the existing 180-second test budget, not a measured completion time. The sweep levels one, two and four deliberately compare baseline, the current active-stream count, and twice that count.

## Existing capacity evidence

Start future commissioning at concurrency two based on **measured on the current llama.cpp host deployment**: useful aggregate throughput about 176 tok/s with two active streams and `--parallel 2`; more callers queued. Source: measurements from the existing single-host llama.cpp deployment (operator notes, not part of this repo). An approximately 179 tok/s aggregate sample with four callers still had only two active streams; it is not evidence for four simultaneous generating slots.

The older single-stream figure about 132 tok/s comes from a previous operator's single-sample benchmark under another configuration, **measured on the current llama.cpp host deployment**, with weaker evidence than the later observed production test. The later production table reports 110 aggregate and 119 per-running-stream tok/s for one caller. Do not combine these into a claimed vLLM speedup. A nominal 176 / 132 = 1.33 ratio compares different configurations; it is not a controlled improvement result. All these numbers are measurements from the existing single-host llama.cpp deployment (operator notes, not part of this repo).

Watch queue, TTFT, error rate, GPU memory and temperature throughout the future sweep. Record counted prompt/output tokens, model revision and engine settings. Include long prompts and warm/cold cache experiments before setting service capacity. The app input limit counts characters rather than tokens; the model context cap remains authoritative.
