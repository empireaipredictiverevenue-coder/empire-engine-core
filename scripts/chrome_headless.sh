#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# Chrome Headless + Xvfb startup script
# ──────────────────────────────────────────────────────────────────────
# This script starts Xvfb (virtual display) and Chrome in headless mode
# with the DevTools debugging endpoint on port 9222.
#
# Designed to be managed by PM2 for auto-restart on crash.
#
# Usage:
#   pm2 start scripts/chrome_headless.sh --name empire-chrome
# ──────────────────────────────────────────────────────────────────────

set -e

CHROME_BIN="/usr/bin/google-chrome"
CHROME_PROFILE="/tmp/empire-chrome-profile"
CHROME_PORT="${CHROME_DEBUG_PORT:-9222}"
XVFB_DISPLAY=":99"

# ── Pre-flight checks ──────────────────────────────────────────────

echo "[chrome] Verifying port $CHROME_PORT is free..."
if ss -tln 2>/dev/null | grep -q ":$CHROME_PORT "; then
  echo "[chrome] ERROR: Port $CHROME_PORT is already in use. Kill the existing process first."
  exit 1
fi

# ── Functions ──────────────────────────────────────────────────────

cleanup() {
  echo "[chrome] Shutting down..."
  # Kill Chrome first (it will try to connect to Xvfb)
  pkill -f "chrome.*remote-debugging-port=$CHROME_PORT" 2>/dev/null || true
  sleep 1
  # Kill Xvfb
  pkill -f "Xvfb $XVFB_DISPLAY" 2>/dev/null || true
  sleep 1
  rm -f "/tmp/.X${XVFB_DISPLAY#:}-lock" 2>/dev/null || true
  echo "[chrome] Cleanup complete."
  exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# ── Boot Xvfb ──────────────────────────────────────────────────────

# Clean stale lock
rm -f "/tmp/.X${XVFB_DISPLAY#:}-lock" 2>/dev/null || true

echo "[chrome] Starting Xvfb on $XVFB_DISPLAY..."
Xvfb "$XVFB_DISPLAY" -screen 0 1920x1080x24 &
XVFB_PID=$!
sleep 2

if ! kill -0 "$XVFB_PID" 2>/dev/null; then
  echo "[chrome] ERROR: Xvfb failed to start"
  exit 1
fi
echo "[chrome] Xvfb PID $XVFB_PID ready."

# ── Boot Chrome ────────────────────────────────────────────────────

# Ensure profile dir exists
mkdir -p "$CHROME_PROFILE"

export DISPLAY="$XVFB_DISPLAY"

echo "[chrome] Starting Chrome on port $CHROME_PORT..."
echo "[chrome] Profile: $CHROME_PROFILE"

"$CHROME_BIN" \
  --no-sandbox \
  --headless=new \
  --remote-debugging-port="$CHROME_PORT" \
  --user-data-dir="$CHROME_PROFILE" \
  --disable-dev-shm-usage \
  --disable-gpu \
  --disable-software-rasterizer \
  --disable-extensions \
  --disable-background-networking \
  --disable-sync \
  --no-first-run \
  --no-default-browser-check \
  --hide-scrollbars \
  --mute-audio \
  --disable-background-mode \
  --disable-component-update \
  --disable-quic \
  --remote-allow-origins=* \
  --disable-features=ChromeWhatsNewUI \
  2>&1 &

CHROME_PID=$!
echo "[chrome] Chrome PID $CHROME_PID"

# Wait for Chrome to be ready
for i in $(seq 1 30); do
  if curl -s "http://localhost:$CHROME_PORT/json/version" >/dev/null 2>&1; then
    echo "[chrome] Ready! Debugging at http://localhost:$CHROME_PORT"
    break
  fi
  sleep 1
done

if ! curl -s "http://localhost:$CHROME_PORT/json/version" >/dev/null 2>&1; then
  echo "[chrome] ERROR: Chrome failed to start or respond — check pm2 logs empire-chrome for details"
  exit 1
fi

# Chrome is now running. Wait indefinitely (PM2 restarts if this exits)
wait $CHROME_PID
