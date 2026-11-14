# Monitoring

Prometheus discovers ServiceMonitors across namespaces and selects all rules. App and model Services expose a named `http` port; the DCGM monitor selects `app=nvidia-dcgm-exporter` in `gpu-operator` and port `gpu-metrics`. Confirm these labels and port against the installed Operator's Service during commissioning. GPU Operator's own monitor is disabled to prevent duplicate scraping. ConfigMaps carry `grafana_dashboard: "1"`; the stack sidecar searches all namespaces.

## vLLM metric contract

Names checked against the [v0.25.0 metric definitions](https://github.com/vllm-project/vllm/blob/v0.25.0/vllm/v1/metrics/loggers.py). These use `model_name` and `engine` labels. Counters exported by the Python client acquire `_total`; histogram series acquire `_bucket`, `_sum` and `_count`.

| Exported name | Meaning |
|---|---|
| `vllm:generation_tokens_total` | Output tokens counter |
| `vllm:prompt_tokens_total` | Prefill tokens counter |
| `vllm:e2e_request_latency_seconds` | End-to-end latency histogram |
| `vllm:time_to_first_token_seconds` | TTFT histogram |
| `vllm:request_time_per_output_token_seconds` | Per-request time per output token histogram |
| `vllm:inter_token_latency_seconds` | Inter-token histogram, distinct from per-request mean |
| `vllm:num_requests_running` | Running requests gauge |
| `vllm:num_requests_waiting` | Waiting queue gauge |
| `vllm:kv_cache_usage_perc` | Used KV block fraction, bounded from zero to one |

The model dashboard shows throughput, running/waiting, KV fraction and latency percentiles. App panels show request status rates, latency, upstream errors and tokens. GPU panels show temperature, utilization, framebuffer and XID fault code. DCGM field support on this consumer card must be checked: absent metrics do not mean a healthy GPU.

## Initial policies and calculations

These are proposed operational thresholds, not measured production SLOs. Scrape period 15 seconds gives four samples per minute; rate windows of five minutes provide about twenty samples. A five-minute sustained alert therefore reduces transient startup/prefill noise. Retention is one week = seven days; 20 GiB Prometheus disk is a proposed reservation (roughly 20 / 7 = 2.86 GiB per day maximum before overhead). Grafana disk is one quarter of that reservation = 5 GiB. Actual series churn determines required capacity.

| Alert | Threshold and reasoning |
|---|---|
| GPU temperature high | 80 C for five minutes: initial operator policy, not a vendor maximum; tune to hardware cooling |
| GPU memory near full | Used / (used + free) > 0.95, leaving less than 24 × 0.05 = 1.2 GiB |
| XID fault | Nonzero reported XID code for one minute; a code is a fault indicator, not an event counter, so no counter rate is used |
| Model down | `up == 0` or absent for two minutes (eight scrape intervals) |
| Queue high | More than two waiting for five minutes: exceeds one configured batch |
| KV high | Fraction > 0.90 for five minutes, leaving less than one tenth of available blocks |
| App error rate | Server errors / all summarize requests > 0.05 for five minutes: initial 95% success policy; denominator clamp 0.001 prevents division by zero |
| App p95 latency | More than 30 seconds for five minutes: initial budget = request deadline / 6 |

The histogram percentile is calculated as `histogram_quantile(0.95, sum by (le)(rate(..._bucket[5m])))`. App alerts and panels filter `/summarize` so probes do not hide errors or bias latency. Alert routing and notification receivers require site-specific configuration; rules alone do not page an operator.

## Screenshots after deployment

The placeholders in [images](images/README.md) are Markdown capture instructions, not screenshots. After deploying to the test environment, collect `gpu.png`, `model.png`, and `app.png` with real traffic, a visible time range, target status, and the relevant dashboard. Record driver/container/model versions alongside the captures. Never fabricate telemetry or images. Dashboard JSON parsing and rule syntax checks do not validate real metric availability.
