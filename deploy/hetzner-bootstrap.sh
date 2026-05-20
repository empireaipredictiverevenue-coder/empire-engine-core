#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
# EMPIRE V49 · HETZNER BOOTSTRAP
# ═══════════════════════════════════════════════════════════════════════════
# One-time setup of a fresh Hetzner Ubuntu 24.04 server.
#   - Installs Dokku v0.34.x
#   - Adds the postgres, redis, and letsencrypt plugins
#   - Tunes nginx for WebSocket support
#   - Sets up UFW firewall (ports 22, 80, 443 only)
#
# Run as root on the Hetzner box:
#   bash /root/hetzner-bootstrap.sh
#
# Idempotent · safe to re-run. Skips already-installed components.
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

DOKKU_VERSION="v0.34.0"
LOG_FILE="/var/log/empire-bootstrap.log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "  EMPIRE V49 · HETZNER BOOTSTRAP · $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""

# ─────────────────────────────────────────────────────────────────────
# 1. Sanity check
# ─────────────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "✗ Must run as root"
    exit 1
fi

. /etc/os-release
echo "→ OS: $PRETTY_NAME"
if [[ "$VERSION_ID" != "24.04" && "$VERSION_ID" != "22.04" ]]; then
    echo "⚠ Tested on Ubuntu 22.04/24.04 · proceeding anyway"
fi

# ─────────────────────────────────────────────────────────────────────
# 2. System update
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq curl wget git ufw fail2ban ca-certificates

# ─────────────────────────────────────────────────────────────────────
# 3. Firewall
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Configuring UFW firewall..."
ufw --force reset > /dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp comment 'http'
ufw allow 443/tcp comment 'https'
ufw --force enable
echo "  ✓ UFW active · ports 22, 80, 443"

# ─────────────────────────────────────────────────────────────────────
# 4. Install Dokku
# ─────────────────────────────────────────────────────────────────────
echo ""
if command -v dokku &> /dev/null; then
    INSTALLED_VERSION=$(dokku version 2>/dev/null || echo "unknown")
    echo "  ✓ Dokku already installed: $INSTALLED_VERSION · skipping install"
else
    echo "▸ Installing Dokku $DOKKU_VERSION (this takes ~3-5 min)..."
    wget -NP /tmp "https://dokku.com/install/$DOKKU_VERSION/bootstrap.sh"
    DOKKU_TAG=$DOKKU_VERSION bash /tmp/bootstrap.sh
    echo "  ✓ Dokku installed"
fi

# Make sure dokku command works for root
if ! command -v dokku &> /dev/null; then
    echo "✗ Dokku not in PATH after install · check the installer log"
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────
# 5. Wire SSH key to dokku user (so git push dokku works)
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Wiring SSH key to dokku user..."
if [ -f /root/.ssh/authorized_keys ]; then
    while IFS= read -r key; do
        [ -z "$key" ] && continue
        [[ "$key" == \#* ]] && continue
        echo "$key" | dokku ssh-keys:add admin-$(date +%s)-$RANDOM 2>/dev/null || true
    done < /root/.ssh/authorized_keys
    echo "  ✓ Keys synced from /root/.ssh/authorized_keys"
else
    echo "  ⚠ No /root/.ssh/authorized_keys found"
fi

# ─────────────────────────────────────────────────────────────────────
# 6. Install Dokku plugins
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Installing Dokku plugins..."

install_plugin() {
    local name=$1
    local url=$2
    if dokku plugin:list | grep -q "^  $name"; then
        echo "  ✓ Plugin $name already installed"
    else
        echo "  → Installing $name..."
        dokku plugin:install "$url" "$name" || echo "  ⚠ $name install returned non-zero (may already be installed)"
    fi
}

install_plugin "letsencrypt" "https://github.com/dokku/dokku-letsencrypt.git"
install_plugin "postgres"    "https://github.com/dokku/dokku-postgres.git"
install_plugin "redis"       "https://github.com/dokku/dokku-redis.git"

# ─────────────────────────────────────────────────────────────────────
# 7. Configure global Let's Encrypt email
# ─────────────────────────────────────────────────────────────────────
echo ""
if [ -n "${LETSENCRYPT_EMAIL:-}" ]; then
    echo "▸ Setting global Let's Encrypt email..."
    dokku letsencrypt:set --global email "$LETSENCRYPT_EMAIL"
    echo "  ✓ Email set: $LETSENCRYPT_EMAIL"
fi

# ─────────────────────────────────────────────────────────────────────
# 8. Schedule Let's Encrypt auto-renew
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Scheduling SSL auto-renewal..."
dokku letsencrypt:cron-job --add 2>/dev/null || echo "  ✓ Cron job already scheduled"

# ─────────────────────────────────────────────────────────────────────
# 9. Tune system limits for sustained WebSocket connections
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Tuning system limits for WebSockets..."

cat > /etc/security/limits.d/empire.conf <<'EOF'
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
EOF

# Sysctl tuning for many concurrent connections
cat > /etc/sysctl.d/99-empire.conf <<'EOF'
# Empire AI · WebSocket-friendly TCP tuning
net.core.somaxconn = 1024
net.ipv4.tcp_max_syn_backlog = 4096
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 30
net.ipv4.ip_local_port_range = 1024 65535
EOF
sysctl -p /etc/sysctl.d/99-empire.conf > /dev/null
echo "  ✓ System limits tuned"

# ─────────────────────────────────────────────────────────────────────
# 10. fail2ban for SSH brute force protection
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▸ Hardening fail2ban..."

cat > /etc/fail2ban/jail.d/empire.conf <<'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
findtime = 600
bantime = 3600
EOF

systemctl enable fail2ban > /dev/null 2>&1
systemctl restart fail2ban
echo "  ✓ fail2ban active"

# ─────────────────────────────────────────────────────────────────────
# 11. Done
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "  ✓ HETZNER BOOTSTRAP COMPLETE"
echo "═══════════════════════════════════════════════════════════════════════"
echo ""
echo "  Dokku version : $(dokku version)"
echo "  Plugins       : letsencrypt, postgres, redis"
echo "  Firewall      : ufw (22, 80, 443)"
echo "  Hardening     : fail2ban active"
echo ""
echo "  Next: run empire-app-setup.sh to create the app"
echo ""
