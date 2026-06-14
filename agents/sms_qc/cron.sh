#!/bin/bash
# sms_qc daemon wrapper. Use pm2 to run this -- NOT cron.
# Cron is wrong for QC because it polls; we want a long-lived process.
# The cron.sh exists as a fallback in case pm2 dies: every 5 min
# it pings the daemon, and if the daemon is down, it sends a
# Telegram alert.
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a

# Health check: is the daemon process alive?
if pgrep -f "agents.sms_qc" > /dev/null; then
    exit 0
fi

# Daemon is down. Try to restart it via pm2.
if command -v pm2 > /dev/null 2>&1; then
    pm2 restart sms-qc 2>/dev/null || pm2 start /root/empire-v49/agents/sms_qc/cron.sh --name sms-qc --interpreter bash 2>/dev/null
fi

# Notify via Telegram.
DAEMON="/usr/bin/python3"
MSG="[sms_qc] cron health check: daemon was down at $(date -u +%Y-%m-%dT%H:%M:%SZ). Restarted."
/usr/local/bin/hermes send --to telegram "$MSG" 2>/dev/null || true
echo "$MSG"
