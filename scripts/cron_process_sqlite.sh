#!/bin/bash
# ── EMPIRE V49 · SQLite Storm Bridge Cron ──────────────────────────
# Backs up the in-process tick() poll by hitting the hub's
# /api/v1/storm/process-sqlite endpoint every 15 minutes.
#
# If the hub is down or the poll cycle already picked up all VERIFIED
# alerts, the endpoint is idempotent — it just returns {"processed":0}.
#
# Called by: empire-sqlite-bridge.timer (systemd)
# Logs to:   /root/empire-v49/logs/sqlite_bridge_cron.log
# ─────────────────────────────────────────────────────────────────────
set -eo pipefail

LOG_DIR="/root/empire-v49/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/sqlite_bridge_cron.log"

# Source env vars (HUB_TOKEN). Use grep to extract only the
# variables we need, avoiding $ interpolation in secret strings.
if [ -f /root/.env ]; then
    export HUB_TOKEN="$(grep '^HUB_TOKEN=' /root/.env | cut -d= -f2- | tr -d '"' || echo 'dev-token-insecure')"
    export EMPIRE_HUB_URL="$(grep '^EMPIRE_HUB_URL=' /root/.env | cut -d= -f2- | tr -d '"' || echo 'http://localhost:8001')"
fi

HUB_URL="${EMPIRE_HUB_URL:-http://localhost:8001}"
TOKEN="${HUB_TOKEN:-dev-token-insecure}"
ENDPOINT="${HUB_URL}/api/v1/storm/process-sqlite"

TS="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

HTTP_CODE=$(curl -s -o /tmp/sqlite_bridge_resp.json -w '%{http_code}' \
    -X POST "$ENDPOINT" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{}' \
    --connect-timeout 10 --max-time 30 2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    PROCESSED=$(python3 -c "import json; d=json.load(open('/tmp/sqlite_bridge_resp.json')); print(d.get('processed', 0))" 2>/dev/null || echo "?")
    echo "[$TS] OK 200 · processed=$PROCESSED" >> "$LOG_FILE"
elif [ "$HTTP_CODE" = "000" ]; then
    echo "[$TS] DOWN · hub unreachable (tick() poll will catch up)" >> "$LOG_FILE"
else
    echo "[$TS] ERR $HTTP_CODE · $(head -c 200 /tmp/sqlite_bridge_resp.json 2>/dev/null || echo 'no body')" >> "$LOG_FILE"
fi

# Trim log to last 500 lines
tail -n 500 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
