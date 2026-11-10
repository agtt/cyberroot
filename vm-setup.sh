#!/bin/bash
# Runs as root inside the VM (cyber sync). $1 = opencode version or "latest", $2 = idle shutdown minutes (0 = off).
set -euo pipefail
WANT="$1"
case "$(uname -m)" in aarch64|arm64) ARCH=arm64 ;; *) ARCH=x64 ;; esac
PKG="cli-linux-$ARCH"
if [[ "$WANT" == latest ]]; then WANT="$(curl -fsSL "https://registry.npmjs.org/@opencode/$PKG/latest" | jq -r .version)"; fi
HAVE="$(/usr/local/bin/opencode --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)"
if [[ "$HAVE" != "$WANT" ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL "https://registry.npmjs.org/@opencode/$PKG/-/$PKG-${WANT}.tgz" | tar -xz -C "$tmp"
  install -m 755 "$tmp/package/bin/opencode" /usr/local/bin/opencode
  rm -rf "$tmp"
  echo "opencode ${HAVE:-none} -> $WANT"
fi
install -d -o agent -g agent -m 700 /home/agent/.config /home/agent/.config/opencode /home/agent/.secrets
install -d -o agent -g agent -m 755 /home/agent/work

# --- Preinstalled tools, so tasks do not download them again (APK analysis) ---
export DEBIAN_FRONTEND=noninteractive
if ! command -v java >/dev/null || ! command -v apktool >/dev/null; then
  apt-get update -q >/dev/null
  apt-get install -y --no-install-recommends default-jre-headless apktool >/dev/null
fi
JADX_VER=1.5.1
if [[ ! -x /opt/jadx-$JADX_VER/bin/jadx ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/jadx.zip" "https://github.com/skylot/jadx/releases/download/v$JADX_VER/jadx-$JADX_VER.zip"
  install -d -m 755 "/opt/jadx-$JADX_VER"
  unzip -qo "$tmp/jadx.zip" -d "/opt/jadx-$JADX_VER"
  chmod 755 "/opt/jadx-$JADX_VER/bin/jadx"
  ln -sfn "/opt/jadx-$JADX_VER/bin/jadx" /usr/local/bin/jadx
  rm -rf "$tmp"
  echo "jadx $JADX_VER installed"
fi

# --- Disk: caches must not grow (apt archives/lists, journal) ---
apt-get clean >/dev/null 2>&1 || true
rm -rf /var/lib/apt/lists/* 2>/dev/null || true
install -d -m 755 /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=50M\n' > /etc/systemd/journald.conf.d/ailab.conf
systemctl restart systemd-journald >/dev/null 2>&1 || true
systemctl enable --now fstrim.timer >/dev/null 2>&1 || true

# --- Idle auto-shutdown: counts minutes while user "agent" has no process ---
install -d -m 755 /etc/ai-lab
echo "${2:-15}" > /etc/ai-lab/idle-min
cat > /usr/local/sbin/ailab-idle <<'EOF'
#!/bin/bash
lim="$(cat /etc/ai-lab/idle-min 2>/dev/null || echo 15)"
[ "$lim" -gt 0 ] 2>/dev/null || exit 0
f=/run/ailab-idle
# the opencode background service (serve --service) does not count as work
if pgrep -u agent -a | grep -vq "opencode serve --service"; then echo 0 > "$f"; exit 0; fi
n=$(( $(cat "$f" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$f"
[ "$n" -ge "$lim" ] && systemctl poweroff
exit 0
EOF
chmod 755 /usr/local/sbin/ailab-idle
cat > /etc/systemd/system/ailab-idle.service <<'EOF'
[Unit]
Description=ai-lab idle shutdown check
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ailab-idle
EOF
cat > /etc/systemd/system/ailab-idle.timer <<'EOF'
[Unit]
Description=ai-lab idle shutdown check (every minute)
[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now ailab-idle.timer >/dev/null 2>&1
