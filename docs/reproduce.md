# Reproduce the platform

All cluster commands are for the operator's authorized test environment; no deployment was performed during implementation. The default is llama.cpp with the existing GGUF inside a **new** WSL2 Ubuntu 24.04 distro. Follow [test-env-wsl.md](test-env-wsl.md) for the exact snapshot, stop, prepare, staged deployment, verification and restore sequence. No weight download is needed or authorized by that test sequence.

Tool versions are reproducibility selections: Helm 3.17.3, kubeconform 0.6.7, kustomize 5.6.0, promtool 3.2.1 and actionlint 1.7.7. `make tools` locates Python 3.12 and installs tooling inside ignored `.tools/`; the Makefile uses explicit tool paths. Local checks require no cluster:

```sh
make tools test lint-k8s lint-rules lint-dashboards
.tools/bin/actionlint .github/workflows/ci.yml
```

## Default staged WSL smoke test

Use the full steps in test-env-wsl.md. The deployment order is standalone NVIDIA device plugin, CUDA verification Job (delete it afterward), monitoring with the WSL toleration overlay, llama.cpp chart, then summarizer. Use the existing file mounted at `/mnt/d/gemma/bench/models`; byte size is 16,947,541,728. Set `gitops/values/llamacpp.yaml` node name only if the new test-node identity differs from the preparation script. Inspect GPU startup logs and health before any completion/load test.

The WSL smoke procedure uses Helm releases for explicit staging. It does not concurrently apply Argo Applications to the same resources. CPU services receive the WSL profile tolerations because there is only one tainted node. GPU Operator and DCGM are not part of that test path. Empty GPU panels are expected until supported telemetry is demonstrated.

## GitOps deployment path

1. Replace example repository URLs in `gitops/` with the actual repository URL, and confirm `gitops/values/summarizer.yaml` points to an accessible built image. Do not reset existing values or use a floating tag. Configure private repository/registry access through the site's secret-management process.
2. Prepare the selected node topology. Default active infrastructure is the experimental standalone device plugin on WSL2. Native Ubuntu remains documented in gpu-node-join.md. For infrastructure or engine alternatives use **only** [engines.md](engines.md); do not add a second model Application.
3. Bootstrap Argo CD using the site's approved installation. For the single-node WSL cluster apply `deploy/argocd-wsl-values.yaml` to its Helm installation so all components tolerate the GPU taint. Do not publish Argo/Grafana publicly during the test.
4. Apply `gitops/root.yaml`. Its nonrecursive `gitops/apps` source includes monitoring, sealed-secrets, standalone device plugin, observability, **one** model Application selecting llama.cpp, and summarizer. The alternative vLLM/GPU Operator Applications live outside that source. Monitor the initial sync carefully: waves are not cross-Application readiness dependencies. Keep the model child paused until the GPU Job has passed and released its allocation; wait for monitoring CRDs before custom monitors/rules. Child auto-sync/self-heal settings can be paused during commissioning, with parent reconciliation paused to preserve that pause.
5. Confirm the bound read-only PV/PVC, file-check init output, model `/health`, app readiness and a short completion. Verify only one model Deployment and one model Service. See test-env-wsl.md for local port-forwards and explicit-target load testing. Check the actual ServiceMonitor label/port selectors and dashboard datasource UID `prometheus`.
6. Capture real screenshots after traffic. App and llama.cpp targets should work if commissioning succeeds; DCGM on WSL is not assumed. Keep the vLLM dashboard/rules as inactive alternative resources; the down alert checks whether the corresponding Deployment is desired.

Sealed Secrets controller is included, with WSL tolerations. The example in `gitops/secrets` is deliberately outside synced paths and is not valid ciphertext. Default GGUF serving uses no HF token. For a separately authorized vLLM cache workflow, seal any required token with this cluster's certificate and name/namespace binding; never write plaintext credentials to Git. Back up controller keys outside Git. No real secret was created during this work.

## Native alternative and rollback

The native topology uses the GPU Operator values, preinstalled driver/toolkit and separate CPU control plane from gpu-node-join.md. The engine choice remains independent; a native test of the existing GGUF needs a pre-existing read-only path and matching PV node affinity. vLLM retains its checkpoint revision, cache initialization and memory budget as an alternative, not an active second GPU consumer. Its weight fetch requires separate authorization; the WSL smoke path never fetches weights.

Rollback details are in rollback.md, with engine changes centralized in engines.md. Existing GGUF files are never altered by chart initialization or release rollback. HostPath PV/PVC objects are retained on uninstall; explicitly review their lifecycle before another claim is bound. Helm does not restore disk contents or reverse CRD migrations.

## Pipeline behavior

Pull requests validate only. Main pushes validate all three local charts, app/load-test tests, rules and JSON, then build/publish the app image with its git SHA. Semver tag events also publish version tags. The dependent main-branch promotion job changes only the app image repository/tag, preserving context/tolerations and other values. Bot permissions and protected-branch policy remain operator setup. No publish, commit, push, remote creation or cluster reconciliation was executed by this work.
