#!/bin/bash
# Empire AI · safe hub restart
# 1. clear stale .pyc files (root cause of "port 8000 not bound" issues)
# 2. restart the hub
# 3. wait for port 8000 to come up
# 4. report status
set -e

HUB_PORT=8000
LOG=/root/empire-v49/logs/hub_restart.log
MAX_WAIT=300  # 5 minutes for slow imports

echo "[$(date -u +%H:%M:%S)] restarting hub..."
echo "[$(date -u +%H:%M:%S)] clearing __pycache__..."
find /root/empire-v49 -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

echo "[$(date -u +%H:%M:%S)] pm2 restart..."
pm2 restart empire-hub >/dev/null 2>&1

echo "[$(date -u +%H:%M:%S)] waiting for port $HUB_PORT..."
elapsed=0
while ! curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$HUB_PORT/" 2>/dev/null | grep -q 200; do
  if [ $elapsed -ge $MAX_WAIT ]; then
    echo "[$(date -u +%H:%M:%S)] TIMEOUT after ${MAX_WAIT}s — hub did not come up"
    exit 1
  fi
  sleep 5
  elapsed=$((elapsed + 5))
done

echo "[$(date -u +%H:%M:%S)] hub UP on port $HUB_PORT"
pm2 show empire-hub 2>&1 | grep -E "status|↺" | head -2
