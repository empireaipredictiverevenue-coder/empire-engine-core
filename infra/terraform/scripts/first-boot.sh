#!/bin/bash
# Empire AI — Hetzner Cloud first-boot script (cloud-init user_data).
#
# Runs ONCE on the new box as root, after the OS image boots but
# before Terraform considers the server "ready". Keep this fast
# (~30s) and idempotent so `terraform apply` is fast and re-runnable.
#
# This script intentionally does NOT install Ollama, PM2, the
# reverse proxy, or the app code. Those are in the post-provision
# runbook (DEPLOY_HETZNER.md §2 onward) so they can be re-run
# after `git pull` without re-creating the box.

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# 1. apt update + upgrade (security patches)
apt-get update -y
apt-get upgrade -y

# 2. Base packages the deploy scripts + the app need
apt-get install -y \
    curl \
    wget \
    git \
    ca-certificates \
    gnupg \
    ufw \
    fail2ban \
    htop \
    vim \
    unattended-upgrades \
    apt-transport-https

# 3. Log dir (PM2 + uvicorn write here; rotated by PM2/logrotate)
mkdir -p /var/log/empire
chmod 755 /var/log/empire

# 4. Timezone (UTC keeps the AGI governor's cron + audit logs sane)
timedatectl set-timezone UTC

# 5. Unattended security upgrades — auto-install OS security patches
dpkg-reconfigure -plow unattended-upgrades

# 6. fail2ban — SSH brute-force protection. Defaults: 5 attempts per
# 10 min, 1-hour ban. Tighten by editing /etc/fail2ban/jail.local
# after provisioning.
cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port    = ssh
filter  = sshd
logpath = %(sshd_log)s
EOF
systemctl enable --now fail2ban

# 7. ufw defaults (we don't actually use ufw — Hetzner Cloud
# firewalls handle ingress. Leaving ufw in default-deny-all
# state would block the cloud firewall's traffic, so we keep
# it disabled. The comment is here so future readers don't
# add `ufw allow 22` and silently double-up the ruleset.)
# ufw --force reset
# ufw default deny incoming
# ufw default allow outgoing
# ufw --force enable

echo "[first-boot] done — box is ready for DEPLOY_HETZNER.md §2+"
