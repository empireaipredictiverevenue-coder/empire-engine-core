#!/bin/bash
# Empire AI · Solana USDC Revenue Engine — Background Service Launcher
# ====================================================================
# Starts the standalone payment verification microservice on port 8070.
#
# Usage:
#   chmod +x deploy_payments.sh
#   ./deploy_payments.sh
#
# The service runs as a background daemon. Logs are written to
#   /root/empire-v49/logs/solana_engine.log
#
# For hub-integrated mode (recommended), do NOT run this script.
# Instead, the hub already registers the routes at /api/v1/payments/verify-usdc
# when the SolanaRevenueEngine is configured with the correct env vars.
#
# Pre-requisite env vars (in /root/.env):
#   SUPABASE_URL
#   SUPABASE_SERVICE_ROLE_KEY
#   SOLANA_RPC_URL
#   EMPIRE_VAULT_WALLET
#   EMPIRE_USDC_MINT (optional, defaults to mainnet)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
PID_FILE="${LOG_DIR}/solana_engine.pid"
LOG_FILE="${LOG_DIR}/solana_engine.log"

echo "==> Empire AI · Solana Revenue Engine Launcher"
echo "==> Step 1: Cleaning historical processes on Port 8070..."

# Kill any existing process on port 8070
pkill -f "uvicorn workers.solana_payment_engine:app" 2>/dev/null || true
# Also kill whatever was on port 8070
lsof -ti:8070 2>/dev/null | xargs kill 2>/dev/null || true
sleep 1

echo "==> Step 2: Checking environment..."
REQUIRED_VARS=("SUPABASE_URL" "SUPABASE_SERVICE_ROLE_KEY" "SOLANA_RPC_URL" "EMPIRE_VAULT_WALLET")
MISSING=0
for VAR in "${REQUIRED_VARS[@]}"; do
    if [ -z "$(eval echo \${$VAR:-})" ]; then
        echo "    ⚠  $VAR is not set — checking /root/.env..."
        # Try sourcing from /root/.env
        if [ -f /root/.env ]; then
            VAL=$(grep "^${VAR}=" /root/.env | head -1 | cut -d= -f2-)
            if [ -n "$VAL" ]; then
                export "$VAR=$VAL"
                echo "    ✓ $VAR loaded from /root/.env"
            else
                echo "    ✗ $VAR not found in /root/.env"
                MISSING=1
            fi
        else
            echo "    ✗ $VAR not set and /root/.env not found"
            MISSING=1
        fi
    else
        echo "    ✓ $VAR is set"
    fi
done

if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "==> ⚠  Some required env vars are missing. The engine may not function correctly."
    echo "    Set them in /root/.env and re-run, or export them manually."
    echo "    Continuing anyway..."
fi

echo "==> Step 3: Creating log directory..."
mkdir -p "$LOG_DIR"

echo "==> Step 4: Instantiating Live Solana Payment Monitor Engine..."
cd "$SCRIPT_DIR"

# Source /root/.env if it exists (after our explicit checks, for any remaining vars)
if [ -f /root/.env ]; then
    set -a
    source /root/.env
    set +a
fi

nohup uvicorn workers.solana_payment_engine:app \
    --host 0.0.0.0 \
    --port 8070 \
    --workers 1 \
    --log-level info \
    > "$LOG_FILE" 2>&1 &

ENGINE_PID=$!
echo "$ENGINE_PID" > "$PID_FILE"

sleep 2

# Verify it's running
if kill -0 "$ENGINE_PID" 2>/dev/null; then
    echo "==> ✓ Production Revenue Tracker is active and monitoring on Port 8070 (PID $ENGINE_PID)"
    echo "    Logs: $LOG_FILE"
    echo ""
    echo "    Test the health endpoint:"
    echo "      curl http://localhost:8070/health"
    echo ""
    echo "    Verify a payment:"
    echo '      curl -X POST http://localhost:8070/api/v1/payments/verify-usdc'
    echo '        -H "Content-Type: application/json"'
    echo '        -d '\''{"signature_hash":"your_tx_sig","campaign_memo_id":"campaign_001"}'\'
else
    echo "==> ✗ Engine failed to start. Check logs: $LOG_FILE"
    tail -20 "$LOG_FILE"
    exit 1
fi
