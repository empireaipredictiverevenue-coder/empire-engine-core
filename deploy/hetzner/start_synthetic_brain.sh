#!/bin/bash
# Empire AI — production startup for the synthetic_brain server
# Run by PM2 via deploy/hetzner/ecosystem.config.js
#
# What this does:
#   1. Loads /root/.env (which has SYNTHETIC_BRAIN_API_KEY, OLLAMA_MODEL,
#      EMPIRE_PUBLIC_BASE_URL, VONAGE_*)
#   2. Verifies the required env vars are set (fail-closed)
#   3. Launches uvicorn on 0.0.0.0:8005 so the reverse proxy (Caddy/Nginx)
#      can reach it on loopback. The Caddy/Nginx config in deploy/hetzner/
#      does the TLS termination + WebSocket upgrade.

set -euo pipefail

# Load /root/.env into the current shell
if [ -f /root/.env ]; then
    set -a
    # shellcheck disable=SC1091
    source /root/.env
    set +a
else
    echo "[synthetic_brain] FATAL: /root/.env not found" >&2
    exit 1
fi

# Fail-closed: refuse to start if the production env is misconfigured
: "${SYNTHETIC_BRAIN_API_KEY:?must be set in /root/.env}"
: "${EMPIRE_PUBLIC_BASE_URL:?must be set in /root/.env (e.g. https://brain.your-domain.com)}"
: "${OLLAMA_MODEL:=llama3.2:3b}"

cd /root/empire-v49

echo "[synthetic_brain] starting on 0.0.0.0:8005 (public: $EMPIRE_PUBLIC_BASE_URL, model: $OLLAMA_MODEL)"

# `--proxy-headers` makes uvicorn respect X-Forwarded-* from the reverse proxy
# `--ws-max-size 20mb` accommodates long TTS audio payloads
# `--workers 2` = 2 uvicorn worker processes (Caddy round-robins between them).
#   NOTE: this means the in-process _STREAMING_REGISTRY dict is per-worker.
#   For multi-worker deploys, swap the dict for Redis or a shared HTTP poll.
exec uvicorn synthetic_brain:app \
    --host 0.0.0.0 \
    --port 8005 \
    --workers 2 \
    --proxy-headers \
    --ws-max-size 20971520 \
    --log-level info
