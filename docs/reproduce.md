# Reproduce the platform

All cluster commands below are for the operator's future test environment. No live deployment was performed. Tool versions are reproducibility selections, not measured capacities: Helm 3.17.3, kubeconform 0.6.7, kustomize 5.6.0, promtool 3.2.1 and actionlint 1.7.7. `scripts/install-tools.sh` installs tools under ignored `.tools/`; Python dependencies are pinned. Binary downloads use HTTPS release URLs; digest verification is an additional supply-chain improvement listed in limitations.

1. Run the README local gates. Review the app Dockerfile and build the image for `linux/amd64` before publishing to the chosen GHCR repository. The image runs as an unprivileged user. No publishing was executed here.
2. Complete [GPU node preparation](gpu-node-join.md) and its CUDA test. Keep vLLM stopped while the test owns the GPU.
3. Configure GitOps identity: replace `https://github.com/EXAMPLE/gemloy-mlops.git` in all `gitops/` Applications with the operator's repository URL. Replace `ghcr.io/EXAMPLE/gemloy-mlops` in `gitops/values/summarizer.yaml` and the chart/plain image example with the built image path. Values in CI derive the actual lower-case repository name. Review Argo repository credentials through your secret-management process for private repositories. No remotes or credentials have been created by this work.
4. Install Argo CD using the site's approved installation and configure its repository access. Bootstrap is intentionally manual. Apply `gitops/root.yaml` to the test cluster. Root reconciliation creates monitoring, sealed-secrets, GPU Operator, observability, vLLM and summarizer children. Automated child sync and self-heal are enabled. Sync waves express order but are not a readiness dependency across Applications: explicitly wait for monitoring CRDs and GPU Operator health before syncing observability and model children. Disable auto-sync during initial commissioning if necessary.
5. Optional HF token: fetch the Sealed Secrets public certificate for this cluster, then seal a locally supplied token. The following reads it without embedding it in shell history; do not enable shell tracing:

   ```sh
   read -rs HF_TOKEN
   export HF_TOKEN
   python3 - <<'PY' | kubeseal --controller-name sealed-secrets --controller-namespace kube-system --format yaml > /tmp/hf-token.sealed.yaml
   import base64, json, os
   print(json.dumps({"apiVersion":"v1", "kind":"Secret", "metadata":{"name":"hf-token", "namespace":"platform"}, "data":{"token":base64.b64encode(os.environ["HF_TOKEN"].encode()).decode()}}))
   PY
   unset HF_TOKEN
   ```

   Review only the ciphertext output, then place it in a separately configured GitOps secrets path or apply it to the test namespace. `gitops/secrets/hf-token.example.yaml` is intentionally outside the synced child directory and is not valid ciphertext. Never sync the example. Back up the controller sealing keys securely outside Git; ciphertext is bound to name, namespace and controller keys.
6. Confirm the cache PVC binds on the GPU node. The init container downloads the pinned revision only when its successful-download marker is missing. A failed download resumes on retry. Main serving uses the local directory with hub access disabled. Wait for startup, then inspect model logs for actual memory and KV token capacity before testing `/health` and completion behavior.
7. Check all three monitors as active Prometheus targets. Grafana dashboard UID for the default Prometheus datasource is `prometheus`; adjust dashboard datasource UIDs if the site's installation differs. Take real screenshots using [monitoring](monitoring.md).
8. Use [runbook](runbook.md) for functional validation and [load test](../loadtest/README.md) for an explicitly approved test endpoint. Evaluate latency, queue and memory before enabling traffic.

## Manual Helm alternative

Use this instead of Argo ownership, never concurrently for the same resources:

```sh
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm repo update
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version 69.8.2 -n monitoring --create-namespace -f deploy/monitoring-values.yaml --wait
helm upgrade --install sealed-secrets sealed-secrets/sealed-secrets --version 2.17.2 -n kube-system
helm upgrade --install gpu-operator nvidia/gpu-operator --version v25.3.0 \
  -n gpu-operator --create-namespace -f deploy/gpu-operator-values.yaml --wait
kubectl apply -k monitoring -n monitoring
helm upgrade --install vllm deploy/charts/vllm -n platform --create-namespace --timeout 35m
helm upgrade --install summarizer deploy/charts/summarizer -n platform \
  -f gitops/values/summarizer.yaml --wait
```

The model Helm timeout is a proposed startup allowance plus five minutes (30 + 5 = 35 minutes); initialization download time is variable and may require more. The plain alternative is `kubectl apply -k deploy/manifests/app`; remove the Helm app release first and supply its image tag through a kustomize image override. Plain manifests include the app monitor, alerts and dashboard; their base is kept equivalent to default chart rendering.

Chart versions in GitOps pin inputs. Driver and toolkit patches follow the installed package repositories; record them at commissioning. Upgrades require checking chart support matrices and CRD changes. CI validates local resources without installing upstream charts or running inference.

## Pipeline behavior

Pull requests validate only. Main pushes validate, build and publish a full git-SHA image; semver tag pushes additionally publish the version without its `v` prefix. The dependent bump job updates the GitOps app image on main only after a successful publish and commits it with a skip marker. Repository permissions must allow the workflow bot to push main; protected-branch installations should use a reviewed change workflow instead. The built commit and desired-state commit differ intentionally. GitOps values use the immutable SHA tag; no floating image tag is promoted.
