# WSL2 test environment: operator-only steps

These steps are a proposed test path on the same Windows 11 PC, using a **new** Ubuntu 24.04 distribution named `k8s-test`. No command here has been run on that PC. The existing service must release the RTX 3090 before any test GPU workload starts. No weights are downloaded or modified. Stop at any failed gate and follow restoration below.

GPU Operator is not supported for this WSL2 path and is excluded from active GitOps. DCGM exporter is likely unavailable or incomplete; GPU temperature, XID and framebuffer telemetry are **not verified** and are not required to appear as healthy zeroes. The standalone NVIDIA device plugin is an experiment: its NVML discovery and resource allocation under WSL2 are **not verified**. CUDA container support does not establish Kubernetes device-plugin support. If allocation fails, do not bypass `nvidia.com/gpu` requests or claim success; collect logs and restore the existing service.

## Exact sequence

1. **Inventory and snapshot before changing anything.** In Windows PowerShell record `wsl --version`, `wsl --list --verbose`, Windows driver information, the running model executable/version and its launch flags. The known serving configuration is build `10850-f114f91f9`, total context 262144, two slots, and all layers on GPU; measured on the current llama.cpp host deployment. Confirm the model file without opening/copying its contents:

   ```powershell
   Get-Item 'D:\gemma\bench\models\gemma-4-26B-A4B-it-UD-Q4_K_M.gguf' | Select-Object Name,Length
   ```

   Expected length is 16,947,541,728 bytes. Choose an external encrypted backup location and record the existing distro name and supervisor units locally, without putting them in this repository:

   ```powershell
   $ExistingDistro = Read-Host 'Existing serving distribution'
   $BackupDir = Read-Host 'Existing encrypted backup directory'
   $ManagedUnits = (Read-Host 'Space-separated model, gateway, watchdog and boot supervisor units').Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
   Copy-Item "$env:USERPROFILE\.wslconfig" "$BackupDir\wslconfig.before" -ErrorAction SilentlyContinue
   foreach ($Unit in $ManagedUnits) {
       wsl.exe -d $ExistingDistro -u root -- systemctl show $Unit --property=ActiveState,UnitFileState
   }
   wsl.exe --export $ExistingDistro "$BackupDir\serving-before.tar"
   ```

   Treat the export as sensitive and crash-consistent if services were running. Record active/enabled states and retain existing executable/configuration backups in the encrypted location, never in Git. Do not print environment files or credentials. Identify Windows scheduled tasks or other auto-restart mechanisms and record their exact prior enabled/running state. Do not proceed without a restoration plan for every supervisor.

2. **Quiesce the existing deployment.** Enter its documented maintenance mode if available. Disable only the recorded watchdog/boot/task mechanisms that could restart the model, then stop the recorded gateway/model units:

   ```powershell
   $StopUnits = @($ManagedUnits)
   [Array]::Reverse($StopUnits)
   foreach ($Unit in $StopUnits) {
       wsl.exe -d $ExistingDistro -u root -- systemctl stop $Unit
   }
   ```

   Use the operator's recorded scheduled-task controls for any Windows launcher. Verify the old model process has exited and GPU memory is released with Windows `nvidia-smi`. Do not kill unrelated GPU processes. A second export after stopping provides a consistent recovery point if needed. Starting the test while the old backend remains resident is prohibited.

