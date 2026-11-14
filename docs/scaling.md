# Scaling proposal

Default engine is llama.cpp. Use `llamacpp:requests_deferred` as its queue signal; the existing KEDA fragment below is for the retained vLLM alternative. Neither scaler is deployed. The single-node WSL profile adds app tolerations but creates no additional GPU capacity.

App HPA is included and enabled in GitOps values; chart defaults keep it optional. The initial range is one to three replicas (baseline plus two spare CPU replicas), targeting 70% of requested CPU so 30% remains as an initial headroom policy. A 300-second scale-down stabilization window equals five minutes. These are proposed settings, not measured capacity. HPA helps parsing, HTTP connection handling and availability but cannot increase model throughput. CPU is imperfect for an async proxy: later add in-flight or request-rate metrics based on measured app saturation.

The current llama.cpp configuration has two active streams. Begin the future test environment at concurrency two, then measure vLLM independently; see loadtest/README.md. More app replicas must not be interpreted as more model capacity. Add ingress admission limits and queue deadlines when exposing the service.

## Model queue scaling

Keep model replicas fixed at one on the current card. Each model pod reserves one exclusive GPU; another replica on this node would stay Pending. Do not attach an HPA or KEDA scaler to this Deployment until more GPU capacity exists. Local-path PVCs are node-bound and cannot be shared across independent GPU replicas.

For a future GPU pool, use KEDA's Prometheus scaler with a Deployment per checkpoint and a separate cache per replica/node (or suitable shared read-only model storage). Proposed trigger:

```yaml
triggers:
  - type: prometheus
    metadata:
      serverAddress: http://kube-prometheus-stack-prometheus.monitoring:9090
      metricName: model_waiting
      query: sum(vllm:num_requests_waiting{model_name="gemma4-summary"})
      threshold: "2"
      activationThreshold: "0"
```

This is a design fragment, deliberately not an active ScaledObject. Target queue threshold equals one batch of two requests. Scale only after sustained demand, respect available GPU count, and include load time in capacity planning. Keep a warm baseline replica; scale-to-zero would remove the very metric source needed to observe demand. A load balancer's external queue metric is needed if zero replicas is a goal. Use queue age, TTFT and KV occupancy together to distinguish prefill pressure from decode saturation. A shared queue or routing layer is needed to avoid hot replicas while others are idle. No vLLM throughput or startup-time guarantee has been measured here.
