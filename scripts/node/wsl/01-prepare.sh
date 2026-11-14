#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 && ${WSL_DISTRO_NAME:-} == k8s-test ]] || { echo 'Run as root only in k8s-test'; exit 1; }
grep -qi microsoft /proc/version || exit 1
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || exit 1
apt-get update
apt-get install -y python3 curl gpg ca-certificates
python3 - <<'PY'
import configparser
from pathlib import Path
path = Path('/etc/wsl.conf')
config = configparser.ConfigParser()
config.read(path)
if not config.has_section('boot'):
    config.add_section('boot')
config.set('boot', 'systemd', 'true')
with path.open('w') as output:
    config.write(output)
PY
printf '%s\n' 'From Windows terminate only k8s-test, then reopen it to activate systemd.'
