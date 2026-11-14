#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 && ${WSL_DISTRO_NAME:-} == k8s-test ]] || { echo 'Run as root only in k8s-test'; exit 1; }
grep -qi microsoft /proc/version || exit 1
[[ -e /dev/dxg && -x /usr/lib/wsl/lib/nvidia-smi ]] || { echo 'Windows GPU bridge is missing'; exit 1; }
# The Windows driver owns the GPU. Never install a Linux display driver in WSL.
/usr/lib/wsl/lib/nvidia-smi
install -d -m 0755 /usr/share/keyrings
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' > /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update
apt-get install -y nvidia-container-toolkit
printf '%s\n' /usr/lib/wsl/lib > /etc/ld.so.conf.d/wsl-nvidia.conf
ldconfig
if ! command -v nvidia-smi >/dev/null 2>&1; then
  ln -s /usr/lib/wsl/lib/nvidia-smi /usr/local/bin/nvidia-smi
fi
