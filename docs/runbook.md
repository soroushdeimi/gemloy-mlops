# Runbook

Commands in this document are for the future test cluster, never the current host deployment. Start with `kubectl get pods -n platform -o wide`, pod events, Argo health and Prometheus targets. Do not print token Secrets or request bodies into incident logs.

| Symptom | Inspect and act |
|---|---|
| GPU pod Pending | Describe pod events, labels, taints, RuntimeClass and node allocatable GPUs. The verification Job or an old model pod may own the sole resource. Do not enable GPU sharing to bypass the conflict. |
| GPU resource absent | Inspect GPU Operator device-plugin/GFD logs, native host `nvidia-smi`, agent runtime config and node driver health. Confirm driver/toolkit ownership remains disabled in Operator. |
| Init stuck | Inspect init logs, HF repository/revision access, DNS, package-index access and PVC disk space. A marker is created only on success. Do not delete the PVC to fix a transient fetch failure. |
| Model OOM at load | Capture allocator budget and cache capacity from startup logs. Compare with the design budget; reduce context as documented before retrying. Eager execution is already enabled. Persistent weight-size failure needs a model-budget review. |
| Model readiness fails | Inspect `/health`, process logs, probe timings, GPU faults and memory. Startup allowance applies after download, not during init. Repeated liveness restarts can conceal a load or kernel failure. |
| App returns 502 | Check upstream connection and HTTP failures, model Service endpoints and app upstream-error counters. Exhausted retries or malformed upstream content map here. |
| App returns 504 | Inspect model queue, prompt length and latency; read timeouts are not retried. Connection failures retry at most three times; see design decisions. |
| Queue or KV alert | Stop increasing concurrency. Reduce input/output budgets, inspect long requests, compare running requests to configured sequence cap, and follow the scaling proposal. |
| GPU temperature/memory alert | Inspect native host cooling, external GPU consumers and allocator use. Model allocation alone can produce high framebuffer use; interpret with KV occupancy. Pause traffic for sustained thermal faults. |
| XID fault | Record fault code and native kernel logs. Drain workload before driver recovery or reboot; use vendor diagnostics. A nonzero code is not an event count. |
| Missing dashboards or metrics | Check sidecar label, datasource UID, monitor namespace/Service selectors and named ports, then Prometheus target discovery. Missing consumer-card DCGM fields require documenting telemetry gaps. |

## Commissioning checks

```sh
kubectl rollout status deployment/vllm -n platform --timeout=35m
kubectl rollout status deployment/summarizer -n platform
kubectl get servicemonitors,prometheusrules -A
kubectl get endpoints -n platform
kubectl logs -n platform deployment/vllm -c vllm --tail=100
```

Use a port-forward in the authorized test environment to verify app `/healthz`, `/readyz`, `/metrics` and a short `/summarize` request. Compare prompt/completion usage to app token counters; inject a test-only upstream failure and check 502/504 and the upstream-error counter. Verify model metric families and labels against the pinned contract, then take screenshots. Do not expose model or app Services publicly during this check.

Confirm an ordinary CPU pod without the GPU toleration cannot land on the GPU node, while the verification Job and model can. Confirm HPA has metrics-server input and CPU requests. Run model load and restart tests before allowing application traffic. Record observed cold-load time and replace the proposed probe budget if needed.

Back up Argo configuration, sealed-secret controller keys and any irreplaceable state using the site's encrypted backup process. Model weights are reconstructable from the pinned repository revision while it remains available; local-path is not a backup. Recovery from GPU-node loss requires rescheduling storage or restoring the cache on a replacement node with equivalent labels.

Use [rollback](rollback.md) for a bad release. Avoid manual edits under self-heal: reconciliation will overwrite them.
