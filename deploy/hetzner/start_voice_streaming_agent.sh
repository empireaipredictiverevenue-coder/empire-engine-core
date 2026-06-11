#!/bin/bash
# Empire AI — production startup for the voice_streaming_agent bot
# Run by PM2 via deploy/hetzner/ecosystem.config.js
#
# What this does:
#   1. Loads /root/.env
#   2. Verifies the brain URL + public base URL are set
#   3. Runs the AGI-orchestrated voice_streaming_agent in its event loop

set -euo pipefail

if [ -f /root/.env ]; then
    set -a
    # shellcheck disable=SC1091
    source /root/.env
    set +a
else
    echo "[voice_streaming_agent] FATAL: /root/.env not found" >&2
    exit 1
fi

# The agent registers streams with synthetic_brain on loopback.
# Vonage (the only entity that sees the public wss:// URL) connects to
# EMPIRE_PUBLIC_BASE_URL, which Caddy/Nginx reverse-proxies back to
# 127.0.0.1:8005.
: "${SYNTHETIC_BRAIN_API_KEY:?must be set in /root/.env}"
: "${SYNTHETIC_BRAIN_URL:=http://127.0.0.1:8005}"
: "${EMPIRE_PUBLIC_BASE_URL:?must be set in /root/.env (e.g. https://brain.your-domain.com)}"
: "${STREAM_CONFIDENCE_THRESHOLD:=0.7}"
: "${VOICE_STREAMING_INTERVAL_HOURS:=0.5}"

cd /root/empire-v49

echo "[voice_streaming_agent] starting (brain: $SYNTHETIC_BRAIN_URL, public: $EMPIRE_PUBLIC_BASE_URL, threshold: $STREAM_CONFIDENCE_THRESHOLD)"

exec python3 -u bots/voice_streaming_agent.py
