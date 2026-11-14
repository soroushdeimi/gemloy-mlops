#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || exit 1
command -v nvidia-container-runtime >/dev/null
# k3s detects the installed runtime on startup and renders containerd's CRI config.
systemctl restart k3s-agent
config=/var/lib/rancher/k3s/agent/etc/containerd/config.toml
grep -q 'nvidia-container-runtime' "$config" || { echo 'Runtime detection failed; see docs/gpu-node-join.md'; exit 1; }
