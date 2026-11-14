#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 && ${WSL_DISTRO_NAME:-} == k8s-test ]] || { echo 'Run as root only in k8s-test'; exit 1; }
grep -qi microsoft /proc/version || exit 1
[[ $(ps -p 1 -o comm=) == systemd ]] || { echo 'Enable systemd and reopen the test distro first'; exit 1; }
command -v nvidia-container-runtime >/dev/null
if ! systemctl cat k3s.service >/dev/null 2>&1; then
  curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.32.3+k3s1 sh -s - server \
    --disable traefik --node-name gpu-test \
    --node-label nvidia.com/gpu.present=true --node-label node-role.gemloy/gpu=true
fi
systemctl enable --now k3s
# Re-render k3s-owned containerd config after runtime installation; never edit its output.
systemctl restart k3s
grep -q 'nvidia-container-runtime' /var/lib/rancher/k3s/agent/etc/containerd/config.toml || { echo 'NVIDIA runtime detection failed; inspect k3s PATH and journal'; exit 1; }
k3s kubectl wait --for=condition=Ready node/gpu-test --timeout=180s
k3s kubectl label node gpu-test nvidia.com/gpu.present=true node-role.gemloy/gpu=true --overwrite
# A single tainted node also hosts CPU infrastructure in this test profile.
patch='{"spec":{"template":{"spec":{"tolerations":[{"key":"nvidia.com/gpu","operator":"Equal","value":"present","effect":"NoSchedule"}]}}}}'
for name in coredns local-path-provisioner metrics-server; do
  k3s kubectl patch deployment "$name" -n kube-system --type=strategic -p "$patch"
done
k3s kubectl taint node gpu-test nvidia.com/gpu=present:NoSchedule --overwrite
k3s kubectl get runtimeclass nvidia
