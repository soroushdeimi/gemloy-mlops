# Join the GPU node

Operator-run procedure for native Ubuntu 22.04 or 24.04, bare metal or dual boot. These OS versions and the single-agent topology are assignment choices. No script here has been executed on hardware. Review outbound repository access, OS backups, Secure Boot signing, DNS, clock synchronization, swap policy and private connectivity before starting. Keep join tokens outside Git.

1. Prepare the separate CPU control plane. Install pinned k3s `v1.32.3+k3s1` (a reproducibility choice, not the reference host's version):

   ```sh
   curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.32.3+k3s1 sh -s - server --disable traefik
   ```

   Retain local-path and metrics-server. Restrict the API, kubelet and overlay network to trusted node addresses; consult [k3s requirements](https://docs.k3s.io/installation/requirements) for ports. Securely place the server's agent token in a root-readable file on the GPU node using the operator's approved process. Do not paste it into shell history or this repo. Use the full secure token, which includes the CA hash. Protect kubeconfigs similarly.

2. On the native Ubuntu GPU node run `sudo scripts/node/01-driver.sh`. It rejects WSL, installs the Ubuntu driver branch and matching kernel headers. Branch 580 is a proposed compatibility baseline; exact package patch follows the selected Ubuntu repository. If unavailable, configure the vendor's signed driver repository rather than falling back silently. Reboot after driver/kernel changes and verify `nvidia-smi`. Resolve module signing under Secure Boot before continuing. Do not install Linux GPU drivers inside WSL.

3. Run `sudo scripts/node/02-toolkit.sh`. The script installs the signed NVIDIA repository and toolkit once per desired package state. Confirm `/usr/bin/nvidia-container-runtime` exists. Driver and toolkit versions must be recorded by the operator and checked against the container's CUDA requirement using the [compatibility guide](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html). Driver installation is not delegated to GPU Operator.

4. Join manually (the token-file path is an operator-created local file):

   ```sh
   sudo env K3S_URL=https://CONTROL_PLANE:6443 K3S_TOKEN_FILE=/root/k3s-agent-token \
     scripts/node/03-join.sh
   sudo scripts/node/04-runtime.sh
   ```

   Join registers both labels and `nvidia.com/gpu=present:NoSchedule`. Re-running preserves an existing service, so changing URL/token/labels later requires reviewing its existing service configuration. For an already joined node, use the following operator commands:

   ```sh
   kubectl label node GPU_NODE nvidia.com/gpu.present=true node-role.gemloy/gpu=true --overwrite
   kubectl taint node GPU_NODE nvidia.com/gpu=present:NoSchedule --overwrite
   ```

5. Validate the k3s containerd runtime configuration. Unlike a standalone containerd install, do not run `nvidia-ctk runtime configure` against `/etc/containerd/config.toml`: k3s renders its own configuration. Installing the runtime before joining lets k3s discover it. The runtime script restarts the agent and checks `/var/lib/rancher/k3s/agent/etc/containerd/config.toml` for the runtime binary. Check `kubectl get runtimeclass nvidia -o yaml`. k3s supplies this RuntimeClass on supported versions. The effective handler must resolve to `nvidia-container-runtime`.

   For an environment where detection fails, inspect the service PATH first. If an explicit template is necessary, extend the k3s base template at `/var/lib/rancher/k3s/agent/etc/containerd/config-v3.toml.tmpl` for containerd v2, rather than replacing its entire config:

   ```toml
   {{ template "base" . }}
   [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.nvidia]
     runtime_type = "io.containerd.runc.v2"
   [plugins.'io.containerd.cri.v1.runtime'.containerd.runtimes.nvidia.options]
     BinaryName = "/usr/bin/nvidia-container-runtime"
     SystemdCgroup = true
   ```

   Only add this when the base does not already define `nvidia`; duplicate TOML tables fail startup. Restart the agent and inspect its journal. For older containerd configurations, the plugin prefix differs; this template is deliberately scoped to the pinned k3s series. See [k3s containerd and alternative runtimes](https://docs.k3s.io/advanced).

6. Install monitoring CRDs first, then GPU Operator with [values](../deploy/gpu-operator-values.yaml), using [reproduce](reproduce.md). Driver/toolkit are disabled; device plugin, DCGM exporter and GFD are enabled. Operator DaemonSets and NFD tolerate the GPU taint. The operator namespace may need privileged Pod Security admission; apply that only to its namespace. Verify discovery and allocation:

   ```sh
   kubectl get node GPU_NODE --show-labels
   kubectl describe node GPU_NODE
   kubectl get pods -n gpu-operator -o wide
   ```

   Expect one allocatable `nvidia.com/gpu` from the physical card; this is the requested exclusive allocation policy. GFD's discovery labels complement the custom role label. A label alone does not expose a resource.

7. Before deploying the model, run the GPU verification Job:

   ```sh
   kubectl create namespace platform --dry-run=client -o yaml | kubectl apply -f -
   kubectl apply -f deploy/manifests/gpu/verify.yaml
   kubectl wait -n platform --for=condition=complete job/gpu-verify --timeout=300s
   kubectl logs -n platform job/gpu-verify -c nvidia-smi
   kubectl logs -n platform job/gpu-verify -c vector-add
   kubectl delete -n platform job/gpu-verify
   ```

   The [catalogued CUDA sample](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/k8s/containers/cuda-sample) container uses its published default entrypoint for vectorAdd after a CUDA base-image init container runs `nvidia-smi`. Both containers request the same exclusive GPU sequentially. Both must exit successfully and the sample must report its test passed. The 300-second wait is a proposed five-minute image-pull/test budget, not a measured execution time. The sample image execution must be verified when pulling it on the real node; no sample image was downloaded during local checks. Delete the Job before model sync so it releases the only GPU.

8. Deploy vLLM and confirm readiness, allocation, metrics and an authorized test completion. Record driver/toolkit versions, container digest, model revision, allocator memory, load time, temperature and sample output. Do not migrate traffic until this commissioning evidence exists.

## WSL boundary

The reference Windows 11 + WSL2 host currently serves a Windows CUDA executable. CUDA containers can work in WSL, but NVML and `nvidia-smi` features are limited. NVIDIA's [WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html) explicitly uses the Windows driver. GPU Operator and DCGM exporter support on WSL2 is limited; their complete installation, discovery, scheduling and telemetry on this host are **not verified**. In particular do not assume DCGM temperature, memory and XID metrics are available. Native Ubuntu is required for this proposed procedure; it is not a script for converting the running WSL service.
