#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .tools/bin
system=$(uname -s | tr '[:upper:]' '[:lower:]')
case $(uname -m) in arm64|aarch64) arch=arm64;; x86_64) arch=amd64;; *) exit 1;; esac
fetch_tar() {
  local url=$1 dir=$2
  mkdir -p "$dir"
  curl --fail --location --connect-timeout 15 --max-time 60 --retry 2 "$url" | tar -xz -C "$dir"
}
if [[ ! -x .tools/bin/helm ]]; then
  fetch_tar "https://get.helm.sh/helm-v3.17.3-$system-$arch.tar.gz" .tools/helm
  cp ".tools/helm/$system-$arch/helm" .tools/bin/helm
fi
if [[ ! -x .tools/bin/kubeconform ]]; then
  fetch_tar "https://github.com/yannh/kubeconform/releases/download/v0.6.7/kubeconform-$system-$arch.tar.gz" .tools/kubeconform
  cp .tools/kubeconform/kubeconform .tools/bin/
fi
if [[ ! -x .tools/bin/kustomize ]]; then
  fetch_tar "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.6.0/kustomize_v5.6.0_${system}_${arch}.tar.gz" .tools/kustomize
  cp .tools/kustomize/kustomize .tools/bin/
fi
if [[ ! -x .tools/bin/promtool ]]; then
  fetch_tar "https://github.com/prometheus/prometheus/releases/download/v3.2.1/prometheus-3.2.1.$system-$arch.tar.gz" .tools/prometheus
  cp ".tools/prometheus/prometheus-3.2.1.$system-$arch/promtool" .tools/bin/
fi
if [[ ! -x .tools/bin/actionlint ]]; then
  fetch_tar "https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_${system}_${arch}.tar.gz" .tools/actionlint
  cp .tools/actionlint/actionlint .tools/bin/
fi
python_bin=''
for candidate in .tools/python/*/bin/python3.12 .tools/python/bin/python3.12; do
  if [[ -x $candidate ]] && "$candidate" -c 'import sys; assert sys.version_info[:2] == (3, 12)' 2>/dev/null; then
    python_bin=$candidate
    break
  fi
done
if [[ -z $python_bin ]] && command -v python3.12 >/dev/null 2>&1; then
  python_bin=$(command -v python3.12)
fi
if [[ -z $python_bin ]]; then
  echo 'Python 3.12 is required in .tools/python or on PATH.' >&2
  exit 1
fi
if ! .tools/venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 12)' 2>/dev/null; then
  "$python_bin" -m venv --clear .tools/venv
fi
.tools/venv/bin/python -m pip install --cache-dir .tools/pip-cache -r requirements-dev.txt
