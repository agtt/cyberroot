#!/bin/bash
# Prepares a VPS as an ai-lab target (Ubuntu/Debian). Runs as root, safe to re-run.
# `cyber target vps <ssh-host>` + `cyber up` sends it automatically.
#
# The model runs as user "agent" (no sudo). agent's egress to private networks and cloud metadata
# (169.254.169.254) is blocked; internet egress is open and shows the VPS IP.
# The rule only applies to agent: root/ssh/system traffic is untouched, so you keep access to the VPS.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends ca-certificates curl wget git jq ripgrep unzip file \
  less procps python3 python3-pip python3-venv build-essential dnsutils whois openssl \
  netcat-openbsd nmap ncat nftables sudo
for p in sqlmap ffuf gobuster whatweb hydra nikto; do apt-get install -y --no-install-recommends "$p" || echo "skip $p"; done

id agent >/dev/null 2>&1 || useradd -m -s /bin/bash agent
gpasswd -d agent sudo >/dev/null 2>&1 || true
install -d -o agent -g agent -m 755 /home/agent/work

cat > /usr/local/sbin/ailab-agent-fw <<'EOF'
#!/bin/bash
set -euo pipefail
nft -f - <<'NFT'
table inet ailab_agent
delete table inet ailab_agent
table inet ailab_agent {
  chain out {
    type filter hook output priority filter; policy accept;
    meta skuid != "agent" accept
    oifname "lo" accept
    ct state established,related accept
    ip daddr { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 169.254.0.0/16, 172.16.0.0/12,
               192.0.0.0/24, 192.168.0.0/16, 198.18.0.0/15, 224.0.0.0/3 } counter drop
    ip6 daddr { fc00::/7, fe80::/10, ff00::/8 } counter drop
  }
}
NFT
EOF
chmod 755 /usr/local/sbin/ailab-agent-fw

cat > /etc/systemd/system/ailab-agent-fw.service <<'EOF'
[Unit]
Description=ai-lab agent egress firewall
After=network-pre.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/ailab-agent-fw
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now ailab-agent-fw.service
systemctl restart ailab-agent-fw.service

touch /var/lib/ailab-provisioned
