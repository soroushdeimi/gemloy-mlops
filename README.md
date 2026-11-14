# GPU Kubernetes platform

Start here. This repository defines a k3s GPU platform and a Python summarizer calling vLLM. It contains code and deployment instructions; nothing has been deployed by this work. The target is a native Ubuntu GPU agent with an RTX 3090 and a separate single control plane. The existing Windows/WSL service is a reference, not a cluster node.

## Quickstart

```sh
scripts/install-tools.sh
make test lint-k8s lint-rules lint-dashboards
.tools/bin/actionlint .github/workflows/ci.yml
docker build -t summarizer:local .
```

For local app development, activate `.tools/venv`, set `MODEL_URL` to a test model endpoint and run `uvicorn app.main:app --port 8080`. Tests mock the upstream and make no model requests. Example request for a future test environment:

```sh
curl http://localhost:8080/summarize -H 'Content-Type: application/json' \
  -d '{"text":"Kubernetes places workloads according to their resource requests."}'
```

Follow [GPU node join](docs/gpu-node-join.md) then [reproduce](docs/reproduce.md) for operator-run deployment. Replace the documented repository and registry examples before enabling GitOps. Never execute the node scripts on the current Windows/WSL host.

## Repository map

| Path | Purpose |
|---|---|
| `app/`, `tests/`, `Dockerfile` | Service, mocked upstream tests, non-root image |
| `deploy/charts/summarizer/` | App Helm chart, optional HPA and observability |
| `deploy/charts/vllm/` | Exclusive GPU deployment, persistent model cache |
| `deploy/manifests/app/` | Equivalent plain app manifests with kustomize |
| `deploy/*-values.yaml` | GPU Operator and monitoring Helm values |
| `scripts/node/` | Small operator-run native Ubuntu preparation scripts |
| `monitoring/` | GPU/model dashboards, DCGM monitor, platform alerts |
| `gitops/` | Root and child applications, desired values, sealed secret example |
| `loadtest/` | Explicit-target test driver; never run on the current host |
| `docs/` | Architecture, decisions, operations, evidence and limitations |

Read [architecture](docs/architecture.md), [design decisions](docs/design-decisions.md), [monitoring](docs/monitoring.md), [runbook](docs/runbook.md), [rollback](docs/rollback.md), [limitations](docs/limitations.md), and [MIG design](docs/mig.md).

## Assignment coverage

| Requirement | Implementation |
|---|---|
| Native GPU node preparation: driver, toolkit, k3s containerd runtime and agent join | `scripts/node/01-driver.sh` through `04-runtime.sh`; `docs/gpu-node-join.md` |
| GPU Operator Helm installation; preinstalled driver/toolkit ownership, device plugin, DCGM and GFD | `deploy/gpu-operator-values.yaml`; `gitops/apps/gpu-operator.yaml`; `docs/reproduce.md` |
| GPU labels, taint, workload selectors/tolerations and exclusive allocation | `scripts/node/03-join.sh`; `deploy/charts/vllm/templates/deployment.yaml`; `docs/gpu-node-join.md` |
| GPU verification with device inspection and CUDA vector addition | `deploy/manifests/gpu/verify.yaml`; `docs/gpu-node-join.md` |
| Pinned vLLM, verified quantized checkpoint, chat-completions endpoint | `deploy/charts/vllm/values.yaml`; `deploy/charts/vllm/templates/deployment.yaml`; `docs/design-decisions.md` |
| Serving flags, VRAM/KV budget, quantization and framework trade-offs | `docs/design-decisions.md`; `deploy/charts/vllm/values.yaml` |
| Persistent weights, conditional init download, optional secret, GPU resources, shared memory, probes and Recreate strategy | `deploy/charts/vllm/templates/`; `docs/design-decisions.md` |
| Prometheus/Grafana stack via Helm | `deploy/monitoring-values.yaml`; `gitops/apps/monitoring.yaml` |
| DCGM, model and app ServiceMonitors | `monitoring/dcgm-servicemonitor.yaml`; `deploy/charts/vllm/templates/servicemonitor.yaml`; `deploy/charts/summarizer/templates/servicemonitor.yaml` |
| GPU/model/app dashboards as sidecar-labelled ConfigMaps | `monitoring/dashboards/`; `monitoring/gpu-dashboard.yaml`; `monitoring/model-dashboard.yaml`; `deploy/charts/summarizer/templates/dashboard.yaml` |
| GPU temperature/memory/XID, model down/queue/KV, app errors/p95 alerts | `monitoring/rules.yaml`; `deploy/charts/summarizer/templates/rules.yaml` |
| Pinned metric names, queries and initial thresholds | `docs/monitoring.md`; `monitoring/dashboards/` |
| Python summarizer calling the model, validation, bounded retries and 502/504/422 mapping | `app/main.py`; `tests/test_app.py` |
| App liveness/readiness and request/latency/upstream/token metrics | `app/main.py`; `deploy/charts/summarizer/templates/deployment.yaml` |
| Non-root multi-stage slim image, mocked-upstream tests and ruff | `Dockerfile`; `tests/test_app.py`; `pyproject.toml`; `Makefile` |
| Plain app manifests with kustomize and configurable Helm chart | `deploy/manifests/app/`; `deploy/charts/summarizer/` |
| Model Helm chart and app HPA/monitor/rule/dashboard toggles | `deploy/charts/vllm/`; `deploy/charts/summarizer/values.yaml`; `deploy/charts/summarizer/templates/` |
| CI tests, chart/schema/rule/workflow validation | `.github/workflows/ci.yml`; `Makefile`; `scripts/check_rules.py`; `scripts/install-tools.sh` |
| GHCR image build/publish with SHA and semver tags; desired-image promotion | `.github/workflows/ci.yml`; `gitops/values/summarizer.yaml` |
| Argo CD app-of-apps: monitoring, GPU Operator, model, app and observability | `gitops/root.yaml`; `gitops/apps/`; `docs/reproduce.md` |
| Sealed Secrets controller and example-only ciphertext handling | `gitops/apps/sealed-secrets.yaml`; `gitops/secrets/hf-token.example.yaml`; `docs/reproduce.md` |
| Argo history rollback, Git revert and native Helm rollback | `docs/rollback.md` |
| Architecture diagram, repository map, quickstart and reproduction | `README.md`; `docs/architecture.md`; `docs/gpu-node-join.md`; `docs/reproduce.md` |
| Trade-offs, monitoring overview, real screenshot capture slots, runbook and limitations | `docs/design-decisions.md`; `docs/monitoring.md`; `docs/images/README.md`; `docs/runbook.md`; `docs/limitations.md` |
| Optional: direct streaming model load test, app target, concurrency sweep and recommendation | `loadtest/run.py`; `loadtest/README.md`; `tests/test_loadtest.py` |
| Optional: app autoscaling plus queue-based model scaling proposal | `deploy/charts/summarizer/templates/hpa.yaml`; `gitops/values/summarizer.yaml`; `docs/scaling.md` |
| Optional: two-model MIG placement on future supported multi-GPU hardware | `docs/mig.md` |
