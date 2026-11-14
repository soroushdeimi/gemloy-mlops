#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
. /etc/os-release
[[ $ID == ubuntu && ( $VERSION_ID == 22.04 || $VERSION_ID == 24.04 ) ]] || exit 1
if grep -qi microsoft /proc/version; then echo 'Use native Ubuntu, not WSL'; exit 1; fi
apt-get update
apt-get install -y linux-headers-"$(uname -r)" nvidia-driver-580
printf '%s\n' 'Reboot if the loaded driver differs, then run nvidia-smi.'
