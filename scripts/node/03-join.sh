#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || exit 1
: "${K3S_URL:?Set control plane HTTPS URL}"
: "${K3S_TOKEN_FILE:?Set path to root-only agent token file}"
[[ -r $K3S_TOKEN_FILE ]] || exit 1
if ! systemctl cat k3s-agent.service >/dev/null 2>&1; then
  curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.32.3+k3s1 sh -s - agent \
    --server "$K3S_URL" --token-file "$K3S_TOKEN_FILE" \
    --node-label node-role.gemloy/gpu=true \
    --node-label nvidia.com/gpu.present=true \
    --node-taint nvidia.com/gpu=present:NoSchedule
fi
systemctl enable --now k3s-agent
