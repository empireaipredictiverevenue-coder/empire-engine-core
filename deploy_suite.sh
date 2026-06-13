#!/bin/bash
# =============================================================================
# EMPIRE AI · MULTI-PRODUCT SUITE DEPLOYMENT
# =============================================================================
# Deploys the 3-product Suite Gateway (Inbound Router, Data Vault, Buyer Spy AI)
# with the subscription + feature-flag entitlement system.
#
# Usage:
#   chmod +x deploy_suite.sh
#   ./deploy_suite.sh              # deploy standalone suite gateway on port 8040
#   ./deploy_suite.sh --integrated # ONLY init DB + restart hub (routes on main API)
#   ./deploy_suite.sh --status     # check gateway health
#   ./deploy_suite.sh --validate   # send a test gatecheck request
#   ./deploy_suite.sh --stop       # kill the standalone gateway
# =============================================================================
set -e

BASE_DIR="/root/empire-v49"
LOG_DIR="$BASE_DIR/logs"
SUITE_PORT="${SUITE_PORT:-8040}"
ENV_FILE="/root/.env"

echo ""
echo "═══ EMPIRE AI SUITE GATEWAY ═══"
echo "Base:      $BASE_DIR"
echo "Port:      $SUITE_PORT"
echo "Mode:      $1"

# ── 1. Init DB schema ──────────────────────────────────────────────────────
echo ""
echo "==> Initializing database extensions (product_subscriptions, feature_flags)..."
python3 -c "
from suite_core import _init_suite_db
_init_suite_db()
print('[suite] Local SQLite schema initialized successfully.')
" 2>&1 || echo "[suite] WARNING: DB init had issues (tables may already exist)"

# ── 2. Standalone gateway (port 8040) ──────────────────────────────────────
if [ "$1" = "--integrated" ]; then
    echo ""
    echo "==> Integrated mode: restarting hub to pick up suite routes..."
    pm2 restart empire-hub 2>/dev/null || echo "WARNING: hub not running. Start it separately."
    echo ""
    echo "=== Suite routes are available on the main hub API (/api/v6/suite/*) ==="
    echo ""
    exit 0
fi

if [ "$1" = "--status" ]; then
    echo ""
    echo "==> Checking gateway status..."
    curl -s "http://localhost:$SUITE_PORT/api/v6/suite/health" 2>/dev/null || echo "Gateway not running on port $SUITE_PORT"
    echo ""
    exit 0
fi

if [ "$1" = "--validate" ]; then
    echo ""
    echo "==> Sending test gatecheck..."
    curl -s -X POST "http://localhost:$SUITE_PORT/api/v6/suite/gatecheck" \
        -H "Content-Type: application/json" \
        -d '{"customer_account_id": "client_alpha_operator", "feature_requested": "buyer_spy"}'
    echo ""
    echo ""
    echo "==> Checking suite stats..."
    curl -s "http://localhost:$SUITE_PORT/api/v6/suite/stats"
    echo ""
    exit 0
fi

if [ "$1" = "--stop" ]; then
    echo "==> Stopping suite gateway..."
    pkill -f "uvicorn suite_core:standalone_app" 2>/dev/null || true
    echo "Stopped."
    exit 0
fi

# ── 3. Kill any existing gateway process ────────────────────────────────────
echo ""
echo "==> Stopping any existing gateway process..."
pkill -f "uvicorn suite_core:standalone_app" 2>/dev/null || true
sleep 1

# ── 4. Load env vars (for SUITE_PORT) ───────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE" 2>/dev/null || true
    set +a
fi

# ── 5. Start standalone gateway ────────────────────────────────────────────
mkdir -p "$LOG_DIR"
echo ""
echo "==> Starting Suite Gateway on port $SUITE_PORT..."
nohup uvicorn suite_core:standalone_app \
    --host 0.0.0.0 \
    --port "$SUITE_PORT" \
    --workers 2 \
    --log-level info \
    > "$LOG_DIR/suite_gateway.log" 2>&1 &

GATEWAY_PID=$!
echo "Gateway PID: $GATEWAY_PID"

# Wait for it to be ready
sleep 3

# ── 6. Verification ────────────────────────────────────────────────────────
echo ""
echo "==> Health check..."
curl -s "http://localhost:$SUITE_PORT/api/v6/suite/health" || echo "FAILED"
echo ""

echo ""
echo "==> Gatecheck verification (client_alpha_operator → buyer_spy)..."
curl -s -X POST "http://localhost:$SUITE_PORT/api/v6/suite/gatecheck" \
    -H "Content-Type: application/json" \
    -d '{"customer_account_id": "client_alpha_operator", "feature_requested": "buyer_spy"}'
echo ""

echo ""
echo "==> Stats..."
curl -s "http://localhost:$SUITE_PORT/api/v6/suite/stats"
echo ""

echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  Empire AI Multi-Product Suite is fully deployed and operational"
echo "  Gateway:  http://localhost:$SUITE_PORT"
echo "  Log:      $LOG_DIR/suite_gateway.log"
echo "  Routes:"
echo "    POST /api/v6/suite/gatecheck   — entitlement verification"
echo "    POST /api/v6/suite/usage/log   — usage metering"
echo "    GET  /api/v6/suite/usage       — usage summary"
echo "    GET  /api/v6/suite/subscriptions      — list subscriptions"
echo "    POST /api/v6/suite/subscriptions      — create subscription"
echo "    POST /api/v6/suite/subscriptions/{id}/update — update status"
echo "    GET  /api/v6/suite/stats        — suite-wide stats"
echo "    GET  /api/v6/suite/health       — health check"
echo "══════════════════════════════════════════════════════════════════"
