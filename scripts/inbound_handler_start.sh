#!/bin/bash
# Empire AI · safe inbound handler startup
# Ensures the inbound handler is running on port 9120. If it's down,
# restarts it. Loops every 30s checking, exits after first successful start.
set -e
HANDLER_DIR=/root/empire-v49/agents/inbound_handler
LOG=/root/empire-v49/logs/inbound_handler.log
PORT=9120
ATTEMPTS=10

for i in $(seq 1 $ATTEMPTS); do
  if curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q 200; then
    echo "[$(date +%H:%M:%S)] inbound handler already up on port $PORT"
    exit 0
  fi
  echo "[$(date +%H:%M:%S)] attempt $i: starting inbound handler..."
  pkill -f 'uvicorn server:app' 2>/dev/null || true
  sleep 2
  cd "$HANDLER_DIR"
  nohup python3 -m uvicorn server:app --host 0.0.0.0 --port $PORT --log-level info > "$LOG" 2>&1 &
  disown
  sleep 5
  if curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q 200; then
    echo "[$(date +%H:%M:%S)] inbound handler UP on port $PORT"
    exit 0
  fi
  echo "[$(date +%H:%M:%S)] attempt $i failed, retrying..."
done
echo "FATAL: could not start inbound handler after $ATTEMPTS attempts"
tail -20 "$LOG"
exit 1
