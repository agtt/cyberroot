#!/bin/bash
# Explicit optional-tool prerequisites; root inside the guest only, never on the host.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
case "${1:-}" in
  engine)
    apt-get update -q
    apt-get install -y --no-install-recommends uidmap dbus-user-session slirp4netns fuse-overlayfs
    loginctl enable-linger agent
    systemctl start "user@$(id -u agent).service"
    ;;
  shannon)
    apt-get update -q
    apt-get install -y --no-install-recommends nodejs unzip
    ;;
  strix|kali) exit 0 ;;
  *) echo 'Unknown optional tool.' >&2; exit 2 ;;
esac
apt-get clean