3. **Prepare the new distro.** Review and run `scripts/node/wsl/00-create.ps1` from Windows PowerShell. It creates only `k8s-test` using Ubuntu 24.04, explicitly selects WSL2 for that distro and requires a WSL version supporting [named installation](https://ubuntu.com/wsl/docs/stable/tutorials/develop-with-ubuntu-wsl/). Finish first-user setup with `wsl -d k8s-test`. Put a checkout of this repository in the new distro's Linux filesystem. Do not share its mutable state with the existing serving distro.

   `.wslconfig` is global to WSL. Review the backup before any manual edit. A proposed test budget is `memory=24GB` and `swap=8GB`: the documented 32 GB host minus an 8 GB Windows reserve gives 24 GB; swap is a proposed safety buffer, not GPU memory. This is a proposal, not an automatic script change. Existing networking settings should be preserved unless the operator explicitly chooses otherwise. Applying global changes requires `wsl --shutdown`, which stops **all** distros: only do so after the serving deployment is safely stopped. NVIDIA's [WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html) requires the Windows GPU driver; never install a Linux display driver here.

4. **Enable systemd and install toolkit, inside the new distro only:**

   ```sh
   sudo env WSL_DISTRO_NAME="$WSL_DISTRO_NAME" scripts/node/wsl/01-prepare.sh
   ```

   In Windows run `wsl --terminate k8s-test`, reopen it, and confirm systemd is PID 1. Then:

   ```sh
   sudo env WSL_DISTRO_NAME="$WSL_DISTRO_NAME" scripts/node/wsl/02-toolkit.sh
   ```

   Expect `/dev/dxg`, `/usr/lib/wsl/lib/nvidia-smi`, and the injected WSL driver libraries. The script exposes `/usr/lib/wsl/lib` to the loader and installs only Container Toolkit. If the GPU bridge is absent, stop and fix Windows/WSL setup before k3s.

5. **Install the single-node test cluster:**

   ```sh
   sudo env WSL_DISTRO_NAME="$WSL_DISTRO_NAME" scripts/node/wsl/03-k3s.sh
   mkdir -p "$HOME/.kube"
   sudo install -o "$(id -u)" -g "$(id -g)" -m 600 /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
   kubectl get nodes
   kubectl get runtimeclass nvidia
   ```

   The pinned k3s install names the new test node `gpu-test`, matching the chart's PV affinity. Runtime installation precedes k3s so its containerd config discovers `nvidia-container-runtime`. Check the effective config under `/var/lib/rancher/k3s/agent/etc/containerd/`; do not edit its rendered output. The script patches CoreDNS, metrics-server and local-path-provisioner tolerations **before** applying the GPU taint. Single-node CPU workloads require the matching WSL overlay; this intentionally differs from native GPU-only node isolation. Reapplying labels/taints is safe; an existing k3s installation with different node identity requires operator review rather than automatic replacement.

6. **Deploy the standalone plugin and verify allocation before loading a model:**

   ```sh
   helm repo add nvdp https://nvidia.github.io/k8s-device-plugin
   helm repo update
   helm upgrade --install nvidia-device-plugin nvdp/nvidia-device-plugin --version 0.17.1 \
     -n gpu-system --create-namespace -f deploy/nvidia-device-plugin-values.yaml --wait
   kubectl describe node gpu-test
   kubectl logs -n gpu-system daemonset/nvidia-device-plugin --all-containers --tail=100
   kubectl create namespace platform --dry-run=client -o yaml | kubectl apply -f -
   kubectl apply -f deploy/manifests/gpu/verify.yaml
   kubectl wait -n platform --for=condition=complete job/gpu-verify --timeout=300s
   kubectl logs -n platform job/gpu-verify -c nvidia-smi
   kubectl logs -n platform job/gpu-verify -c vector-add
   kubectl delete -n platform job/gpu-verify
   ```

   Confirm one allocatable GPU and successful CUDA sample output. These are expected test outcomes, not verified facts. The plugin uses the `nvidia` RuntimeClass, envvar device selection and fail-on-init-error; the pinned upstream chart injects compute/utility driver capabilities. NVML can still fail on WSL2. If any check fails, do not deploy the model. The five-minute Job wait is a proposed image-pull/test allowance.

7. **Deploy monitoring, then the GGUF engine and app.** This staged smoke path uses native Helm ownership. Do not also apply the Argo root to these same resources. See reproduce.md for the separate GitOps path and engines.md for the single-engine policy.

   ```sh
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm repo update
   helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
     --version 69.8.2 -n monitoring --create-namespace \
     -f deploy/monitoring-values.yaml -f deploy/monitoring-wsl-values.yaml --wait
   kubectl apply -k monitoring -n monitoring
   helm upgrade --install llamacpp deploy/charts/llamacpp -n platform \
     -f gitops/values/llamacpp.yaml --wait --timeout 35m
   helm upgrade --install summarizer deploy/charts/summarizer -n platform \
     -f gitops/values/summarizer.yaml --wait
   kubectl logs -n platform deployment/llamacpp -c verify-weights
   kubectl logs -n platform deployment/llamacpp -c llamacpp --tail=100
   ```

   The PV binds the existing `/mnt/d/gemma/bench/models` directory on `gpu-test`, read-only. The init container checks the configured filename and exact byte size. No download fallback exists. Directory absence fails the volume mount; missing/wrong-size file produces a clear init error. Inspect actual GPU offload, context/slot allocation and startup memory before traffic. The 35-minute Helm allowance is the 30-minute startup probe budget plus five minutes; it is not a measured load time. If the pinned Linux image cannot reproduce the Windows host's memory fit, stop and restore rather than silently reducing the requested production context.

8. **Verify health, app completion and the explicit model load test.** In separate local shells inside the test distro:

   ```sh
   kubectl port-forward -n platform service/model 8000:8000
   kubectl port-forward -n platform service/summarizer 8080:8080
   ```

   Use only these local test forwards:

   ```sh
   curl --fail http://localhost:8000/health
   curl --fail http://localhost:8080/readyz
   curl --fail http://localhost:8080/summarize -H 'Content-Type: application/json' \
     -d '{"text":"Kubernetes schedules a workload according to resource requests.","max_tokens":128}'
   .tools/venv/bin/python loadtest/run.py --target model --url http://localhost:8000 \
     --concurrency 1,2,4 --requests 10
   ```

   Install only local test tooling first via `make tools` if needed. Save real measurements outside Git until reviewed. Confirm Prometheus has app/model targets; DCGM may have no target or no supported fields. Capture actual app and llama.cpp dashboards into `docs/images/`, plus GPU telemetry only if genuinely available. Record the time range and versions. Do not fabricate GPU panels or infer health from absent metrics.

9. **Restore the original deployment even if the test fails.** End port-forwards, export reviewed test results, uninstall the test app/model releases and stop the test cluster:

   ```sh
   helm uninstall summarizer -n platform
   helm uninstall llamacpp -n platform
   sudo systemctl stop k3s
   ```

   Retained PV/PVC objects contain no copied weights; the original file remains read-only and unchanged. In Windows terminate only `k8s-test`, verify its GPU processes are gone, restore the recorded `.wslconfig` if changed, and perform any necessary global restart while the original service remains stopped. Re-enable only the supervisors/tasks that were enabled before, exit the original maintenance mode, and start the original model before its gateway and watchdogs. Use the recorded unit dependency order and original commands/configuration, not test aliases. From the same Windows PowerShell session, use the recorded original states and dependency order:

   ```powershell
   wsl.exe --terminate k8s-test
   # Restore only if a previous configuration existed and was changed for the test.
   if (Test-Path "$BackupDir\wslconfig.before") {
       Copy-Item "$BackupDir\wslconfig.before" "$env:USERPROFILE\.wslconfig"
   }
   $RestartUnits = (Read-Host 'Previously active units in original start dependency order').Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
   foreach ($Unit in $RestartUnits) {
       wsl.exe -d $ExistingDistro -u root -- systemctl start $Unit
   }
   ```

   Restore recorded task/unit enabled states and maintenance mode using the original service procedure before reopening traffic. If there was no original `.wslconfig`, remove only a file created by this test after reviewing it; if a global WSL restart is required, perform it before starting the units. Verify the original local health, expected GPU memory and one operator-authorized completion before reopening its traffic. Compare against the snapshot and preserve the test failure evidence. Do not unregister or overwrite the original distro.
