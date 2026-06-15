#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────────────────
# EMPIRE V49 · DEPLOY ADMIN EXECUTIVE COMMAND CENTER
# ────────────────────────────────────────────────────────────────────────────
# Launches the cockpit portal on Port 8120 using uvicorn.
#
# Usage:
#   chmod +x deploy_admin.sh
#   ./deploy_admin.sh
#
# Environment (must be set in /root/.env):
#   SUPABASE_URL              Supabase project URL
#   SUPABASE_SERVICE_KEY      Service role key (NOT anon key)
# ────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REPO="/root/empire-v49"
WORKER="$REPO/workers/admin_portal.py"
PORT=8120

# Source env if available
if [ -f /root/.env ]; then
  set -a
  source /root/.env
  set +a
fi

# Validate env
if [ -z "${SUPABASE_URL:-}" ] || [ -z "${SUPABASE_SERVICE_KEY:-}" ]; then
  echo "[DEPLOY ADMIN] ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in /root/.env"
  exit 1
fi

echo "[DEPLOY ADMIN] Launching Executive Command Center on port $PORT ..."
cd "$REPO"

exec uvicorn workers.admin_portal:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --log-level info \
  --access-log \
  --timeout-keep-alive 30
